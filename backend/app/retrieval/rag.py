"""Source-grounded question answering.

Grounding rule: an answer is produced ONLY from retrieved, indexed chunks. If
retrieval finds no sufficiently relevant context, the LLM is never called and
the response is "Not available in indexed sources."
"""
import re
import time

from ..ai import groq_client, llm  # noqa: F401  (groq_client kept for backward-compatible imports)
from ..change_detection.diff import passages
from ..config import MIN_RELEVANCE
from ..services.vector_store import query, tokenize
from ..verification.rules import classify_source, freshness
from .entities import classify_intent, detect_colleges, strip_phrases

NOT_AVAILABLE = "Not available in indexed sources."
MAX_CONTEXT_CHUNKS = 6

GROUNDED_PROMPT = """You are CampusAtlas, an expert, friendly counsellor for Indian engineering colleges.
Answer ONLY from the numbered SOURCES below and cite every fact inline as [S1], [S2]. Never use outside
knowledge and never invent cutoffs, fees, placement figures, dates or rankings.
- Start with the direct answer in the first sentence, then the key numbers, then one practical tip if useful.
- For opinion questions ("is X good", "should I join X", "X or Y") do NOT refuse: give a balanced,
  evidence-based assessment from the cited facts (NIRF rank, median salary, intake, fees, programmes)
  and name what else the student should weigh.
- FIELD REALITY: when the question touches placements, packages, ROI, "is X good" or "X vs Y", lead with the
  official NIRF reality numbers if present (share of graduates actually placed, share with neither a job nor
  higher studies, median salary and its trend) and, if the college advertises a "highest package", say plainly
  that it is one student's offer while the median is what a typical placed student gets.
- If the sources answer only part of the question, answer that part and say exactly which part is missing.
- If the sources contain closely related information (e.g. a dual-degree programme when asked about B.Tech),
  state precisely what they say and what is missing.
- Only if nothing relevant is present, reply exactly: "Not available in indexed sources."
Reply in the same language and style as the question (English or Hinglish). Max 180 words. Plain text;
short "- " bullet lines are fine; no markdown headings, tables or bold. Never reveal reasoning."""


def search_text_for(question: str, college_ids=None, registry=None) -> tuple[list[str], str]:
    """(college scope, text actually searched) for a question."""
    detected, phrases = detect_colleges(question, registry)
    scope = list(college_ids or []) or detected
    search_text = question
    if scope and phrases:
        stripped = strip_phrases(question, phrases)
        if tokenize(stripped):  # keep only content terms once the college filter is applied
            search_text = stripped
    return scope, search_text


def retrieve(question: str, college_ids: list[str] | None = None, registry=None, n: int = 8,
             min_relevance: float | None = None) -> dict:
    """Detect colleges, build the search text and return relevant hits."""
    scope, search_text = search_text_for(question, college_ids, registry)
    hits = query(search_text, scope or None, n=n)
    floor = MIN_RELEVANCE if min_relevance is None else min_relevance
    relevant = [h for h in hits if h.get("coverage", h["score"]) >= floor]
    return {"hits": relevant, "college_ids": scope, "search_text": search_text}


def _source_view(meta: dict, db, index: int, snippet: str, score: float) -> dict:
    from ..models.models import College, Source  # local import avoids cycles

    view = {key: meta.get(key) for key in ("source_id", "source_name", "source_url", "authority_level",
                                            "source_type", "college_id", "document_title")}
    view.update(index=index, snippet=snippet[:280], score=round(score, 3), is_demo=bool(meta.get("is_demo")))
    official_domain, last_checked, last_changed = None, None, None
    if db is not None:
        src = db.get(Source, meta.get("source_id"))
        if src is not None:
            last_checked, last_changed = src.last_checked, src.last_changed
            college = db.get(College, src.college_id) if src.college_id else None
            official_domain = college.official_domain if college else None
    view["verification"] = classify_source(meta.get("source_url", ""), official_domain)
    view["last_checked"], view["last_changed"] = last_checked, last_changed
    view["freshness"] = freshness(last_checked, last_changed)
    return view


def best_snippet(text: str, terms_text: str, max_sentences: int = 2) -> str:
    """Return the sentence(s) of `text` that best match `terms_text` (original order)."""
    terms = set(tokenize(terms_text, expand=True))
    sentences = [x for x in passages(text) if 20 <= len(x) <= 600]
    ranked = sorted(range(len(sentences)), key=lambda i: -len(terms & set(tokenize(sentences[i]))))
    chosen = sorted(i for i in ranked[:max_sentences] if terms & set(tokenize(sentences[i])))
    if chosen:
        return " ".join(sentences[i] for i in chosen)
    # No clean sentence matched (menu-heavy page): show a window around the first matching term.
    lower = text.lower()
    hits = [m.start() for t in terms if len(t) > 2 for m in [re.search(r"\b" + re.escape(t), lower)] if m]
    if not hits:
        return text[:300]
    start = max(0, min(hits) - 100)
    start = lower.rfind(" ", 0, start) + 1 if start else 0
    return ("…" if start else "") + text[start:start + 320].rstrip() + "…"


def _extractive(question: str, hits: list[dict], labels: dict[int, int]) -> str:
    terms = set(tokenize(question, expand=True))
    scored = []
    for rank, hit in enumerate(hits):
        for pos, sentence in enumerate(passages(hit["text"])):
            overlap = len(terms & set(tokenize(sentence)))
            if overlap and 25 <= len(sentence) <= 600:
                scored.append((overlap, -rank, -pos, sentence, labels[hit["metadata"]["source_id"]]))
    if not scored:  # general question: lead with the best chunk
        best = hits[0]
        return f"{best['text'][:420].rstrip()}… [S{labels[best['metadata']['source_id']]}]"
    chosen, seen = [], set()
    for _, _, _, sentence, label in sorted(scored, reverse=True):
        key = sentence.lower()
        if key not in seen:
            seen.add(key)
            chosen.append(f"{sentence} [S{label}]")
        if len(chosen) == 4:
            break
    return " ".join(chosen)


def answer(question: str, college_ids=None, intent: str | None = "general", db=None, registry=None,
           use_llm: bool = True, hits_override: list | None = None) -> dict:
    started = time.perf_counter()
    question = re.sub(r"\s+", " ", question or "").strip()[:500]
    found = retrieve(question, college_ids, registry)
    if hits_override is not None:  # sub-query retrieval already merged by the QA engine
        found["hits"] = hits_override
    hits, scope = found["hits"], found["college_ids"]
    retrieval_ms = (time.perf_counter() - started) * 1000
    detected_intent = classify_intent(question, scope) if intent in (None, "", "general") else intent
    base = {"intent": detected_intent, "college_ids": scope, "question": question}

    if not hits:  # grounding rule: no context -> no generation
        return {**base, "answer": NOT_AVAILABLE, "sources": [], "mode": "none", "grounded": False,
                "provider": "none", "model": None,
                "latency": {"retrieval_ms": round(retrieval_ms, 1), "generation_ms": 0.0,
                            "total_ms": round((time.perf_counter() - started) * 1000, 1)}}

    context = hits[:MAX_CONTEXT_CHUNKS]
    labels, sources = {}, []
    for hit in context:
        sid = hit["metadata"]["source_id"]
        if sid not in labels:
            labels[sid] = len(labels) + 1
            sources.append(_source_view(hit["metadata"], db, labels[sid], hit["text"], hit["score"]))

    gen_started = time.perf_counter()
    mode, notice, model = "extractive", None, None
    text = None
    if use_llm and llm.is_configured():
        blocks = "\n\n".join(f"[S{labels[h['metadata']['source_id']]}] {h['metadata'].get('source_name')}\n{h['text']}" for h in context)
        try:
            text, mode, failed = llm.generate(GROUNDED_PROMPT, f"QUESTION: {question}\n\nSOURCES:\n{blocks}", max_tokens=900,
                                                  prefer=llm.task_provider("answer"))
            model = llm.active_model(mode)
            if failed:
                notice = f"Primary AI provider unavailable ({failed[0]}); answered by {mode.title()} from the same sources."
        except llm.LLMUnavailable as exc:
            notice = f"AI model unavailable ({exc}); showing an extractive answer from the same sources."
    if text is None:
        text = "Relevant passages from the indexed sources: " + _extractive(found["search_text"], context, labels)
    generation_ms = (time.perf_counter() - gen_started) * 1000
    grounded = NOT_AVAILABLE.lower().rstrip(".") not in text.lower()
    strong = [h for h in context if h.get("coverage", 0) >= 0.5]
    partial = not grounded or bool(re.search(r"\b(not (stated|mentioned|provided|available|specified)|do(es)? not (state|mention|provide|specify|contain|give)|don't (state|mention|provide)|missing)\b", text, re.I))
    if not grounded and strong:  # partial evidence: never a bare "not available" when relevant text exists
        text = ("The sources don't state this directly. Most relevant passages: "
                + _extractive(found["search_text"], strong, labels))
        grounded = True
        notice = (notice + " " if notice else "") + "Partial evidence: the exact figure was not found in the cited sources."
    result = {**base, "answer": text, "sources": sources if grounded else [], "mode": mode, "grounded": grounded,
              "provider": mode if mode in ("gemini", "groq") else "demo", "model": model,
              "latency": {"retrieval_ms": round(retrieval_ms, 1), "generation_ms": round(generation_ms, 1),
                          "total_ms": round((time.perf_counter() - started) * 1000, 1)}}
    if partial:
        result["partial"] = True  # lets the API add a cited web search for the missing part
    if notice:
        result["notice"] = notice
    if any(s["is_demo"] for s in sources):
        result["demo_notice"] = "Some cited material is labelled DEMO DATA (first-defence demonstration content)."
    return result
