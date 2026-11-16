"""API tests with FastAPI TestClient."""
import pytest

from app.monitoring import scheduler
from conftest import make_pdf

PAGE = b"<html><head><title>Notices</title></head><body><p>Orientation for first year B.Tech students will be held in the auditorium.</p></body></html>"
PAGE2 = PAGE.replace(b"auditorium", b"auditorium and the seminar hall. Students must carry their ID cards")


@pytest.mark.meta("T36", "API", "GET /health reports status, vector driver and scheduler", "200, status=ok")
def test_health(client, actual):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok" and "monitor" in r.json()
    actual(f"200, driver={r.json()['vector_driver']}")


@pytest.mark.meta("T37", "API", "GET /api/colleges lists the registry incl. new pilot colleges", ">= 53 colleges incl. mait, igdtuw, bpit, gtbit")
def test_colleges(client, actual):
    data = client.get("/api/colleges").json()
    ids = {c["id"] for c in data}
    assert len(data) >= 53 and {"mait", "igdtuw", "bpit", "gtbit", "usict"} <= ids
    actual(f"{len(data)} colleges")


@pytest.mark.meta("T38", "API / Scheduler", "POST /api/monitor/run checks sources and logs the run", "Run SUCCESS; 1 checked; run listed in /api/monitor/runs")
def test_monitor_run_endpoint(client, db, fake_web, new_source, actual):
    src = new_source("https://mait.ac.in/api-notices")
    fake_web[src.source_url] = (PAGE, "text/html")
    run = client.post("/api/monitor/run", json={"source_ids": [src.id]}).json()
    assert run["status"] == "SUCCESS" and run["sources_checked"] == 1 and run["changes_found"] == 1 and run["finished_at"]
    assert run["details"][0]["status"] == "CHANGED"
    assert run["id"] in [r["id"] for r in client.get("/api/monitor/runs").json()]
    actual(f"run #{run['id']} {run['status']}, {run['changes_found']} change, {run['duration_ms']} ms")


@pytest.mark.meta("T39", "API / Scheduler", "A second run detects an update and links the event to the run", "CONTENT_UPDATED event with monitor_run_id; feed shows summary")
def test_monitor_detects_update(client, db, fake_web, new_source, actual):
    src = new_source("https://mait.ac.in/api-notices-2")
    fake_web[src.source_url] = (PAGE, "text/html")
    client.post("/api/monitor/run", json={"source_ids": [src.id]})
    fake_web[src.source_url] = (PAGE2, "text/html")
    run = client.post("/api/monitor/run", json={"source_ids": [src.id]}).json()
    feed = client.get("/api/updates", params={"change_type": "CONTENT_UPDATED"}).json()
    ev = next(u for u in feed if u["source_id"] == src.id)
    assert run["changes_found"] == 1 and ev["monitor_run_id"] == run["id"] and "seminar hall" in ev["summary"]
    detail = client.get(f"/api/updates/{ev['id']}").json()
    assert "+" in detail["diff"] and detail["verification"]["status"] == "OFFICIAL"
    actual(f"event #{ev['id']} linked to run #{run['id']}")


@pytest.mark.meta("T40", "API / Scheduler", "Failed source in a run -> run PARTIAL, error counted, source marked missing", "status PARTIAL, errors=1, source FETCH_FAILED")
def test_monitor_partial_failure(client, db, fake_web, new_source, actual):
    ok = new_source("https://mait.ac.in/api-ok")
    bad = new_source("https://mait.ac.in/api-missing")
    fake_web[ok.source_url] = (make_pdf("Academic calendar for the odd semester including examination schedule and holidays."), "application/pdf")
    run = client.post("/api/monitor/run", json={"source_ids": [ok.id, bad.id]}).json()
    status = {d["source_id"]: d["status"] for d in run["details"]}
    assert run["status"] == "PARTIAL" and run["errors"] == 1 and status[bad.id] == "ERROR"
    assert client.get(f"/api/sources/{bad.id}").json()["status"] == "FETCH_FAILED"
    actual(f"{run['status']}, errors={run['errors']}")


@pytest.mark.meta("T41", "API / Scheduler", "Concurrent runs are prevented", "409 while a run holds the lock")
def test_monitor_lock(client, actual):
    scheduler._run_lock.acquire()
    try:
        r = client.post("/api/monitor/run")
    finally:
        scheduler._run_lock.release()
    assert r.status_code == 409
    actual("409 Conflict")


@pytest.mark.meta("T42", "API / Scheduler", "Scheduler job registers with the configured interval", "Job present with interval; status reports next_run_at")
def test_scheduler_registers_job(actual, monkeypatch):
    monkeypatch.setattr(scheduler.config, "MONITOR_ENABLED", True)
    monkeypatch.setattr(scheduler.config, "MONITOR_INTERVAL_MINUTES", 15)
    scheduler.start_scheduler()
    try:
        st = scheduler.scheduler_status()
        assert st["running"] and st["interval_minutes"] == 15 and st["next_run_at"] is not None
    finally:
        scheduler.stop_scheduler()
    actual(f"next_run_at set, interval=15 min")


@pytest.mark.meta("T43", "API", "POST /api/ask: validation, refusal and query logging", "422 for empty; unknown topic refused; query appears in analytics")
def test_ask_and_logging(client, actual):
    assert client.post("/api/ask", json={"query": "  "}).status_code == 422
    r = client.post("/api/ask", json={"query": "What is the helipad size at NSUT?"}).json()
    assert r["answer"] == "Not available in indexed sources." and r["grounded"] is False
    tops = [q["query"] for q in client.get("/api/analytics").json()["top_queries"]]
    assert "what is the helipad size at nsut" in tops
    actual("422, refusal, logged")


@pytest.mark.meta("T44", "API", "GET /api/sources exposes verification, freshness and DEMO label", "Every source has verification.status and freshness.state")
def test_sources_enriched(client, actual):
    data = client.get("/api/sources").json()
    assert data and all(s["verification"]["status"] in {"OFFICIAL", "THIRD_PARTY", "UNVERIFIED"} for s in data)
    assert all(s["freshness"]["state"] in {"FRESH", "STALE", "NEVER_CHECKED"} for s in data)
    assert any(s["is_demo"] for s in data)
    actual(f"{len(data)} sources enriched")


@pytest.mark.meta("T45", "API", "GET /api/analytics returns dashboard aggregates", "totals, timeline (14 days), breakdowns, top_queries")
def test_analytics(client, actual):
    a = client.get("/api/analytics").json()
    assert {"totals", "timeline", "verification_breakdown", "authority_breakdown", "top_queries", "chunks_by_college"} <= set(a)
    assert len(a["timeline"]) == 14 and a["totals"]["colleges"] >= 53
    actual(f"{a['totals']['sources']} sources, {a['totals']['change_events']} change events")


@pytest.mark.meta("T46", "API", "Input validation on sources and compare", "Bad URL -> 422; unknown colleges -> 422")
def test_validation(client, actual):
    assert client.post("/api/sources", json={"college_id": "mait", "source_name": "x", "source_url": "ftp://x"}).status_code == 422
    assert client.post("/api/compare/evidence", json={"college_ids": ["nope"]}).status_code == 422
    actual("422, 422")


@pytest.mark.meta("T47", "API", "POST /api/compare/evidence returns a topic x college table", "Topics listed; unavailable cells say 'Not available in indexed sources.'")
def test_compare_evidence_api(client, actual):
    data = client.post("/api/compare/evidence", json={"college_ids": ["mait", "igdtuw"]}).json()
    assert "Fees" in data["topics"] and set(data["colleges"]) == {"mait", "igdtuw"}
    cells = [c for row in data["colleges"].values() for c in row.values()]
    assert all(c["available"] or c["text"] == "Not available in indexed sources." for c in cells)
    actual(f"{sum(c['available'] for c in cells)}/{len(cells)} cells with evidence")
