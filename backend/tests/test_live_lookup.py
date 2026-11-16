"""On-demand live lookup: official crawl -> NIRF -> third-party -> 'not published' (network mocked)."""
import pytest

from app.live import crawler, lookup, nirf
from app.models.models import QueryLog


def page(url, text="", links=(), title="Page"):
    html = "<html><head><title>%s</title></head><body><p>%s</p>%s</body></html>" % (
        title, text, "".join(f'<a href="{u}">{a}</a>' for a, u in links))
    return {"url": url, "title": title, "text": text, "doc_type": "HTML", "html": html}


@pytest.fixture
def web(monkeypatch):
    """url -> doc. Unknown URLs raise like a 404. Records every fetch."""
    monkeypatch.setenv("LIVE_FETCH_ENABLED", "true")
    pages, calls = {}, []

    def fake_fetch(url, timeout, browser_ua=False):
        calls.append(url)
        if url not in pages:
            raise RuntimeError("404")
        return pages[url]
    monkeypatch.setattr(crawler, "fetch", fake_fetch)
    return pages, calls


NIRF_HTML = """<html><body><h3>India Rankings 2025: Engineering</h3><table>
<tr><th>Institute ID</th><th>Name</th><th>City</th><th>State</th><th>Score</th><th>Rank</th></tr>
<tr><td>IR-E-U-0098</td><td>Delhi Technological University More Details</td><td>Delhi</td><td>Delhi</td><td>58.1</td><td>27</td></tr>
<tr><td>IR-E-C-6379</td><td>Netaji Subhas University of Technology (NSUT) More Details</td><td>Delhi</td><td>Delhi</td><td>50.43</td><td>70</td></tr>
</table></body></html>"""


@pytest.mark.meta("T58", "Live lookup", "No indexed evidence -> focused crawl of the official domain answers with citations", "Label 'Fetched live from msit.in · <date>', Official citation, step=official")
def test_official_crawl_answers(client, web, actual):
    pages, _ = web
    pages["https://msit.in/"] = page("https://msit.in/", "Welcome to MSIT, Janakpuri.", [("Fee Structure", "https://msit.in/fee-structure"), ("Gallery", "https://msit.in/gallery")])
    pages["https://msit.in/fee-structure"] = page("https://msit.in/fee-structure", "Fee structure 2026-27: the annual tuition fee for the B.Tech programme at MSIT is Rs 1,90,000 as notified by GGSIPU. " * 2, title="Fee Structure")
    r = client.post("/api/ask", json={"query": "What is the tuition fee at MSIT?"}).json()
    assert r["grounded"] and r["live"]["step"] == "official" and r["answer_label"].startswith("Fetched live from msit.in · ")
    assert "1,90,000" in r["answer"] and r["sources"][0]["verification"]["status"] == "OFFICIAL"
    actual(f"{r['answer_label']}; cites {r['sources'][0]['source_url']}")


@pytest.mark.meta("T59", "Live lookup", "Official site silent -> the college's row from the official NIRF table", "Answer cites the NIRF row (rank 70), label 'Fetched live from nirfindia.org', snapshot source")
def test_nirf_step(client, db, web, actual):
    pages, _ = web
    pages["https://nsut.ac.in/"] = page("https://nsut.ac.in/", "Welcome to Netaji Subhas University of Technology, Dwarka.")
    url = nirf.NIRF_PAGES[0]
    pages[url] = {"url": url, "title": "NIRF", "text": "", "doc_type": "HTML", "html": NIRF_HTML}
    r = client.post("/api/ask", json={"query": "What is the NIRF rank of NSUT?"}).json()
    assert r["grounded"] and r["live"]["step"] == "nirf" and "nirfindia.org" in r["answer_label"]
    assert "70" in r["answer"] and "Delhi Technological" not in r["answer"]
    from app.models.models import Source
    src = db.query(Source).filter(Source.college_id == "nsut", Source.source_url == url).one()
    assert src.status == "SNAPSHOT"
    actual(f"{r['answer_label']}; rank 70 cited; DTU row excluded")


@pytest.mark.meta("T60", "Live lookup", "Official + NIRF silent -> reputable third-party page, badged Unverified", "label 'Unverified third-party', THIRD_PARTY citation, confirm-on-official note")
def test_third_party_step(client, web, actual):
    pages, _ = web
    url = "https://www.careers360.com/colleges/bhagwan-parshuram-institute-of-technology-delhi/placement"
    pages[url] = page(url, "BPIT placements 2025: the highest package offered was 12 LPA and more than 150 companies visited the campus for placement drives. " * 2)
    r = client.post("/api/ask", json={"query": "How are placements at BPIT?"}).json()
    assert r["grounded"] and r["live"]["step"] == "third_party" and r["answer_label"].startswith("Unverified third-party · careers360.com")
    assert r["sources"][0]["verification"]["status"] == "THIRD_PARTY" and "confirm" in r["third_party_note"]
    actual(f"{r['answer_label']}; badge={r['sources'][0]['verification']['label']}")


@pytest.mark.meta("T61", "Live lookup", "Nothing anywhere -> 'Official sources don't publish this information (checked: …)' + official links", "grounded=False, checked list, official links, no LLM answer")
def test_not_published(client, web, actual):
    pages, _ = web
    pages["https://www.ipu.ac.in/usict/index.php"] = page("https://www.ipu.ac.in/usict/index.php", "University School of Information, Communication and Technology.",
                                                          [("Admissions", "https://www.ipu.ac.in/adm.php"), ("Contact Us", "https://www.ipu.ac.in/contact.php")])
    r = client.post("/api/ask", json={"query": "What is the hostel mess fee at USICT?"}).json()
    assert not r["grounded"] and r["answer"].startswith("Official sources don't publish this information (checked: ")
    assert "ipu.ac.in/usict/index.php" in r["answer"] and r["sources"] == []
    assert any("contact" in l["url"] or "adm" in l["url"] for l in r["official_links"])
    actual(f"{r['answer'][:80]}…; {len(r['official_links'])} official links")


@pytest.mark.meta("T62", "Live lookup", "Same college + topic within 24 h is served from the cache (no re-crawl)", "0 new fetches; live.cached=True")
def test_cache(client, web, actual):
    pages, calls = web
    q = {"query": "What is the hostel mess fee at GTBIT?"}
    client.post("/api/ask", json=q)
    before = len(calls)
    r = client.post("/api/ask", json=q).json()
    assert len(calls) == before and r["live"]["cached"] is True
    actual(f"first run {before} fetches, second run 0")


@pytest.mark.meta("T63", "Live lookup", "Crawler respects the page limit and stays on the official domain", "<= 15 pages, no external hosts")
def test_crawl_limits(web, actual):
    pages, calls = web
    links = [(f"Fee notice {i}", f"https://mait.ac.in/fee-{i}") for i in range(40)] + [("Fees elsewhere", "https://other.com/fees")]
    pages["https://mait.ac.in/"] = page("https://mait.ac.in/", "MAIT home", links)
    for i in range(40):
        pages[f"https://mait.ac.in/fee-{i}"] = page(f"https://mait.ac.in/fee-{i}", "fee notice text")
    res = crawler.crawl("https://mait.ac.in/", "mait.ac.in", ["fee"], max_pages=15, budget_s=5)
    assert len(res["checked"]) <= 15 and all("other.com" not in u for u in calls)
    actual(f"{len(res['checked'])} pages checked, external skipped")


@pytest.mark.meta("T64", "Live lookup", "Link scoring prefers topic keywords; NIRF parser keeps only the college's row", "fee links ranked first; only NSUT row kept with headers")
def test_scoring_and_nirf_rows(actual):
    links = crawler.extract_links('<a href="/gallery">Gallery</a><a href="/fees.pdf">Fee Structure 2026</a><a href="/about">About</a>',
                                  "https://bpitindia.ac.in/", "bpitindia.ac.in", ["fee", "fees"])
    assert links[0][1] == "https://bpitindia.ac.in/fees.pdf" and len(links) == 1
    rows = nirf.rows_for(NIRF_HTML, "https://nirf/x", ["Netaji Subhas University of Technology"])
    assert len(rows) == 1 and "Rank: 70" in rows[0]["text"] and "Delhi Technological" not in rows[0]["text"]
    actual("fee PDF ranked first; 1 NIRF row with 'Rank: 70'")


@pytest.mark.meta("T65", "Live lookup", "Probe call (live=false) reports what would be checked and is not logged", "live_available.domain set; query log unchanged")
def test_probe_not_logged(client, db, web, actual):
    before = db.query(QueryLog).count()
    r = client.post("/api/ask", json={"query": "What is the hostel fee at IGDTUW?", "live": False}).json()
    assert r["live_available"]["domain"] == "igdtuw.ac.in" and r["live_available"]["topic"] == "hostel"
    assert db.query(QueryLog).count() == before
    actual(f"live_available={r['live_available']}")


@pytest.mark.meta("T66", "Live lookup", "Live lookup off (LIVE_FETCH_ENABLED=false) keeps the plain refusal", "'Not available in indexed sources.' and no fetches")
def test_disabled(client, web, monkeypatch, actual):
    _, calls = web
    monkeypatch.setenv("LIVE_FETCH_ENABLED", "false")
    r = client.post("/api/ask", json={"query": "What is the hostel fee at DTU?"}).json()
    assert r["answer"] == "Not available in indexed sources." and calls == []
    actual("plain refusal, 0 fetches")


@pytest.mark.meta("T67", "Live lookup", "Comparison / multi-college questions never trigger a crawl", "no fetches; no live_available")
def test_comparison_skips_live(client, web, actual):
    _, calls = web
    r = client.post("/api/ask", json={"query": "Which is better, DTU or NSUT for hostel fees?", "live": False}).json()
    r2 = client.post("/api/ask", json={"query": "Which is better, DTU or NSUT for hostel fees?"}).json()
    assert "live_available" not in r and "live" not in r2 and calls == []
    actual("0 fetches for a comparison question")
