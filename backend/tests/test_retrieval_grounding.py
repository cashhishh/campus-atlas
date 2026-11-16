import pytest

from app.ai import groq_client
from app.retrieval import rag
from app.retrieval.entities import classify_intent, detect_colleges
from app.services import vector_store
from app.services.vector_store import tokenize


def _chunk(cid, sid, text, i=0):
    return {"id": f"{sid}-t-{i}", "text": text, "metadata": {
        "college_id": cid, "source_id": sid, "source_url": f"https://{cid}.ac.in/", "source_name": f"{cid} page",
        "source_type": "OFFICIAL_COLLEGE", "authority_level": "VERY_HIGH", "document_title": f"{cid} page", "is_demo": False}}


@pytest.fixture
def corpus():
    vector_store.replace_source_chunks(9001, [_chunk("gtbit", 9001, "GTBIT offers B.Tech in Information Technology and Electronics and Communication Engineering.")])
    vector_store.replace_source_chunks(9002, [_chunk("bpit", 9002, "BPIT hostel facility is not provided on campus; students arrange private accommodation.")])
    vector_store.replace_source_chunks(9003, [_chunk("usict", 9003, "The university school offers M.Tech and B.Tech programmes in computer science.")])
    yield
    for sid in (9001, 9002, 9003):
        vector_store.delete_source(sid)


@pytest.mark.meta("T17", "Retrieval", "Tokenizer removes stopwords and expands abbreviations", "'Does MAIT offer ECE?' -> mait, offer, ece, electronic, communication")
def test_tokenize(actual):
    toks = tokenize("Does MAIT offer ECE?", expand=True)
    assert "does" not in toks and {"mait", "ece", "electronic", "communication"} <= set(toks)
    actual(str(toks))


@pytest.mark.meta("T18", "Retrieval", "BM25 ranks the relevant chunk first", "Top hit for 'hostel accommodation' is the BPIT hostel chunk")
def test_query_ranking(corpus, actual):
    hits = vector_store.query("hostel accommodation")
    assert hits and hits[0]["metadata"]["source_id"] == 9002 and hits[0]["coverage"] == 1.0
    actual(f"top={hits[0]['metadata']['college_id']} score={hits[0]['score']}")


@pytest.mark.meta("T19", "Retrieval", "College filter restricts the search space", "Query scoped to gtbit never returns usict chunks")
def test_college_filter(corpus, actual):
    hits = vector_store.query("B.Tech programmes", ["gtbit"])
    assert hits and {h["metadata"]["college_id"] for h in hits} == {"gtbit"}
    actual(f"{len(hits)} hit(s), all gtbit")


@pytest.mark.meta("T20", "Retrieval", "College detection uses aliases with word boundaries", "MAIT/IGDTUW detected; 'IIIT Delhi' is not mistaken for 'IIT Delhi'")
def test_detect_colleges(actual):
    assert detect_colleges("Is MAIT better than igdtuw?")[0] == ["mait", "igdtuw"]
    ids, _ = detect_colleges("Tell me about IIIT Delhi")
    assert "iiit-delhi" in ids and "iit-delhi" not in ids
    actual("aliases + boundaries OK")


@pytest.mark.meta("T21", "Retrieval", "Intent classification", "fees / placements / comparison / rankings recognised")
def test_intent(actual):
    assert classify_intent("What are the fees?", ["mait"]) == "fees"
    assert classify_intent("placement record", ["dtu"]) == "placements"
    assert classify_intent("DTU vs NSUT", ["dtu", "nsut"]) == "comparison"
    assert classify_intent("NIRF rank", ["nsut"]) == "rankings"
    actual("4/4 intents correct")


@pytest.mark.meta("T22", "Grounding rule", "No relevant context -> fixed refusal and the LLM is NEVER called", "'Not available in indexed sources.', grounded=False, 0 sources, 0 LLM calls")
def test_no_context_no_answer(corpus, monkeypatch, actual):
    calls = []
    monkeypatch.setattr(groq_client, "is_configured", lambda: True)
    monkeypatch.setattr(groq_client, "chat", lambda *a, **k: calls.append(a) or "invented")
    r = rag.answer("What is the swimming pool timing at GTBIT?")
    assert r["answer"] == rag.NOT_AVAILABLE and r["grounded"] is False and r["sources"] == [] and r["mode"] == "none"
    assert calls == []
    actual(f"answer='{r['answer']}', llm_calls={len(calls)}")


@pytest.mark.meta("T23", "Grounding rule", "With context, the extractive answer cites its source", "Answer contains [S1]; citation has verification + freshness")
def test_answer_with_citation(corpus, actual):
    r = rag.answer("Does GTBIT offer ECE?", use_llm=False)
    assert r["grounded"] and "[S1]" in r["answer"] and "Electronics and Communication" in r["answer"]
    s = r["sources"][0]
    assert s["source_id"] == 9001 and s["verification"]["status"] == "OFFICIAL" and "state" in s["freshness"]
    actual(f"mode={r['mode']}, cites S1 ({s['verification']['label']})")


@pytest.mark.meta("T24", "Grounding rule", "LLM receives only retrieved context, numbered as sources", "Prompt contains SOURCES block with the chunk; question included")
def test_llm_gets_only_context(corpus, monkeypatch, actual):
    seen = {}
    monkeypatch.setattr(groq_client, "is_configured", lambda: True)

    def fake_chat(system, user, **k):
        seen["system"], seen["user"] = system, user
        return "GTBIT offers ECE [S1]."
    monkeypatch.setattr(groq_client, "chat", fake_chat)
    r = rag.answer("Does GTBIT offer ECE?")
    assert r["mode"] == "groq" and "Answer ONLY from the numbered SOURCES" in seen["system"]
    assert "[S1]" in seen["user"] and "Information Technology" in seen["user"] and "hostel" not in seen["user"]
    actual("prompt = question + 1 retrieved source only")


@pytest.mark.meta("T25", "Grounding rule", "LLM failure falls back to an extractive answer from the same sources", "mode=extractive with notice; still cited")
def test_llm_failure_fallback(corpus, monkeypatch, actual):
    monkeypatch.setattr(groq_client, "is_configured", lambda: True)

    def boom(*a, **k):
        raise groq_client.GroqUnavailable("HTTP 503")
    monkeypatch.setattr(groq_client, "chat", boom)
    r = rag.answer("Does GTBIT offer ECE?")
    assert r["mode"] == "extractive" and "notice" in r and "[S1]" in r["answer"]
    actual("fallback extractive + notice")
