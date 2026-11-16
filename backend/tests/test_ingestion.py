import pytest

from app.ingestion.pipeline import IngestionError, clean_html, extract_pdf, ingest, process_text
from app.models.models import ContentVersion, IngestionEvent, UpdateEvent
from app.services import vector_store
from conftest import make_pdf

HTML = b"""<html><head><title>MAIT Departments</title><style>.x{}</style><script>var tracking=1;</script></head>
<body><nav>Home | About | Contact</nav><header>Top banner</header>
<main><h1>Departments</h1><p>The institute offers B.Tech in Computer Science and Engineering.</p>
<p>Electronics and Communication Engineering is offered as a four year programme.</p>
<p>The central library is open to all students on working days.</p></main>
<footer>Copyright footer text</footer></body></html>"""


@pytest.mark.meta("T01", "Ingestion (HTML)", "clean_html strips nav/header/footer/script/style boilerplate", "Body text kept; boilerplate removed")
def test_clean_html_removes_boilerplate(actual):
    text = clean_html(HTML.decode())
    assert "Electronics and Communication Engineering" in text
    for junk in ("Home | About", "Copyright footer", "tracking", "Top banner"):
        assert junk not in text
    actual(f"{len(text)} chars kept, 0 boilerplate strings")


@pytest.mark.meta("T02", "Ingestion (HTML)", "End-to-end HTML ingestion of a new source", "NEW_SOURCE_CONTENT event, version 1, chunks indexed, title extracted")
def test_html_ingestion_end_to_end(db, fake_web, new_source, actual):
    src = new_source("https://mait.ac.in/test-departments")
    fake_web[src.source_url] = (HTML, "text/html; charset=utf-8")
    result = ingest(db, src.id)
    assert result["changed"] and result["change_type"] == "NEW_SOURCE_CONTENT" and result["chunks"] >= 1
    version = db.query(ContentVersion).filter_by(source_id=src.id).one()
    assert version.version_no == 1 and version.document_title == "MAIT Departments"
    stored = [c for c in vector_store.all_chunks() if c["metadata"]["source_id"] == src.id]
    assert len(stored) == result["chunks"] and stored[0]["metadata"]["doc_type"] == "HTML"
    actual(f"{result['change_type']}, v{version.version_no}, {result['chunks']} chunk(s)")


@pytest.mark.meta("T03", "Ingestion (PDF)", "PyMuPDF extracts text from a PDF byte stream", "Extracted text contains the PDF sentence; page count 1")
def test_extract_pdf(actual):
    data = make_pdf("Hostel accommodation is available for first year students on a first come basis.")
    text, pages = extract_pdf(data)
    assert "Hostel accommodation is available" in text and pages == 1
    actual(f"{len(text)} chars, {pages} page")


@pytest.mark.meta("T04", "Ingestion (PDF)", "End-to-end ingestion of a PDF source (content-type sniffed)", "doc_type=PDF on chunks; text searchable")
def test_pdf_ingestion_end_to_end(db, fake_web, new_source, actual):
    src = new_source("https://example.ac.in/brochure.pdf", college_id="dtu", source_type="OFFICIAL_PDF")
    fake_web[src.source_url] = (make_pdf("Brochure: the training and placement cell coordinates campus recruitment drives every year."), "application/pdf")
    result = ingest(db, src.id)
    chunk = next(c for c in vector_store.all_chunks() if c["metadata"]["source_id"] == src.id)
    assert result["changed"] and chunk["metadata"]["doc_type"] == "PDF" and "placement cell" in chunk["text"]
    actual(f"{result['chunks']} PDF chunk(s) indexed")


@pytest.mark.meta("T05", "Ingestion", "Unreachable source is kept but marked missing", "status FETCH_FAILED, last_error set, FAILED ingestion event")
def test_fetch_failure_marks_source_missing(db, fake_web, new_source, actual):
    src = new_source("https://mait.ac.in/does-not-exist")
    with pytest.raises(RuntimeError):
        ingest(db, src.id)
    db.refresh(src)
    event = db.query(IngestionEvent).filter_by(source_id=src.id).order_by(IngestionEvent.id.desc()).first()
    assert src.status == "FETCH_FAILED" and "404" in src.last_error and event.status == "FAILED"
    assert src.content_hash is None
    actual(f"status={src.status}, event={event.status}")


@pytest.mark.meta("T06", "Ingestion", "Near-empty extraction (JS-only page) is rejected, not indexed", "IngestionError raised; no version stored")
def test_short_text_rejected(db, new_source, actual):
    src = new_source("https://mait.ac.in/js-only")
    with pytest.raises(IngestionError):
        process_text(db, src, "Loading...", "JS page")
    db.rollback()
    assert db.query(ContentVersion).filter_by(source_id=src.id).count() == 0
    assert db.query(UpdateEvent).filter_by(source_id=src.id).count() == 0
    actual("IngestionError raised, 0 versions")
