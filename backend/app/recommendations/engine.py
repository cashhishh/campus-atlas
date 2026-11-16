"""Explainable preference scoring and evidence-aware comparison.

Every point added to a score comes with a human-readable reason. Claims about
programmes are only credited when an indexed source actually mentions them.
"""
from typing import Callable

WEIGHTS = {"branch": 30, "location": 20, "type": 15, "hostel": 10, "placement": 5}
MAX_SCORE = sum(WEIGHTS.values())

COMPARE_TOPICS = {
    "Programmes": "b tech programmes courses intake branches",
    "Admissions": "admission eligibility counselling jee cet jac",
    "Fees": "fee fees tuition",
    "Placements": "placement placements recruiters training",
    "Campus & facilities": "campus hostel library laboratories facilities",
    "Rankings & accreditation": "nirf rank ranking naac nba accreditation",
}


def _is_public(category: str) -> bool:
    return category not in ("Private",)


def recommend(colleges: list[dict], p: dict, evidence: Callable[[str, str], bool] | None = None) -> list[dict]:
    branch = (p.get("branch") or "").strip().lower()
    loc = (p.get("location") or "").strip().lower()
    pref = (p.get("type") or "").strip()
    out = []
    for c in colleges:
        score, why = 0, []
        if branch:
            if evidence and evidence(c["id"], branch):
                score += WEIGHTS["branch"]
                why.append(f"Indexed sources mention “{branch}”")
            else:
                why.append("Program fit needs confirmation from indexed academic sources")
        if loc and (loc in (c.get("state") or "").lower() or loc in (c.get("city") or "").lower()):
            score += WEIGHTS["location"]
            why.append("Located in your preferred area")
        if pref and (pref.lower() in (c.get("category") or "").lower()
                     or (pref == "Government" and _is_public(c.get("category") or ""))):
            score += WEIGHTS["type"]
            why.append("Matches your institution preference")
        if p.get("hostel"):
            score += WEIGHTS["hostel"]
            why.append("Hostel preference recorded; availability requires source verification")
        if p.get("placement"):
            score += WEIGHTS["placement"]
            why.append("Placement importance included in scoring")
        out.append({"college": c, "score": min(score, MAX_SCORE), "max_score": MAX_SCORE,
                    "why": why or ["A registry match; more sources will improve recommendations"]})
    return sorted(out, key=lambda x: (-x["score"], x["college"]["name"]))[:8]


def compare_evidence(college_ids: list[str], retrieve_fn, topics: dict[str, str] | None = None) -> dict:
    """For each college x topic, return the best indexed evidence or 'Not available'.

    `retrieve_fn(text, college_id)` returns ranked hits (see retrieval.rag.retrieve).
    """
    from ..retrieval.rag import NOT_AVAILABLE, best_snippet

    topics = topics or COMPARE_TOPICS
    table = {}
    for cid in college_ids:
        row = {}
        for topic, terms in topics.items():
            hits = retrieve_fn(terms, cid)
            if hits:
                h = hits[0]
                row[topic] = {"available": True, "text": best_snippet(h["text"], terms)[:420], "score": h["score"],
                              "source_id": h["metadata"]["source_id"], "source_name": h["metadata"].get("source_name"),
                              "source_url": h["metadata"].get("source_url"), "is_demo": bool(h["metadata"].get("is_demo"))}
            else:
                row[topic] = {"available": False, "text": NOT_AVAILABLE}
        table[cid] = row
    return {"topics": list(topics), "colleges": table}
