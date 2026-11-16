import pytest

from app.change_detection.diff import compute_diff, deterministic_summary
from app.ingestion.pipeline import content_hash, ingest
from app.models.models import ContentVersion, UpdateEvent
from app.services import vector_store

V1 = b"<html><body><p>Admissions for B.Tech are through IPU CET counselling.</p><p>The library opens at 9 am.</p></body></html>"
V2 = b"<html><body><p>Admissions for B.Tech are through IPU CET counselling.</p><p>The library opens at 8 am on weekdays.</p><p>A new robotics lab was inaugurated.</p></body></html>"


@pytest.mark.meta("T11", "Change detection", "Re-checking identical content creates no change event", "changed=False; still 1 update event")
def test_same_content_no_event(db, fake_web, new_source, actual):
    src = new_source("https://mait.ac.in/notices-same")
    fake_web[src.source_url] = (V1, "text/html")
    ingest(db, src.id)
    second = ingest(db, src.id)
    assert second["changed"] is False
    assert db.query(UpdateEvent).filter_by(source_id=src.id).count() == 1
    actual("changed=False, 1 event")


@pytest.mark.meta("T12", "Change detection", "Changed content: new hash -> CONTENT_UPDATED with stored diff and summary", "Version 2, diff has '+' lines, deterministic summary lists additions")
def test_changed_content_creates_update(db, fake_web, new_source, actual):
    src = new_source("https://mait.ac.in/notices-change")
    fake_web[src.source_url] = (V1, "text/html")
    first = ingest(db, src.id)
    old_hash = db.get(type(src), src.id).content_hash
    fake_web[src.source_url] = (V2, "text/html")
    second = ingest(db, src.id)
    event = db.get(UpdateEvent, second["update_event_id"])
    assert first["change_type"] == "NEW_SOURCE_CONTENT" and second["change_type"] == "CONTENT_UPDATED"
    assert event.old_hash == old_hash and event.new_hash != old_hash
    assert "+A new robotics lab was inaugurated." in event.diff
    assert event.summary_mode == "deterministic" and "robotics lab" in event.summary
    assert db.query(ContentVersion).filter_by(source_id=src.id).count() == 2
    actual(f"{event.change_type}, +{event.added_count}/-{event.removed_count} passages")


@pytest.mark.meta("T13", "Change detection", "Hash ignores whitespace-only differences", "Identical SHA-256 for reformatted text")
def test_hash_normalises_whitespace(actual):
    assert content_hash("Fees  are\n listed  ") == content_hash("Fees are listed")
    assert content_hash("Fees are listed") != content_hash("Fees are updated")
    actual("equal for whitespace, different for words")


@pytest.mark.meta("T14", "Change detection", "compute_diff separates added and removed passages", "1 added, 1 removed, similarity < 1")
def test_compute_diff(actual):
    d = compute_diff("Alpha one. Beta two. Gamma three.", "Alpha one. Beta TWO changed. Gamma three.")
    assert d["added"] == ["Beta TWO changed."] and d["removed"] == ["Beta two."] and d["similarity"] < 1
    assert "1 passage(s) added and 1 removed" in deterministic_summary(d, "X")
    actual(f"added={d['added']}, removed={d['removed']}")


@pytest.mark.meta("T15", "Change detection", "Old chunks are replaced on update (no stale text retrievable)", "Only new-version chunks remain for the source")
def test_stale_chunks_replaced(db, fake_web, new_source, actual):
    src = new_source("https://mait.ac.in/notices-replace")
    fake_web[src.source_url] = (V1, "text/html")
    ingest(db, src.id)
    fake_web[src.source_url] = (V2, "text/html")
    ingest(db, src.id)
    texts = " ".join(c["text"] for c in vector_store.all_chunks() if c["metadata"]["source_id"] == src.id)
    versions = {c["metadata"]["version_no"] for c in vector_store.all_chunks() if c["metadata"]["source_id"] == src.id}
    assert "9 am" not in texts and "8 am" in texts and versions == {2}
    actual(f"versions in store: {sorted(versions)}")


@pytest.mark.meta("T16", "Change detection", "Change simulation is limited to DEMO DATA sources", "400 for a real source; CONTENT_UPDATED for a demo source")
def test_simulate_change_only_demo(client, db, new_source, actual):
    real = new_source("https://mait.ac.in/real-source")
    assert client.post(f"/api/demo/sources/{real.id}/simulate-change").status_code == 400
    demo_id = client.get("/api/sources").json()[0]["id"]  # seeded DEMO source
    r = client.post(f"/api/demo/sources/{demo_id}/simulate-change")
    assert r.status_code == 200 and r.json()["change_type"] == "CONTENT_UPDATED"
    assert "Simulated notice" in r.json()["summary"]
    actual("real=400, demo=CONTENT_UPDATED")
