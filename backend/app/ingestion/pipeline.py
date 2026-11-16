"""Ingestion pipeline: fetch -> extract -> clean -> version -> diff -> chunk -> index.

Phase 2 behaviour (HTML/PDF extraction, chunking, hash events) is kept; Phase 5
adds content versions, diffs, change summaries and failure marking.
"""
import hashlib
import re
import ssl
from urllib.parse import urlparse
from datetime import datetime

import httpx
import pymupdf
from bs4 import BeautifulSoup

from ..change_detection.diff import compute_diff, new_content_summary, summarize_change
from ..config import USER_AGENT
from ..models.models import ContentVersion, IngestionEvent, Source, UpdateEvent
from ..services.vector_store import replace_source_chunks

DEMO_TEXT = {
    'dtu': 'DEMO DATA — Delhi Technological University is a public university in New Delhi. Undergraduate admissions are described through the configured admission source. Applicants should consult the official admission notice for current eligibility, counselling and dates.',
    'mait': 'DEMO DATA — Maharaja Agrasen Institute of Technology provides academic information through its institutional website. The configured academic source lists Electronics and Communication Engineering among academic offerings. Applicants should verify current intake and eligibility using official notices.',
    'bits-pilani': 'DEMO DATA — BITS Pilani academic material describes undergraduate academic programmes and campus facilities. Admission and fee details change by cycle; consult the official brochure for current information.',
    'nit-trichy': 'DEMO DATA — NIT Tiruchirappalli campus information describes student facilities and campus services. Hostel availability, allocation rules and current charges should be verified from current official notices.',
}

BOILERPLATE_TAGS = ["nav", "footer", "script", "style", "header", "aside", "noscript", "svg", "form", "iframe", "button", "select"]
MIN_TEXT_CHARS = 80


class IngestionError(RuntimeError):
    pass


# ------------------------------------------------------------------ extract
def clean_html(raw: str, base_url: str | None = None) -> str:
    """Strip navigation/boilerplate and return whitespace-normalised visible text."""
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(BOILERPLATE_TAGS):
        tag.decompose()
    for tag in soup.select('[role="navigation"], [aria-hidden="true"], .menu, #menu, .navbar, .cookie, .breadcrumb'):
        tag.decompose()
    base = normalize(soup.get_text(" ", strip=True))
    _drop_link_dense_blocks(soup, _host(base_url))
    filtered = normalize(soup.get_text(" ", strip=True))
    # Pages whose content *is* a list of links (notices, NIRF documents) keep their text.
    return filtered if len(filtered) >= max(200, 0.25 * len(base)) else base


def _host(url: str | None) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _is_internal(href: str, site: str) -> bool:
    href = (href or "").strip()
    if not href.lower().startswith(("http://", "https://", "//")):
        return not href.lower().startswith(("mailto:", "tel:", "javascript:"))
    return bool(site) and (_host(href if not href.startswith("//") else "http:" + href) == site)


def _drop_link_dense_blocks(soup, site: str = "", min_links: int = 5, max_ratio: float = 0.7) -> None:
    """Remove menus rendered as plain lists/divs: blocks whose text is mostly *internal* link text.

    Lists of external links (recruiters, document portals) are content and are kept."""
    for block in soup.find_all(["ul", "ol", "div", "td", "section"]):
        if getattr(block, "decomposed", False):  # parent already removed
            continue
        links = [a for a in block.find_all("a") if _is_internal(a.get("href", ""), site)]
        if len(links) < min_links:
            continue
        text = block.get_text(" ", strip=True)
        link_text = sum(len(a.get_text(" ", strip=True)) for a in links)
        if text and link_text / len(text) >= max_ratio:
            block.decompose()


def html_title(raw: str) -> str | None:
    soup = BeautifulSoup(raw, "html.parser")
    return soup.title.string.strip() if soup.title and soup.title.string else None


def extract_pdf(data: bytes) -> tuple[str, int]:
    """Extract text from a PDF with PyMuPDF. Returns (text, page_count)."""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        text = " ".join(page.get_text() for page in doc)
        return normalize(text), doc.page_count


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------- chunk
def chunk_text(text: str, size: int = 700, overlap: int = 120, min_len: int = 30) -> list[str]:
    """Split on word boundaries into ~`size`-char chunks with ~`overlap` chars of overlap."""
    words = normalize(text).split(" ") if text and text.strip() else []
    out, start = [], 0
    while start < len(words):
        end, length = start, 0
        while end < len(words) and (end == start or length + len(words[end]) + 1 <= size):
            length += len(words[end]) + 1
            end += 1
        chunk = " ".join(words[start:end])
        if len(chunk) >= min_len:
            out.append(chunk)
        if end >= len(words):
            break
        new_start, back = end, 0
        while new_start > start + 1 and back < overlap:
            new_start -= 1
            back += len(words[new_start]) + 1
        start = new_start
    return out


def chunks(text, size=700):
    """First-defence name kept for compatibility."""
    return chunk_text(text, size)


# ------------------------------------------------------------------- fetch
def _ssl_context():
    """Prefer the OS trust store (handles sites with incomplete certificate chains)."""
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return True


def http_get(url: str, timeout: float = 25.0) -> httpx.Response:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8"}
    response = httpx.get(url, timeout=timeout, follow_redirects=True, headers=headers, verify=_ssl_context())
    response.raise_for_status()
    return response


def latest_version(db, source_id: int) -> ContentVersion | None:
    return (db.query(ContentVersion).filter(ContentVersion.source_id == source_id)
            .order_by(ContentVersion.version_no.desc()).first())


def fetch_document(src: Source, demo_text: str | None = None) -> dict:
    """Fetch and extract a source. Pure network/extraction step: no DB writes."""
    if src.status == "DEMO_READY" or src.is_demo:
        text = demo_text or DEMO_TEXT.get(src.college_id, "DEMO DATA — Indexed information from configured source.")
        return {"text": text, "title": src.source_name, "doc_type": "DEMO"}
    response = http_get(src.source_url)
    ctype = response.headers.get("content-type", "").lower()
    if "pdf" in ctype or src.source_url.lower().endswith(".pdf") or response.content[:5] == b"%PDF-":
        text, pages = extract_pdf(response.content)
        return {"text": text, "title": src.source_name, "doc_type": "PDF", "pages": pages}
    return {"text": clean_html(response.text, str(response.url) if hasattr(response, "url") else src.source_url), "title": html_title(response.text) or src.source_name, "doc_type": "HTML"}


# ----------------------------------------------------------------- process
def process_text(db, src: Source, text: str, title: str | None, doc_type: str = "HTML",
                 monitor_run_id: int | None = None, use_llm: bool = True) -> dict:
    """Hash, version, diff, summarise and index extracted text for one source."""
    text = normalize(text)
    if len(text) < MIN_TEXT_CHARS:
        raise IngestionError(f"Extracted only {len(text)} characters (JavaScript-only page or scanned PDF?)")
    now = datetime.utcnow()
    new_hash = content_hash(text)
    old_hash = src.content_hash
    src.last_checked = now
    src.last_error = None
    if src.status == "FETCH_FAILED":
        src.status = "ACTIVE"

    if new_hash == old_hash:
        if latest_version(db, src.id) is None:  # legacy DB: store a baseline so future diffs work
            db.add(ContentVersion(source_id=src.id, version_no=1, content_hash=new_hash, text=text,
                                  char_count=len(text), document_title=title))
        db.add(IngestionEvent(source_id=src.id, status="SUCCESS", document_title=title, chunks_created=0,
                              message="No content change", monitor_run_id=monitor_run_id))
        db.commit()
        return {"status": "success", "changed": False, "chunks": 0, "source_id": src.id}

    previous = latest_version(db, src.id)
    version = ContentVersion(source_id=src.id, version_no=(previous.version_no + 1) if previous else 1,
                             content_hash=new_hash, text=text, char_count=len(text), document_title=title)
    db.add(version)
    db.flush()

    pieces = chunk_text(text)
    payload = [{
        "id": f"{src.id}-v{version.version_no}-{i}",
        "text": piece,
        "metadata": {
            "college_id": src.college_id or "", "source_id": src.id, "source_url": src.source_url,
            "source_name": src.source_name, "source_type": src.source_type or "",
            "authority_level": src.authority_level or "", "document_title": title or src.source_name,
            "doc_type": doc_type, "version_no": version.version_no, "chunk_index": i,
            "is_demo": bool(src.is_demo or src.status == "DEMO_READY"), "ingested_at": now.isoformat(),
        },
    } for i, piece in enumerate(pieces)]
    replace_source_chunks(src.id, payload)

    if previous is None and old_hash is None:
        change_type, diff = "NEW_SOURCE_CONTENT", None
        summary, mode = new_content_summary(text, len(pieces), title), "deterministic"
    elif previous is None:
        change_type, diff = "CONTENT_UPDATED", None
        summary, mode = "Content changed; the previous text predates version tracking so no diff is available.", "deterministic"
    else:
        change_type = "CONTENT_UPDATED"
        diff = compute_diff(previous.text, text)
        summary, mode = summarize_change(diff, src.source_name, use_llm=use_llm)

    event = UpdateEvent(
        college_id=src.college_id, source_id=src.id, change_type=change_type, old_hash=old_hash, new_hash=new_hash,
        old_version_id=previous.id if previous else None, new_version_id=version.id, summary=summary,
        summary_mode=mode, diff=diff["unified"] if diff else None,
        added_count=len(diff["added"]) if diff else len(pieces), removed_count=len(diff["removed"]) if diff else 0,
        monitor_run_id=monitor_run_id,
    )
    db.add(event)
    src.content_hash = new_hash
    src.last_changed = now
    db.add(IngestionEvent(source_id=src.id, status="SUCCESS", document_title=title, chunks_created=len(pieces),
                          message=f"Indexed changed content (version {version.version_no})", monitor_run_id=monitor_run_id))
    db.commit()
    return {"status": "success", "changed": True, "chunks": len(pieces), "source_id": src.id,
            "change_type": change_type, "update_event_id": event.id, "summary": summary}


def record_failure(db, src: Source, error: Exception, monitor_run_id: int | None = None) -> None:
    """Keep the source, mark it as missing/failed and log why."""
    message = f"{type(error).__name__}: {error}"[:500]
    src.last_error = message
    if src.status not in ("DEMO_READY", "DISABLED"):
        src.status = "FETCH_FAILED"
    db.add(IngestionEvent(source_id=src.id, status="FAILED", chunks_created=0, message=message, monitor_run_id=monitor_run_id))
    db.commit()


def ingest(db, source_id: int, monitor_run_id: int | None = None, prefetched: dict | None = None) -> dict:
    src = db.get(Source, source_id)
    if not src:
        raise ValueError("Source not found")
    try:
        if prefetched is None:
            demo_prev = latest_version(db, src.id) if (src.status == "DEMO_READY" or src.is_demo) else None
            prefetched = fetch_document(src, demo_prev.text if demo_prev else None)
        return process_text(db, src, prefetched["text"], prefetched.get("title"), prefetched.get("doc_type", "HTML"),
                            monitor_run_id=monitor_run_id)
    except Exception as exc:
        db.rollback()
        src = db.get(Source, source_id)
        record_failure(db, src, exc, monitor_run_id)
        raise
