from datetime import datetime, timedelta

import pytest

from app.recommendations.engine import MAX_SCORE, compare_evidence, recommend
from app.verification.rules import classify_source, freshness

COLLEGES = [
    {"id": "mait", "name": "MAIT", "category": "Delhi & NCR", "city": "New Delhi", "state": "Delhi"},
    {"id": "vit", "name": "VIT", "category": "Private", "city": "Vellore", "state": "Tamil Nadu"},
    {"id": "nitk", "name": "NITK", "category": "NIT", "city": "Mangaluru", "state": "Karnataka"},
]


@pytest.mark.meta("T26", "Compare scoring", "Location preference adds +20 with an explanation", "Delhi college scores 20 and explains why; others 0")
def test_location_scoring(actual):
    out = recommend(COLLEGES, {"location": "delhi"})
    assert out[0]["college"]["id"] == "mait" and out[0]["score"] == 20 and "Located in your preferred area" in out[0]["why"]
    assert all(r["score"] == 0 for r in out[1:])
    actual(f"mait=20, others={[r['score'] for r in out[1:]]}")


@pytest.mark.meta("T27", "Compare scoring", "Branch points only when an indexed source mentions the branch", "+30 with evidence; 0 + 'needs confirmation' without")
def test_branch_requires_evidence(actual):
    evidence = lambda cid, text: cid == "nitk"
    out = {r["college"]["id"]: r for r in recommend(COLLEGES, {"branch": "electronics"}, evidence=evidence)}
    assert out["nitk"]["score"] == 30 and out["mait"]["score"] == 0
    assert "needs confirmation" in out["mait"]["why"][0]
    actual("nitk=30 (evidence), mait=0 (no evidence)")


@pytest.mark.meta("T28", "Compare scoring", "Scores are bounded, sorted descending and explainable", f"0 <= score <= {MAX_SCORE}; sorted; every result has reasons")
def test_scores_bounded_sorted(actual):
    out = recommend(COLLEGES, {"branch": "cse", "location": "delhi", "type": "Government", "hostel": True, "placement": True},
                    evidence=lambda *_: True)
    scores = [r["score"] for r in out]
    assert scores == sorted(scores, reverse=True) and all(0 <= s <= MAX_SCORE for s in scores) and all(r["why"] for r in out)
    assert out[0]["score"] == MAX_SCORE
    actual(f"scores={scores}")


@pytest.mark.meta("T29", "Compare evidence", "Topics without indexed evidence say 'Not available in indexed sources.'", "Fees cell unavailable; programmes cell cites source")
def test_compare_evidence_not_available(actual):
    def fake_retrieve(text, cid):
        if "programmes" in text:
            return [{"text": "B.Tech in ECE and CSE is offered.", "score": 0.9, "metadata": {"source_id": 1, "source_name": "Dept page", "source_url": "https://mait.ac.in/"}}]
        return []
    data = compare_evidence(["mait"], fake_retrieve)
    row = data["colleges"]["mait"]
    assert row["Programmes"]["available"] and row["Programmes"]["source_name"] == "Dept page"
    assert row["Fees"] == {"available": False, "text": "Not available in indexed sources."}
    actual("Programmes=cited, Fees=Not available")


@pytest.mark.meta("T30", "Verification", ".ac.in / .edu.in / .gov.in domains are official", "OFFICIAL")
def test_academic_domains_official(actual):
    for url in ("https://www.dtu.ac.in/admissions", "https://www.srmist.edu.in/", "https://www.education.gov.in/x.pdf"):
        assert classify_source(url)["status"] == "OFFICIAL"
    actual("3/3 OFFICIAL")


@pytest.mark.meta("T31", "Verification", "NIRF (nirfindia.org) is official", "OFFICIAL with 'Government / statutory body'")
def test_nirf_official(actual):
    v = classify_source("https://www.nirfindia.org/Rankings/2025/EngineeringRanking.html")
    assert v["status"] == "OFFICIAL" and "statutory" in v["reason"]
    actual(v["reason"])


@pytest.mark.meta("T32", "Verification", "College's registered domain (non-.ac.in) is official", "msit.in -> OFFICIAL only when it is MSIT's registered domain")
def test_registered_domain(actual):
    assert classify_source("https://msit.in/about", "msit.in")["status"] == "OFFICIAL"
    assert classify_source("https://msit.in/about")["status"] == "UNVERIFIED"
    actual("with domain=OFFICIAL, without=UNVERIFIED")


@pytest.mark.meta("T33", "Verification", "Aggregators are third-party; unknown domains unverified", "shiksha=THIRD_PARTY, random blog=UNVERIFIED")
def test_third_party_and_unverified(actual):
    assert classify_source("https://www.shiksha.com/college/mait")["status"] == "THIRD_PARTY"
    assert classify_source("https://en.wikipedia.org/wiki/DTU")["status"] == "THIRD_PARTY"
    assert classify_source("https://best-colleges-blog.com/mait")["status"] == "UNVERIFIED"
    actual("THIRD_PARTY, THIRD_PARTY, UNVERIFIED")


@pytest.mark.meta("T34", "Verification", "Look-alike domains are not trusted", "mait.ac.in.evil.com and fakeac.in -> not OFFICIAL")
def test_lookalike_domains(actual):
    assert classify_source("https://mait.ac.in.evil.com/", "mait.ac.in")["status"] != "OFFICIAL"
    assert classify_source("https://notmait.in/", "mait.in")["status"] != "OFFICIAL"
    actual("both rejected")


@pytest.mark.meta("T35", "Freshness", "Fresh / stale / never-checked states", "2h=FRESH, 100h=STALE (72h limit), None=NEVER_CHECKED")
def test_freshness(actual):
    now = datetime(2026, 11, 16, 12, 0)
    assert freshness(now - timedelta(hours=2), None, now, 72)["state"] == "FRESH"
    stale = freshness(now - timedelta(hours=100), now - timedelta(hours=200), now, 72)
    assert stale["state"] == "STALE" and stale["stale"] and stale["changed_hours_ago"] == 200
    assert freshness(None, None, now, 72)["state"] == "NEVER_CHECKED"
    actual("FRESH, STALE, NEVER_CHECKED")
