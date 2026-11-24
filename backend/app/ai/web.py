"""Web-grounded fallback answers (tier 3 of CampusAtlas answering).

Order of answering for a question:
  1. indexed official sources (RAG over the CampusAtlas index, cited [S#])
  2. on-demand crawl of the college's official site / NIRF tables (live lookup)
  3. THIS MODULE: a live web search (Gemini + Google Search grounding, else Groq Compound
     web search), still cited, official sites preferred and every source badged
     OFFICIAL / THIRD-PARTY / UNVERIFIED.
So the student never hits a dead end, and every sentence still links to where it came from -
unlike a general chatbot, which answers from memory with no sources or dates.
"""
import os
import re
from datetime import datetime

from . import gemini_client, groq_client

WEB_SYSTEM = """You are CampusAtlas, an expert counsellor for Indian engineering admissions and colleges.
Use web search to answer the student's question with CURRENT facts (prefer the latest year).
Prefer official sources: college websites (.ac.in, .edu.in, .edu), JoSAA / JAC Delhi / GGSIPU counselling
sites, NIRF (nirfindia.org), government sites (.gov.in, .nic.in). If you rely on an aggregator
(Shiksha, Collegedunia, Careers360 etc.) say it is unofficial. Never invent cutoffs, fees, packages or dates;
when figures differ between sources, give the range and say so. Give a direct, useful answer first, then
key numbers, then one practical next step. For "which is better / should I" questions give a balanced,
evidence-based view with the trade-offs instead of refusing. Ground reality matters: for placements prefer the
median salary and the share of students placed (NIRF data) over the "highest package"; you may add what current
students report (Reddit, Quora etc.) as a clearly labelled "Students say" line, never as fact. Reply in the same language and style as the
question (English or Hinglish). Max 220 words. Plain text; you may use short "- " bullet lines.
No markdown headings, tables or bold."""

LOCAL_HINT = "\n\nCAMPUSATLAS INDEXED EVIDENCE (official pages; use it if relevant and consistent):\n"


def enabled() -> bool:
    if os.getenv("WEB_FALLBACK", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return gemini_client.is_configured() or groq_client.is_configured()


def _domain(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return (m.group(1) if m else "").lower().removeprefix("www.")


def _groq_web(question: str, timeout: float = 30.0, system: str | None = None) -> dict:
    """Groq Compound (built-in web search). Returns {answer, sources, model}."""
    import httpx

    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key or key == "your_groq_api_key_here":
        raise groq_client.GroqUnavailable("GROQ_API_KEY is not configured")
    model = os.getenv("GROQ_WEB_MODEL", "groq/compound-mini")
    try:
        r = httpx.post(groq_client.GROQ_URL, timeout=timeout,
                       headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                       json={"model": model, "max_tokens": 900, "temperature": 0.2,
                             "messages": [{"role": "system", "content": system or WEB_SYSTEM}, {"role": "user", "content": question}]})
    except httpx.HTTPError as exc:
        raise groq_client.GroqUnavailable(f"Groq web search failed: {type(exc).__name__}") from exc
    if r.status_code != 200:
        raise groq_client.GroqUnavailable(f"Groq web search returned HTTP {r.status_code}")
    msg = (r.json().get("choices") or [{}])[0].get("message", {})
    text = re.sub(r"<think>[\s\S]*?</think>", "", msg.get("content") or "").strip()
    if not text:
        raise groq_client.GroqUnavailable("Groq web search returned an empty answer")
    sources, seen = [], set()
    for tool in msg.get("executed_tools") or []:
        results = tool.get("search_results") or []
        if isinstance(results, dict):
            results = results.get("results") or []
        for res in results:
            url = (res or {}).get("url")
            if url and url not in seen:
                seen.add(url)
                sources.append({"title": (res.get("title") or url)[:160], "url": url, "domain": _domain(url),
                                "snippet": (res.get("content") or "")[:280]})
    for url in re.findall(r"https?://[^\s)\]>\"']+", text + "\n" + (msg.get("reasoning") or "")):
        url = url.rstrip(".,;")
        if url not in seen:
            seen.add(url)
            sources.append({"title": _domain(url), "url": url, "domain": _domain(url), "snippet": ""})
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1", text)  # markdown links -> text (sources listed below)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"(?im)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"\n\s*(sources?|references?)\s*:?\s*\n[\s\S]*$", "", text, flags=re.I).strip()
    return {"answer": text, "sources": sources[:8], "model": model}


_CACHE: dict = {}  # normalized question -> (time, result); web answers for the same question are reused for a day


def search(question: str, local_context: str = "") -> dict | None:
    """Web-grounded answer: Gemini + Google Search first, Groq Compound second. None if both fail."""
    import time

    key = re.sub(r"\W+", " ", question.lower()).strip()
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < float(os.getenv("WEB_CACHE_HOURS", "24")) * 3600:
        return hit[1]
    r = _search(question, local_context)
    if r:
        if len(_CACHE) > 500:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = (time.time(), r)
    return r


def _search(question: str, local_context: str = "") -> dict | None:
    prompt = question + (LOCAL_HINT + local_context[:2500] if local_context else "")
    errors = []
    if gemini_client.is_configured():
        try:
            r = gemini_client.web_research(prompt, system=WEB_SYSTEM)
            return {**r, "provider": "gemini", "errors": errors}
        except gemini_client.GeminiUnavailable as exc:
            errors.append(f"gemini: {exc}")
    if groq_client.is_configured():
        try:
            r = _groq_web(prompt)
            return {**r, "provider": "groq", "errors": errors}
        except groq_client.GroqUnavailable as exc:
            errors.append(f"groq: {exc}")
    return None


def citation_views(sources: list[dict], start: int) -> list[dict]:
    """Shape web sources like indexed citations so the UI shows the same badges."""
    from ..verification.rules import classify_source

    now = datetime.utcnow()
    views = []
    for i, s in enumerate(sources):
        url = s.get("url") or ""
        domain = s.get("domain") or _domain(url)
        verification = classify_source(f"https://{domain}/" if domain else url)
        views.append({
            "index": start + i, "source_id": -(start + i), "source_name": s.get("title") or domain or url,
            "source_url": url, "authority_level": "WEB_SEARCH", "source_type": "WEB_SEARCH", "college_id": "",
            "document_title": s.get("title") or "", "snippet": s.get("snippet") or (f"Found via live web search on {domain}" if domain else ""),
            "score": 1.0, "is_demo": False, "verification": verification, "last_checked": now, "last_changed": None,
            "freshness": {"state": "FRESH", "stale": False, "checked_hours_ago": 0.0, "changed_hours_ago": None,
                          "stale_after_hours": 72},
        })
    return views  # order kept: inline [S#] markers refer to these positions


def add_markers(text: str, supports: list, start: int) -> str:
    """Insert [S#] after each sentence Google Search grounded (Gemini grounding supports).

    `supports` = [(end_byte_index, [chunk_index, ...]), ...]; chunk i becomes [S{start+i}]."""
    if not supports:
        return text
    raw = text.encode("utf-8")
    for end, chunks in sorted(supports, key=lambda x: -x[0]):
        if not chunks or end is None or end > len(raw):
            continue
        tag = "".join(f"[S{start + c}]" for c in sorted(set(chunks))[:3]).encode()
        raw = raw[:end] + tag + raw[end:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return text


# ---------------------------------------------------------------- campus life: official + what students say
LIFE_SECTIONS = [
    ("teaching", "Teachers & teaching"), ("attendance", "Attendance & academics pressure"),
    ("campus_life", "Campus life & crowd"), ("fests", "Fests, clubs & societies"),
    ("hostel_food", "Hostel, food & commute"), ("coding", "Coding culture & placement prep"),
    ("infra", "Infrastructure & labs"), ("watch_out", "Watch out for"),
]
LIFE_SYSTEM = """You research the GROUND REALITY of student life at an Indian engineering college for a student
deciding whether to join. Use web search: the college's own site for official facts (fest names, clubs, hostel),
and student discussions (Reddit r/Indian_Academia and city/college subreddits, Quora, YouTube campus reviews,
Shiksha/Careers360/Collegedunia reviews) for what students actually experience. Be concrete and honest, including
negatives; no brochure language. Name real fests, societies and teams when sources mention them. Where students
disagree, say so. Never invent; if nothing reliable is found for a section write "Not enough reliable information".
Reply in EXACTLY this format, one block per heading, 2-4 short sentences each, plain text, no markdown:
""" + "\n".join(f"{key.upper()}: <text>" for key, _ in LIFE_SECTIONS) + """
VERDICT: <one line: who this college suits and who it doesn't>"""

_LIFE: dict = {}


def _life_path():
    from ..config import data_dir
    return data_dir() / "life_reports.json"


def _life_load():
    import json
    if _LIFE:
        return
    try:
        _LIFE.update(json.loads(_life_path().read_text(encoding="utf-8")))
    except Exception:
        pass


def _life_save():
    import json
    try:
        _life_path().write_text(json.dumps(_LIFE, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def life_report(college_id: str, name: str, city: str = "", local_context: str = "", refresh: bool = False) -> dict | None:
    """Sectioned campus-life report (teachers, attendance, fests, hostel...) with web sources. Cached 7 days
    on disk, so each college costs one search per week however often it is viewed."""
    import time

    _life_load()
    hit = _LIFE.get(college_id)
    if hit and not refresh and time.time() - hit["at"] < float(os.getenv("LIFE_CACHE_DAYS", "7")) * 86400:
        return hit
    question = (f"Ground reality of student life at {name}{', ' + city if city else ''}: teachers, attendance, "
                f"campus life, fests and societies, hostel and food, coding culture, infrastructure.")
    if local_context:
        question += "\n\nOFFICIAL NIRF DATA (already verified; use, don't repeat verbatim):\n" + local_context[:1500]
    r = None
    if gemini_client.is_configured():
        try:
            r = {**gemini_client.web_research(question, system=LIFE_SYSTEM, timeout=45.0), "provider": "gemini"}
        except gemini_client.GeminiUnavailable:
            r = None
    if r is None and groq_client.is_configured():
        try:
            r = {**_groq_web(question, timeout=45.0, system=LIFE_SYSTEM), "provider": "groq"}
        except groq_client.GroqUnavailable:
            r = None
    if not r or not r.get("answer"):
        return hit  # stale report is better than none
    sections = parse_sections(r["answer"])
    if len([v for v in sections.values() if v]) < 3:
        return hit
    report = {"at": time.time(), "college_id": college_id, "sections": sections, "provider": r["provider"],
              "model": r.get("model"), "sources": [{k: s.get(k) for k in ("title", "url", "domain")} for s in r.get("sources") or []][:10]}
    _LIFE[college_id] = report
    _life_save()
    return report


def parse_sections(text: str) -> dict:
    keys = [k.upper() for k, _ in LIFE_SECTIONS] + ["VERDICT"]
    pattern = re.compile(r"^\s*\**(" + "|".join(keys) + r")\**\s*:\s*", re.M)
    parts = pattern.split(text)
    out = {k.lower(): "" for k in keys}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i].lower()] = re.sub(r"\s+", " ", re.sub(r"\s*\[\d+(?:,\s*\d+)*\]", "", parts[i + 1])).strip()
    return out
