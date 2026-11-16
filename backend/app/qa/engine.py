"""Question answering orchestration on top of retrieval.

FACT      -> sub-query retrieval (hybrid) -> grounded LLM answer with [S#] citations
COMPARE   -> per-college cited table (structured NIRF facts + retrieved snippets) + neutral summary
RECOMMEND -> candidates by location / branch evidence, ranked by NIRF facts, cited table + caveat
LIST      -> same as RECOMMEND without ranking claims
Every cell and sentence comes from an ingested source; missing cells say "not in sources".
"""
import re
import time

from ..facts.nirf_facts import facts_for
from ..models.models import College, Source
from ..retrieval.rag import _source_view, answer, best_snippet, retrieve
from .understand import TOPIC_QUERY, understand

NOT_IN_SOURCES = "not in sources"
CAVEAT = ("Which is better depends on your branch, budget and priorities — use Find My College to weigh them. "
          "This is not an absolute verdict.")
PILOT = ["dtu", "nsut", "igdtuw", "mait", "bpit", "gtbit", "msit", "usict"]


def _lakh(n: float) -> str:
    return f"₹{n / 100000:.2f} L".replace(".00 L", " L")


class Citations:
    """Assigns [S#] numbers to sources as cells cite them."""

    def __init__(self, db):
        self.db, self.index, self.views = db, {}, []

    def cite(self, meta: dict, snippet: str = "", score: float = 1.0) -> int:
        sid = meta["source_id"]
        if sid not in self.index:
            self.index[sid] = len(self.index) + 1
            self.views.append(_source_view(meta, self.db, self.index[sid], snippet, score))
        return self.index[sid]

    def cite_source(self, src_id: int, snippet: str) -> int | None:
        src = self.db.get(Source, src_id) if src_id else None
        if not src:
            return None
        meta = {"source_id": src.id, "source_name": src.source_name, "source_url": src.source_url,
                "authority_level": src.authority_level, "source_type": src.source_type, "college_id": src.college_id,
                "document_title": src.source_name, "is_demo": bool(src.is_demo)}
        return self.cite(meta, snippet)


# A fee cell needs a fee word AND an amount (bare 6-digit numbers are often pincodes).
MONEY = re.compile(r"(?=.*\b(fee|fees|tuition)\b)(?=.*((₹|rs\.?|inr)\s?[\d,]{4,}|\b\d{1,2},\d{2},\d{3}\b))", re.I | re.S)
RANKISH = re.compile(r"(rank|band)\D{0,25}\d", re.I)


def _snippet_cell(cites: Citations, cid: str, query: str, need_digit: bool = False, min_rel: float = 0.34,
                  pattern: re.Pattern | None = None, terms: str | None = None) -> dict:
    hits = retrieve(query, [cid], min_relevance=min_rel)["hits"]
    for h in hits[:4]:
        text = best_snippet(h["text"], terms or query, max_sentences=1)
        if need_digit and not re.search(r"\d", text):
            continue
        if pattern is not None and not pattern.search(text):
            continue
        if len(re.findall(r"[a-z]{3,}", text.lower())) < 4:  # table fragments / menus
            continue
        n = cites.cite(h["metadata"], h["text"], h["score"])
        return {"text": text[:230], "cite": [n]}
    return {"text": NOT_IN_SOURCES, "cite": []}


def _nirf_cell(cites, facts, cid) -> dict:
    if "nirf_rank" in facts:
        f = facts["nirf_rank"]
        score = facts.get("nirf_score")
        n = cites.cite_source(f.source_id, f.evidence)
        return {"text": f"Rank {f.value}" + (f" (score {score.value})" if score else "") + f", NIRF {f.year} Engineering",
                "cite": [n] if n else [], "num": f.num}
    if "nirf_band" in facts:
        f = facts["nirf_band"]
        n = cites.cite_source(f.source_id, f.evidence)
        label = "GGSIPU (parent university) " if cid == "usict" else ""
        return {"text": f"{label}Rank band {f.value}, NIRF {f.year} Engineering", "cite": [n] if n else [], "num": f.num}
    return _snippet_cell(cites, cid, "NIRF rank band ranking", min_rel=0.5, pattern=RANKISH)


def _fact_cell(cites, facts, field, fmt) -> dict:
    f = facts.get(field)
    if not f:
        return {"text": NOT_IN_SOURCES, "cite": []}
    n = cites.cite_source(f.source_id, f.evidence)
    return {"text": fmt(f), "cite": [n] if n else [], "num": f.num}


ROWS = {
    "NIRF 2025": lambda c, f, cid: _nirf_cell(c, f, cid),
    "Median UG salary": lambda c, f, cid: _fact_cell(c, f, "median_salary_ug", lambda x: f"{_lakh(x.num)} ({x.year} graduates)"),
    "UG intake": lambda c, f, cid: _fact_cell(c, f, "ug_intake", lambda x: f"{int(x.num):,} seats (sanctioned)"),
    "Fees": lambda c, f, cid: _snippet_cell(c, cid, TOPIC_QUERY["fees"], pattern=MONEY, terms="fee fees tuition annual"),
    "Programmes": lambda c, f, cid: _snippet_cell(c, cid, TOPIC_QUERY["academics"]),
    "Placements": lambda c, f, cid: _snippet_cell(c, cid, TOPIC_QUERY["placements"]),
    "Hostel": lambda c, f, cid: _snippet_cell(c, cid, TOPIC_QUERY["hostel"]),
}
TOPIC_ROWS = {"placements": ["Median UG salary", "UG intake", "NIRF 2025"], "fees": ["Fees", "Hostel"],
              "hostel": ["Hostel", "Fees"], "rankings": ["NIRF 2025"], "academics": ["Programmes", "UG intake"]}
DEFAULT_ROWS = ["NIRF 2025", "Median UG salary", "Fees", "Programmes", "UG intake"]


def _rows_for(topics: list[str]) -> list[str]:
    rows = []
    for t in topics:
        rows += TOPIC_ROWS.get(t, [])
    return list(dict.fromkeys(rows)) or DEFAULT_ROWS


def _table(db, college_ids, row_names, cites, branch_query: str | None = None, branch_terms: str | None = None):
    names = {c.id: c.name for c in db.query(College).filter(College.id.in_(college_ids)).all()}
    table = {"columns": [{"id": cid, "name": names.get(cid, cid)} for cid in college_ids], "rows": []}
    facts = {cid: facts_for(db, cid) for cid in college_ids}
    if branch_query:
        terms = branch_terms or branch_query
        table["rows"].append({"aspect": "Branch evidence", "cells": [_snippet_cell(cites, cid, branch_query, min_rel=0.5, terms=terms) for cid in college_ids]})
    for row in row_names:
        table["rows"].append({"aspect": row, "cells": [ROWS[row](cites, facts[cid], cid) for cid in college_ids]})
    loc = {c.id: f"{c.city}, {c.state}" for c in db.query(College).filter(College.id.in_(college_ids)).all()}
    table["rows"].append({"aspect": "Location", "cells": [{"text": loc.get(cid, NOT_IN_SOURCES), "cite": []} for cid in college_ids]})
    return table


def _summary(table) -> str:
    cols = [c["name"] for c in table["columns"]]
    short = {c["name"]: re.sub(r"\s*\(.*?\)", "", c["name"]) for c in table["columns"]}
    wins: dict[str, list[str]] = {c: [] for c in cols}
    for row in table["rows"]:
        nums = [(c.get("num"), col) for c, col in zip(row["cells"], cols) if c.get("num") is not None]
        if len(nums) < 2:
            continue
        if row["aspect"] == "NIRF 2025":
            best = min(nums)
            others = ", ".join(f"{short[col]} {cell['text'].split(',')[0].lower()}" for cell, col in zip(row["cells"], cols) if col != best[1] and cell.get("num") is not None)
            if best[0] < max(n for n, _ in nums):
                wins[best[1]].append(f"NIRF position ({[c for c, col in zip(row['cells'], cols) if col == best[1]][0]['text'].split(',')[0]} vs {others})")
        elif row["aspect"] == "Median UG salary":
            best = max(nums)
            if best[0] > min(n for n, _ in nums):
                wins[best[1]].append(f"median UG salary ({_lakh(best[0])} vs " + ", ".join(_lakh(n) for n, col in nums if col != best[1]) + ")")
    parts = [f"{short[c]} is stronger on {' and '.join(w)}" for c, w in wins.items() if w]
    missing = sorted({row["aspect"] for row in table["rows"] if any(cell["text"] == NOT_IN_SOURCES for cell in row["cells"])})
    text = ("; ".join(parts) + ". ") if parts else "The indexed sources do not give directly comparable figures for these colleges. "
    if missing:
        text += f"Not in sources for every college: {', '.join(missing)}. "
    return text + CAVEAT


def _base(question, qu, started):
    return {"question": question, "intent": qu["type"].lower(), "college_ids": qu["colleges"], "query_type": qu["type"],
            "understanding": {k: qu.get(k) for k in ("type", "colleges", "topics", "subqueries", "source", "location", "branch")},
            "provider": "none", "model": None, "mode": "structured",
            "latency": {"retrieval_ms": 0.0, "generation_ms": 0.0, "total_ms": 0.0}}


def _finish(result, started):
    result["latency"]["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result


def compare(db, question, qu, started):
    cites = Citations(db)
    table = _table(db, qu["colleges"][:3], _rows_for(qu["topics"]), cites)
    has_any = any(cell["cite"] for row in table["rows"] for cell in row["cells"])
    return _finish({**_base(question, qu, started), "answer": _summary(table), "table": table, "sources": cites.views,
                    "grounded": has_any, "answer_label": "Cited comparison · indexed sources"}, started)


def recommend(db, question, qu, started):
    loc = (qu.get("location") or "").lower()
    candidates = []
    for c in db.query(College).filter(College.id.in_(PILOT)).all():
        if loc and loc not in f"{c.city} {c.state} {c.category}".lower() and not (loc == "ncr" and "ncr" in c.category.lower()):
            continue
        candidates.append(c.id)
    branch = qu.get("branch")
    branch_query = f"B.Tech {branch} engineering" if branch else None
    cites = Citations(db)
    if branch_query:  # keep only colleges whose sources mention the branch
        candidates = [cid for cid in candidates if retrieve(branch_query, [cid], min_relevance=0.5)["hits"]]

    def key(cid):
        f = facts_for(db, cid)
        rank = (f.get("nirf_rank") or f.get("nirf_band"))
        sal = f.get("median_salary_ug")
        return (rank.num if rank else 999, -(sal.num if sal else 0))
    ranked = sorted(candidates, key=key)[:5] if qu["type"] == "RECOMMEND" else candidates[:6]
    if not ranked:
        return None
    abbrev = {"electronics and communication": "ece", "computer science": "cse", "information technology": "it"}.get(branch or "", "")
    table = _table(db, ranked, ["NIRF 2025", "Median UG salary"], cites, branch_query, f"{branch or ''} {abbrev}".strip())
    names = [c["name"] for c in table["columns"]]
    where = f" in {qu['location'].title()}" if qu.get("location") else ""
    what = f" that list {branch} in their sources" if branch else ""
    if qu["type"] == "RECOMMEND":
        text = (f"Among the indexed colleges{where}{what}, ordered by NIRF 2025 position and then median UG salary: "
                + ", ".join(f"{i + 1}. {n}" for i, n in enumerate(names)) + ". " + CAVEAT)
    else:
        text = f"Indexed colleges{where}{what}: " + ", ".join(names) + "."
    return _finish({**_base(question, qu, started), "answer": text, "table": table, "sources": cites.views,
                    "grounded": True, "answer_label": "Shortlist from indexed sources · NIRF facts"}, started)


def fact(db, question, qu, registry, started, use_llm=True):
    colleges = qu["colleges"] or None
    merged: dict[str, dict] = {}
    for q in [question] + [s for s in qu["subqueries"] if s.lower() != question.lower()][:4]:
        for h in retrieve(q, colleges, registry)["hits"]:
            cid = h.get("id") or f"{h['metadata']['source_id']}-{h['text'][:20]}"
            if cid not in merged or h["score"] > merged[cid]["score"]:
                merged[cid] = h
    hits = sorted(merged.values(), key=lambda h: -h["score"])[:8]
    result = answer(question, colleges, qu["type"].lower() if qu["type"] != "FACT" else None, db=db, registry=registry,
                    use_llm=use_llm, hits_override=hits)
    result["query_type"] = qu["type"]
    result["understanding"] = {k: qu.get(k) for k in ("type", "colleges", "topics", "subqueries", "source", "location", "branch")}
    return result


def related_facts(db, college_ids: list[str], cites: "Citations") -> str:
    """Structured facts we DO have for these colleges (used when the exact answer is missing)."""
    bits = []
    for cid in college_ids[:2]:
        f = facts_for(db, cid)
        college = db.get(College, cid)
        for field, fmt in (("nirf_rank", lambda x: f"NIRF {x.year} Engineering rank {x.value}"),
                           ("nirf_band", lambda x: f"NIRF {x.year} Engineering rank band {x.value}"),
                           ("median_salary_ug", lambda x: f"median UG salary {_lakh(x.num)} ({x.year} graduates)")):
            if field in f:
                n = cites.cite_source(f[field].source_id, f[field].evidence)
                bits.append(f"{college.name if college else cid}: {fmt(f[field])}" + (f" [S{n}]" if n else ""))
    return ("Related facts in the sources — " + "; ".join(bits) + ".") if bits else ""


def ask(db, question: str, registry=None, use_llm: bool = True) -> dict:
    started = time.perf_counter()
    qu = understand(question, registry, use_llm=use_llm)
    if qu["type"] == "COMPARE":
        return compare(db, question, qu, started)
    if qu["type"] in ("RECOMMEND", "LIST"):
        out = recommend(db, question, qu, started)
        if out:
            return out
    return fact(db, question, qu, registry, started, use_llm=use_llm)
