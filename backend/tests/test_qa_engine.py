"""Query understanding, comparison/recommendation tables, NIRF parsing, hybrid ranking, partial evidence."""
import pytest

from app.facts.nirf_facts import parse_data_pdf
from app.live import crawler
from app.models.models import CollegeFact, Source
from app.qa import engine
from app.qa.understand import rules, understand
from app.retrieval import rag
from app.services import embeddings, vector_store

NIRF_TEXT = ("Sanctioned (Approved) Intake Academic Year 2023-24 2022-23 UG [4 Years Program(s)] 2529 2529 PG [2 Year Program(s)] 435 "
             "UG [4 Years Program(s)]: Placement & higher studies for previous 3 years Academic Year ... "
             "2018-19 2210 2240 2019-20 33 2021-22 2131 1880 1300000(Thirteen Lakhs) 251 "
             "2019-20 2360 2262 2020-21 16 2022-23 2220 1965 1410000(Fourteen lakhs ten thousand) 255 "
             "2020-21 2529 2484 2021-22 17 2023-24 2412 1759 1325000(Thirteen lakhs Twenty five thousand only) 653 "
             "PG [2 Year Program(s)]: Placement 2021-22 300 200 1025500(Ten lakhs) 5")


@pytest.mark.meta("T68", "Query understanding", "Rules classify COMPARE / RECOMMEND / FACT and find ALL colleges", "dtu+nsut COMPARE; best college for ECE in Delhi = RECOMMEND with branch+location")
def test_understanding_rules(actual):
    assert rules("which is better dtu or nsut?")["type"] == "COMPARE"
    assert set(rules("compare MAIT and BPIT placements")["colleges"]) == {"mait", "bpit"}
    qu = understand("best college for ECE in Delhi", use_llm=False)
    assert qu["type"] == "RECOMMEND" and qu["location"] == "delhi" and qu["branch"] == "electronics and communication"
    assert understand("MAIT fees", use_llm=False)["type"] == "FACT"
    actual("COMPARE, COMPARE, RECOMMEND(delhi, ECE), FACT")


@pytest.mark.meta("T69", "NIRF facts", "NIRF data PDF text is parsed into median salary by year and UG intake", "3 UG years incl. 2023-24 = 13,25,000; intake 2529; PG row ignored")
def test_parse_nirf_pdf(actual):
    d = parse_data_pdf(NIRF_TEXT)
    assert d["ug_intake"] == 2529 and [r["median"] for r in d["median_salary"]] == [1300000, 1410000, 1325000]
    assert d["median_salary"][-1]["year"] == "2023-24"
    actual("medians 13.0L / 14.1L / 13.25L, intake 2529")


def _fact(db, cid, field, value, num, src):
    db.query(CollegeFact).filter_by(college_id=cid, field=field).delete()
    db.add(CollegeFact(college_id=cid, field=field, value=str(value), num=num, year="2025", source_id=src.id,
                       source_url=src.source_url, source_name=src.source_name, evidence=f"{field} {value}"))
    db.commit()


@pytest.fixture
def nirf_facts(db):
    srcs = {}
    for cid in ("dtu", "nsut"):
        s = Source(college_id=cid, source_name=f"NIRF {cid}", source_url=f"https://www.nirfindia.org/{cid}.pdf",
                   source_type="NIRF_DATA", authority_level="VERY_HIGH", status="SNAPSHOT", is_demo=False)
        db.add(s)
        db.commit()
        db.refresh(s)
        srcs[cid] = s
    _fact(db, "dtu", "nirf_rank", 30, 30.0, srcs["dtu"])
    _fact(db, "nsut", "nirf_rank", 70, 70.0, srcs["nsut"])
    _fact(db, "dtu", "median_salary_ug", 1325000, 1325000.0, srcs["dtu"])
    _fact(db, "nsut", "median_salary_ug", 1650000, 1650000.0, srcs["nsut"])
    return srcs


@pytest.mark.meta("T70", "Compare", "which is better dtu or nsut -> cited table + neutral summary + caveat", "rank row cites NIRF; summary names strengths of each; not an absolute verdict; missing cells = not in sources")
def test_compare_table(db, nirf_facts, actual):
    r = engine.ask(db, "which is better dtu or nsut?", use_llm=False)
    rows = {row["aspect"]: row["cells"] for row in r["table"]["rows"]}
    assert r["query_type"] == "COMPARE" and rows["NIRF 2025"][0]["text"].startswith("Rank 30") and rows["NIRF 2025"][0]["cite"]
    assert "Delhi Technological University is stronger on NIRF position" in r["answer"]
    assert "Netaji Subhas University of Technology is stronger on median UG salary" in r["answer"]
    assert "not an absolute verdict" in r["answer"] and "Find My College" in r["answer"]
    assert any(c["text"] == "not in sources" for cells in rows.values() for c in cells)
    actual(r["answer"][:120] + "…")


@pytest.mark.meta("T71", "Recommend", "best college for ECE in Delhi -> shortlist ordered by NIRF facts with branch evidence", "only colleges whose sources mention ECE; DTU before NSUT; caveat")
def test_recommend(db, nirf_facts, actual):
    for cid, sid in (("dtu", 9301), ("nsut", 9302)):
        vector_store.replace_source_chunks(sid, [{
            "id": f"{sid}-x", "text": f"{cid.upper()} offers B.Tech in Electronics and Communication Engineering with a large intake.",
            "metadata": {"college_id": cid, "source_id": nirf_facts[cid].id, "source_url": nirf_facts[cid].source_url,
                         "source_name": "Programmes", "source_type": "OFFICIAL_COLLEGE", "authority_level": "VERY_HIGH",
                         "document_title": "Programmes", "is_demo": False}}])
    r = engine.ask(db, "best college for ECE in Delhi", use_llm=False)
    names = [c["id"] for c in r["table"]["columns"]]
    assert r["query_type"] == "RECOMMEND" and names[:2] == ["dtu", "nsut"] and "not an absolute verdict" in r["answer"]
    for sid in (9301, 9302):
        vector_store.delete_source(sid)
    actual(f"order={names}")


@pytest.mark.meta("T72", "Hybrid search", "Semantic similarity is blended with BM25 when embeddings exist", "a semantically close chunk with no shared keyword is still returned")
def test_hybrid_ranking(monkeypatch, actual):
    vector_store.replace_source_chunks(9401, [
        {"id": "a", "text": "The training cell helped 300 graduates get jobs last year.", "metadata": {"college_id": "gtbit", "source_id": 9401, "document_title": "T&P"}},
        {"id": "b", "text": "The library opens at nine.", "metadata": {"college_id": "gtbit", "source_id": 9401, "document_title": "Library"}}])
    monkeypatch.setattr(embeddings, "similarities", lambda text, ids: {"a": 0.78, "b": 0.50})
    hits = vector_store.query("placements record", ["gtbit"])
    assert hits and hits[0]["id"] == "a" and hits[0]["cosine"] == 0.78 and all(h["id"] != "b" for h in hits)
    vector_store.delete_source(9401)
    actual("semantic-only match ranked first; unrelated chunk dropped")


@pytest.mark.meta("T73", "Partial evidence", "LLM says not available but strongly relevant text exists -> show the passages", "grounded=True with partial-evidence notice and [S1]")
def test_partial_evidence(monkeypatch, actual):
    from app.ai import llm
    vector_store.replace_source_chunks(9501, [{
        "id": "p", "text": "The swimming pool on campus is open to hostel residents in the evening.",
        "metadata": {"college_id": "mait", "source_id": 9501, "source_url": "https://mait.ac.in/sports", "source_name": "Sports",
                     "source_type": "OFFICIAL_COLLEGE", "authority_level": "VERY_HIGH", "document_title": "Sports", "is_demo": False}}])
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "generate", lambda *a, **k: ("Not available in indexed sources.", "gemini", []))
    r = rag.answer("What is the swimming pool size at MAIT?")
    assert r["grounded"] and "Most relevant passages" in r["answer"] and "[S1]" in r["answer"] and "Partial evidence" in r["notice"]
    vector_store.delete_source(9501)
    actual("passages shown with notice")


@pytest.mark.meta("T74", "Live lookup", "Link ranking demotes PhD/MBA/tender/notice pages unless asked", "B.Tech fee page kept; MBA fee notice and tender dropped")
def test_link_penalties(actual):
    html = ('<a href="/btech-fee">B.Tech Fee Structure</a><a href="/mba-fee-notice.pdf">MBA fee notice</a>'
            '<a href="/tender-fee.pdf">Tender fee</a>')
    links = [u for _, u, _ in crawler.extract_links(html, "https://dtu.ac.in/", "dtu.ac.in", ["fee", "fees", "b.tech"])]
    assert links == ["https://dtu.ac.in/btech-fee"]
    actual(f"kept {links}")
