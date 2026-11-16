"""Gemini primary / Groq fallback / demo provider chain (all mocked, no network)."""
import pytest
from google.genai import errors

from app.ai import gemini_client, groq_client, llm
from app.change_detection.diff import compute_diff, summarize_change
from app.retrieval import rag
from app.services import vector_store


@pytest.fixture
def mait_corpus():
    vector_store.replace_source_chunks(9101, [{
        "id": "9101-t-0", "text": "MAIT offers B.Tech in Electronics and Communication Engineering with an intake of 120.",
        "metadata": {"college_id": "mait", "source_id": 9101, "source_url": "https://mait.ac.in/courses",
                     "source_name": "MAIT courses", "source_type": "OFFICIAL_COLLEGE", "authority_level": "VERY_HIGH",
                     "document_title": "Courses", "is_demo": False}}])
    yield
    vector_store.delete_source(9101)


def _configure(monkeypatch, gemini: bool, groq: bool):
    monkeypatch.setattr(gemini_client, "is_configured", lambda: gemini)
    monkeypatch.setattr(groq_client, "is_configured", lambda: groq)


@pytest.mark.meta("T49", "AI providers", "Gemini (primary) answers when configured; Groq is not called", "provider=gemini, [S1] citation kept, 0 Groq calls")
def test_gemini_success(mait_corpus, monkeypatch, actual):
    _configure(monkeypatch, True, True)
    prompts, groq_calls = [], []
    monkeypatch.setattr(gemini_client, "chat", lambda system, user, **k: prompts.append((system, user)) or "Yes, MAIT offers ECE [S1].")
    monkeypatch.setattr(groq_client, "chat", lambda *a, **k: groq_calls.append(a) or "groq")
    r = rag.answer("Does MAIT offer ECE?")
    assert r["provider"] == "gemini" and r["mode"] == "gemini" and "[S1]" in r["answer"] and groq_calls == []
    assert prompts[0][0] == rag.GROUNDED_PROMPT and "SOURCES:\n[S1]" in prompts[0][1]  # same strict grounding prompt
    actual(f"provider={r['provider']}, groq_calls={len(groq_calls)}")


@pytest.mark.meta("T50", "AI providers", "Gemini failure (429) falls back to Groq", "provider=groq with a notice naming the Gemini failure")
def test_gemini_failure_falls_back_to_groq(mait_corpus, monkeypatch, actual):
    _configure(monkeypatch, True, True)

    def fail(*a, **k):
        raise gemini_client.GeminiUnavailable("Gemini returned HTTP 429")
    monkeypatch.setattr(gemini_client, "chat", fail)
    monkeypatch.setattr(groq_client, "chat", lambda *a, **k: "MAIT offers ECE [S1].")
    r = rag.answer("Does MAIT offer ECE?")
    assert r["provider"] == "groq" and r["grounded"] and "429" in r["notice"]
    actual(f"provider={r['provider']}; notice mentions 429")


@pytest.mark.meta("T51", "AI providers", "No API keys -> grounded demo (extractive) response", "provider=demo, mode=extractive, cites [S1], no notice")
def test_no_keys_demo_response(mait_corpus, monkeypatch, actual):
    _configure(monkeypatch, False, False)
    r = rag.answer("Does MAIT offer ECE?")
    assert r["provider"] == "demo" and r["mode"] == "extractive" and "[S1]" in r["answer"] and "notice" not in r
    actual(f"provider={r['provider']}, mode={r['mode']}")


@pytest.mark.meta("T52", "AI providers", "Both providers fail -> demo response from the same sources", "provider=demo with notice; still grounded")
def test_both_fail_demo(mait_corpus, monkeypatch, actual):
    _configure(monkeypatch, True, True)

    def g(*a, **k):
        raise gemini_client.GeminiUnavailable("timeout")

    def q(*a, **k):
        raise groq_client.GroqUnavailable("HTTP 503")
    monkeypatch.setattr(gemini_client, "chat", g)
    monkeypatch.setattr(groq_client, "chat", q)
    r = rag.answer("Does MAIT offer ECE?")
    assert r["provider"] == "demo" and r["grounded"] and "notice" in r and "[S1]" in r["answer"]
    actual("demo fallback with notice")


@pytest.mark.meta("T53", "AI providers", "LLM_PROVIDER=groq makes Groq primary", "order = [groq, gemini]")
def test_provider_order(monkeypatch, actual):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    assert llm.provider_order() == ["groq", "gemini"]
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    assert llm.provider_order() == ["gemini", "groq"]
    actual("groq→gemini / gemini→groq")


class _FakeModels:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return type("R", (), {"text": out, "candidates": []})()


@pytest.mark.meta("T54", "AI providers", "Gemini SDK call retries once on 429 and skips a missing model", "404 model skipped, 429 retried, text returned")
def test_gemini_retry_and_model_fallback(monkeypatch, actual):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-missing")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "gemini-good")
    monkeypatch.setenv("GEMINI_RETRY_SECONDS", "0")
    monkeypatch.setattr(gemini_client, "_working_model", None)
    fake = _FakeModels([errors.ClientError(404, {"error": {"message": "model not found", "status": "NOT_FOUND"}}),
                        errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}),
                        "Answer [S1]"])
    monkeypatch.setattr(gemini_client, "_client", lambda timeout: type("C", (), {"models": fake})())
    assert gemini_client.chat("system", "user") == "Answer [S1]"
    assert fake.calls == ["gemini-missing", "gemini-good", "gemini-good"] and gemini_client.active_model() == "gemini-good"
    actual(f"calls={fake.calls}")


@pytest.mark.meta("T55", "AI providers", "Change summaries use the active provider", "summary_mode=gemini when Gemini answers")
def test_change_summary_uses_gemini(monkeypatch, actual):
    _configure(monkeypatch, True, False)
    monkeypatch.setattr(gemini_client, "chat", lambda *a, **k: "A new robotics lab was announced.")
    summary, mode = summarize_change(compute_diff("Old text here.", "Old text here. New robotics lab."), "Notices")
    assert mode == "gemini" and "robotics" in summary
    actual(f"mode={mode}")


@pytest.mark.meta("T56", "API", "POST /api/web-research: friendly 503 without key; official domains first with key", "503 + message; sources sorted Official → others")
def test_web_research_endpoint(client, monkeypatch, actual):
    monkeypatch.setattr(gemini_client, "is_configured", lambda: False)
    r = client.post("/api/web-research", json={"question": "MAIT fees"})
    assert r.status_code == 503 and "Gemini" in r.json()["detail"]
    monkeypatch.setattr(gemini_client, "is_configured", lambda: True)
    monkeypatch.setattr(gemini_client, "web_research", lambda q: {"answer": "MAIT fees vary.", "model": "gemini-x", "sources": [
        {"title": "shiksha.com", "url": "https://r/1", "domain": "shiksha.com"},
        {"title": "mait.ac.in", "url": "https://r/2", "domain": "mait.ac.in"}]})
    d = client.post("/api/web-research", json={"question": "MAIT fees"}).json()
    assert d["provider"] == "gemini" and d["experimental"] and [s["domain"] for s in d["sources"]] == ["mait.ac.in", "shiksha.com"]
    assert d["sources"][0]["verification"]["status"] == "OFFICIAL"
    actual("503 without key; mait.ac.in listed first")
