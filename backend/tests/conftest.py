"""Test configuration.

Every test runs against a throw-away SQLite DB and chunk store, with the
scheduler disabled and Groq disabled (deterministic, offline). Each test is
tagged with @pytest.mark.meta(id, module, description, expected) and records
what actually happened via the `actual` fixture; the session writes
docs/test_results.md from that data.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="campusatlas-tests-"))
os.environ.update({
    "DATABASE_URL": f"sqlite:///{(_TMP / 'test.db').as_posix()}",
    "CAMPUSATLAS_DATA_DIR": str(_TMP / "data"),
    "MONITOR_ENABLED": "false",
    "GROQ_API_KEY": "",
    "GEMINI_API_KEY": "",
    "LIVE_FETCH_ENABLED": "false",
    "LLM_PROVIDER": "gemini",
    "VECTOR_DRIVER": "json",
    "STALE_AFTER_HOURS": "72",
    "SEED_RESTORE": "false",
    "ANSWER_PROVIDER": "gemini",
    "UNDERSTAND_PROVIDER": "gemini",
    "SUMMARY_PROVIDER": "gemini",
    "WEB_FALLBACK": "false",
})
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402
import pytest  # noqa: E402

RESULTS: list[dict] = []
DOCS = Path(__file__).resolve().parents[2] / "docs"


def pytest_configure(config):
    config.addinivalue_line("markers", "meta(id, module, description, expected): test-report metadata")


@pytest.fixture
def actual(request):
    def record(text):
        request.node.user_properties.append(("actual", str(text)))
    return record


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" or (rep.when == "setup" and rep.failed):
        mark = item.get_closest_marker("meta")
        tid, module, desc, expected = mark.args if mark else (item.name, "-", item.name, "-")
        actuals = [v for k, v in item.user_properties if k == "actual"]
        if rep.failed:
            msg = str(rep.longrepr).strip().splitlines()[-1][:160] if rep.longrepr else "failed"
            actual_text = msg
        else:
            actual_text = "; ".join(actuals) or "As expected"
        RESULTS.append({"id": tid, "module": module, "description": desc, "expected": expected,
                        "actual": actual_text, "result": "Pass" if rep.passed else "Fail",
                        "duration_ms": round(rep.duration * 1000, 1)})


def pytest_sessionfinish(session, exitstatus):
    if not RESULTS or os.getenv("CAMPUSATLAS_NO_REPORT"):
        return
    DOCS.mkdir(exist_ok=True)
    rows = sorted(RESULTS, key=lambda r: r["id"])
    passed = sum(r["result"] == "Pass" for r in rows)
    esc = lambda s: str(s).replace("|", "\\|").replace("\n", " ")
    lines = [
        "# CampusAtlas — Test Results", "",
        f"Generated automatically by `pytest` on {time.strftime('%Y-%m-%d %H:%M')} (offline: temporary DB, no network, no Groq).", "",
        f"**{passed} / {len(rows)} tests passed.**", "",
        "| Test ID | Module | Description | Expected | Actual | Pass/Fail |",
        "|---|---|---|---|---|---|",
    ]
    lines += [f"| {r['id']} | {r['module']} | {esc(r['description'])} | {esc(r['expected'])} | {esc(r['actual'])} | {r['result']} |" for r in rows]
    perf = DOCS / "_performance.md"
    if perf.exists():
        lines += ["", perf.read_text(encoding="utf-8")]
    (DOCS / "test_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ----------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(client):
    from app.database import SessionLocal

    session = SessionLocal()
    yield session
    session.close()


class FakeResponse:
    def __init__(self, body: bytes, content_type: str):
        self.content = body
        self.headers = {"content-type": content_type}
        self.text = body.decode("utf-8", errors="ignore")


def make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=10)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def fake_web(monkeypatch):
    """Serve fake pages: dict url -> (bytes, content-type). Mutate it to simulate changes."""
    from app.ingestion import pipeline

    pages: dict[str, tuple[bytes, str]] = {}

    def fake_get(url, timeout=25.0):
        if url not in pages:
            raise RuntimeError(f"404 for {url}")
        return FakeResponse(*pages[url])

    monkeypatch.setattr(pipeline, "http_get", fake_get)
    return pages


@pytest.fixture
def new_source(db):
    from app.models.models import Source

    counter = {"n": 0}

    def make(url, college_id="mait", name=None, source_type="OFFICIAL_COLLEGE"):
        counter["n"] += 1
        s = Source(college_id=college_id, source_name=name or f"Test source {counter['n']}", source_url=url,
                   source_type=source_type, authority_level="VERY_HIGH", status="ACTIVE", is_demo=False)
        db.add(s)
        db.commit()
        db.refresh(s)
        return s

    return make
