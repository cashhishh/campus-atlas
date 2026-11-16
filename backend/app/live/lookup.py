"""On-demand evidence lookup when the index has no answer.

Steps (each stops as soon as a grounded, cited answer is possible):
  1. official   — focused crawl of the college's official domain (≈15 pages / ≈12 s)
  2. nirf       — the college's row in the official NIRF ranking tables
  3. third_party— a reputable third-party page, ingested and badged THIRD-PARTY
  4. none       — "Official sources don't publish this information (checked: …)"
Every answer still comes from rag.answer() over ingested text, so every fact is
cited. Nothing is answered from model memory. Results are cached for 24 h per
college + topic.
"""
import json
import os
import time
from datetime import datetime, timedelta

from ..ingestion.pipeline import process_text
from ..models.models import College, LiveLookup, Source
from ..retrieval.rag import answer
from . import crawler, nirf
from .topics import CONTACT_KEYWORDS, TOPIC_KEYWORDS, detect_topic, third_party_urls

START_URLS = {"usict": "https://www.ipu.ac.in/usict/index.php"}
CACHE_HOURS = 24
SNAPSHOT = "SNAPSHOT"  # ingested once on demand; not re-fetched by the monitor


def enabled() -> bool:
    return os.getenv("LIVE_FETCH_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def budget_s() -> float:
    return float(os.getenv("LIVE_FETCH_BUDGET_SECONDS", "10"))


def plan(db, result: dict) -> dict | None:
    """What a live lookup would check for this (ungrounded) result, or None."""
    if not enabled() or result.get("grounded") or not result.get("college_ids"):
        return None
    if result.get("intent") == "comparison" or len(result.get("college_ids") or []) > 1:
        return None  # "which is better" is a judgement, not a fact a page can state
    college = db.get(College, result["college_ids"][0])
    if not college or not college.official_domain:
        return None
    return {"college_id": college.id, "domain": college.official_domain,
            "topic": detect_topic(result.get("question", ""), result.get("intent"))}


def _today() -> str:
    return datetime.utcnow().strftime("%d %b %Y")


def _ingest(db, college_id: str, docs: list[dict], kind: str, keywords: list[str]) -> list[str]:
    """Register + ingest fetched docs. Returns URLs whose content was (re)indexed."""
    source_type, authority, status = {
        "official": ("LIVE_OFFICIAL", "HIGH", "ACTIVE"),
        "nirf": ("NIRF_RANKING", "VERY_HIGH", SNAPSHOT),
        "third_party": ("THIRD_PARTY_REFERENCE", "LOW", SNAPSHOT),
    }[kind]
    indexed = []
    for doc in docs:
        text = doc.get("text") or ""
        if len(text) < 200 and kind != "nirf":
            continue
        if kind == "official" and not any(k in text.lower() for k in keywords):
            continue
        src = db.query(Source).filter(Source.college_id == college_id, Source.source_url == doc["url"]).first()
        if src is not None and (src.is_demo or src.status == "DEMO_READY"):
            continue  # never overwrite labelled DEMO DATA with live text
        if src is None:
            label = {"official": "live fetch", "nirf": "NIRF", "third_party": "third-party"}[kind]
            src = Source(college_id=college_id, source_name=f"{(doc.get('title') or doc['url'])[:110]} ({label})",
                         source_url=doc["url"], source_type=source_type, authority_level=authority, status=status, is_demo=False)
            db.add(src)
            db.commit()
            db.refresh(src)
        try:
            out = process_text(db, src, text[:60000], doc.get("title"), doc.get("doc_type", "HTML"))
        except Exception:
            db.rollback()
            continue
        if out.get("changed") or src.content_hash:
            indexed.append(doc["url"])
    return indexed


def _keywords(question: str, topic: str, college) -> list[str]:
    """Topic keywords plus the question's own content words (minus the college's names)."""
    from ..retrieval.entities import detect_colleges, strip_phrases
    from ..services.vector_store import tokenize

    _, phrases = detect_colleges(question, [(college.id, college.name)])
    own = [t for t in tokenize(strip_phrases(question, phrases)) if len(t) > 3]
    base = TOPIC_KEYWORDS.get(topic, []) if topic != "general" else []
    return list(dict.fromkeys(own + base)) or TOPIC_KEYWORDS["general"]


def _home(college) -> str:
    return START_URLS.get(college.id, f"https://www.{college.official_domain}/")


def _official_links(db, college, crawl_links) -> list[dict]:
    links = [{"title": f"{college.name} — official website", "url": _home(college)}]
    links += [{"title": a or u, "url": u} for u, a in crawl_links]
    for s in db.query(Source).filter(Source.college_id == college.id, Source.status != "DISABLED").all():
        if (any(k in (s.source_name or "").lower() for k in CONTACT_KEYWORDS) and not s.source_url.lower().endswith(".pdf")
                and crawler.host_of(s.source_url).endswith(college.official_domain)):
            links.append({"title": s.source_name, "url": s.source_url})
    seen, out = set(), []
    for link in links:
        if link["url"] not in seen:
            seen.add(link["url"])
            out.append(link)
    return out[:4]


def _short(url: str) -> str:
    s = url.split("://", 1)[-1].removeprefix("www.")
    return s if len(s) <= 60 else s[:57] + "…"


def _not_published(result: dict, college, checked: list[str], links: list[dict], meta: dict, unreadable: bool = False) -> dict:
    shown = [_short(u) for u in dict.fromkeys(checked)]
    listed = ", ".join(shown[:6]) + (f" and {len(shown) - 6} more" if len(shown) > 6 else "")
    text = (f"Official sources don't publish this information (checked: {listed or college.official_domain})."
            if shown or college else result["answer"])
    if unreadable:
        text += (f" Note: {college.official_domain} could not be read automatically (its pages need JavaScript or "
                 f"returned no text), so please check it directly.")
    return {**result, "answer": text, "sources": [], "grounded": False, "mode": "none", "provider": "none",
            "answer_label": f"Searched {len(shown)} official/public page(s) · {_today()}", "official_links": links,
            "live": {**meta, "step": "none"}}


def _save(db, college_id, topic, outcome, payload):
    db.add(LiveLookup(college_id=college_id, topic=topic, outcome=outcome, result=json.dumps(payload, default=str)))
    db.commit()


def resolve(db, question: str, first: dict, registry=None, use_llm: bool = True) -> dict:
    """Try to turn an ungrounded result into a cited one. Always returns a result dict."""
    started = time.perf_counter()
    p = plan(db, first)
    if p is None:
        return first
    college = db.get(College, p["college_id"])
    topic, domain = p["topic"], p["domain"]
    keywords = _keywords(question, topic, college)
    meta = {"college_id": college.id, "domain": domain, "topic": topic, "cached": False, "fetched_at": datetime.utcnow()}

    def finish(r):
        r["latency"] = {**r.get("latency", {}), "total_ms": round((time.perf_counter() - started) * 1000 + first["latency"]["total_ms"], 1)}
        return r

    cached = (db.query(LiveLookup).filter(LiveLookup.college_id == college.id, LiveLookup.topic == topic,
                                          LiveLookup.created_at >= datetime.utcnow() - timedelta(hours=CACHE_HOURS))
              .order_by(LiveLookup.created_at.desc()).first())
    if cached:  # anything found earlier is already indexed; do not crawl again
        data = json.loads(cached.result or "{}")
        meta.update(cached=True, fetched_at=cached.created_at, checked=data.get("checked", []))
        if cached.outcome != "none":
            again = answer(question, [college.id], first.get("intent"), db=db, registry=registry, use_llm=use_llm)
            if again["grounded"]:
                return finish({**again, "answer_label": data.get("label"), "live": {**meta, "step": cached.outcome},
                               **({"third_party_note": data["note"]} if data.get("note") else {})})
        return finish(_not_published(first, college, data.get("checked", []), data.get("links", []), meta,
                                     unreadable=data.get("unreadable", False)))

    checked, fetched = [], []
    skip = {s.source_url for s in db.query(Source).filter(Source.college_id == college.id).all()}

    # 1. official domain
    start = START_URLS.get(college.id, f"https://{domain}/")
    crawl = crawler.crawl(start, domain, keywords, skip_urls=skip, max_pages=15, budget_s=budget_s())
    checked += crawl["checked"]
    links = _official_links(db, college, crawl["links"])
    steps = [("official", lambda: crawl["docs"]),
             ("nirf", lambda: _nirf_docs(college, checked)),
             ("third_party", lambda: _third_party_docs(college, topic, checked))]
    for kind, get_docs in steps:
        if kind == "nirf" and topic != "rankings":  # NIRF rows hold only rank / score
            continue
        new = _ingest(db, college.id, get_docs(), kind, keywords)
        fetched += new
        if not new:
            continue
        again = answer(question, [college.id], first.get("intent"), db=db, registry=registry, use_llm=use_llm)
        if not again["grounded"]:
            continue
        host = {"official": domain, "nirf": "nirfindia.org"}.get(kind) or crawler.host_of(new[0])
        label = (f"Unverified third-party · {host} · {_today()}" if kind == "third_party"
                 else f"Fetched live from {host} · {_today()}")
        note = (f"This answer uses a third-party website, not {college.name}. Please confirm it on the official site "
                f"({_home(college)}).") if kind == "third_party" else None
        payload = {"label": label, "note": note, "checked": checked, "fetched": fetched, "links": links}
        _save(db, college.id, topic, kind, payload)
        out = {**again, "answer_label": label, "official_links": links,
               "live": {**meta, "step": kind, "checked": checked, "fetched": fetched, "elapsed_s": round(time.perf_counter() - started, 1)}}
        if note:
            out["third_party_note"] = note
        return finish(out)

    unreadable = not crawl.get("home_readable", False)
    _save(db, college.id, topic, "none", {"checked": checked, "fetched": fetched, "links": links, "unreadable": unreadable})
    return finish(_not_published(first, college, checked, links,
                                 {**meta, "checked": checked, "fetched": fetched, "elapsed_s": round(time.perf_counter() - started, 1)},
                                 unreadable=unreadable))


def _nirf_docs(college, checked: list[str]) -> list[dict]:
    res = nirf.lookup([college.name], budget_s=8.0)
    checked += res["checked"]
    return res["docs"]


def _third_party_docs(college, topic: str, checked: list[str]) -> list[dict]:
    docs = []
    for url in third_party_urls(college.id, topic):
        checked.append(url)
        try:
            doc = crawler.fetch(url, timeout=8.0, browser_ua=True)
        except Exception:
            continue
        doc["title"] = f"{crawler.host_of(url)} — {college.name} {topic}"
        docs.append(doc)
    return docs


# ---------------------------------------------------------------- multi-college fill (comparisons)
COMPARE_KEYWORDS = ["fee", "fees", "placement", "nirf", "b.tech", "btech", "programme", "intake", "hostel", "admission"]


def fill_plan(db, college_ids: list[str], topic: str) -> dict | None:
    """Colleges in a comparison whose official site has not been searched for this topic in 24 h."""
    if not enabled():
        return None
    since = datetime.utcnow() - timedelta(hours=CACHE_HOURS)
    todo = []
    for cid in college_ids:
        college = db.get(College, cid)
        if not college or not college.official_domain:
            continue
        if db.query(LiveLookup).filter(LiveLookup.college_id == cid, LiveLookup.topic == topic,
                                       LiveLookup.created_at >= since).first():
            continue
        todo.append(college)
    if not todo:
        return None
    return {"colleges": [c.id for c in todo], "domains": [c.official_domain for c in todo], "topic": topic}


def fill(db, college_ids: list[str], topic: str, keywords: list[str] | None = None) -> dict:
    """Crawl every listed college's official domain IN PARALLEL (one shared ~10 s budget), ingest, cache."""
    from concurrent.futures import ThreadPoolExecutor

    keywords = keywords or COMPARE_KEYWORDS
    colleges = [db.get(College, cid) for cid in college_ids]
    colleges = [c for c in colleges if c and c.official_domain]
    skips = {c.id: {s.source_url for s in db.query(Source).filter(Source.college_id == c.id).all()} for c in colleges}
    pool = ThreadPoolExecutor(max_workers=max(1, len(colleges)))
    try:
        futures = {c.id: pool.submit(crawler.crawl, START_URLS.get(c.id, f"https://{c.official_domain}/"), c.official_domain,
                                     keywords, skips[c.id], 12, budget_s()) for c in colleges}
        crawls = {}
        for cid, f in futures.items():
            try:
                crawls[cid] = f.result(timeout=budget_s() + 2)
            except Exception:
                crawls[cid] = {"docs": [], "checked": [], "links": []}
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    report = {"checked": [], "fetched": [], "domains": [c.official_domain for c in colleges]}
    for c in colleges:
        crawl = crawls[c.id]
        new = _ingest(db, c.id, crawl["docs"], "official", keywords)
        report["checked"] += crawl["checked"]
        report["fetched"] += new
        _save(db, c.id, topic, "official" if new else "none",
              {"checked": crawl["checked"], "fetched": new, "links": _official_links(db, c, crawl.get("links", [])),
               "unreadable": not crawl.get("home_readable", False), "label": f"Fetched live from {c.official_domain} · {_today()}"})
    return report
