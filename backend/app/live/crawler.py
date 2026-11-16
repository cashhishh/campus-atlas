"""Focused, time-boxed crawler for on-demand lookups.

Starts at a college's official homepage, follows links on the same domain
whose text/URL match the question topic (two hops), and stops after
`max_pages` pages or `budget_s` seconds. All network access goes through
`fetch()` so tests can replace it.
"""
import time
from concurrent.futures import ThreadPoolExecutor, wait
from urllib.parse import unquote, urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..ingestion.pipeline import clean_html, extract_pdf, html_title, http_get

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".mp4", ".mp3")
SKIP_WORDS = ("login", "signin", "javascript:", "mailto:", "tel:", "#", "facebook.", "twitter.", "instagram.", "youtube.", "linkedin.")
MAX_PDF_BYTES = 12_000_000


def host_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def fetch(url: str, timeout: float, browser_ua: bool = False) -> dict:
    """Fetch one URL and extract text. Returns {url, title, text, doc_type, html}."""
    if browser_ua:
        r = httpx.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": BROWSER_UA})
        r.raise_for_status()
    else:
        r = http_get(url, timeout=timeout)
    ctype = r.headers.get("content-type", "").lower()
    final = str(getattr(r, "url", url))
    if "pdf" in ctype or url.lower().endswith(".pdf") or r.content[:5] == b"%PDF-":
        if len(r.content) > MAX_PDF_BYTES:
            raise ValueError("PDF too large")
        text, _ = extract_pdf(r.content)
        title = unquote(final.rsplit("/", 1)[-1]).rsplit(".", 1)[0].replace("_", " ")
        return {"url": final, "title": title, "text": text, "doc_type": "PDF", "html": ""}
    return {"url": final, "title": html_title(r.text) or final, "text": clean_html(r.text, final), "doc_type": "HTML", "html": r.text}


# Pages that are rarely what a B.Tech applicant asks about: demoted unless the question mentions them.
OFF_TOPIC = ("phd", "ph.d", "mba", "emba", "m.tech", "mtech", "m.des", "mdes", "tender", "recruitment", "advertisement",
             "corrigendum", "walk-in", "faculty-position", "notice", "circular", "quotation", "auction")
BOOST = ("b.tech", "btech", "undergraduate", "placement", "nirf", "fee", "hostel")


def score_link(text: str, url: str, keywords: list[str]) -> int:
    t, u = text.lower(), url.lower()
    score = sum(2 for k in keywords if k in t) + sum(1 for k in keywords if k in u)
    if score <= 0:
        return 0
    asked = " ".join(keywords).lower()
    score += sum(1 for b in BOOST if b in t + " " + u and b in asked)
    if any(o in t + " " + u and o not in asked for o in OFF_TOPIC):
        score -= 4
    return score


def extract_links(html: str, base_url: str, domain: str, keywords: list[str]) -> list[tuple[int, str, str]]:
    """Return [(score, url, anchor)] for same-domain links, best first."""
    out, seen = [], set()
    for a in BeautifulSoup(html or "", "html.parser").find_all("a", href=True):
        href = a["href"].strip()
        if not href or any(w in href.lower() for w in SKIP_WORDS[:5]):
            continue
        url = urldefrag(urljoin(base_url, href))[0]
        if not url.startswith("http") or url in seen or url.lower().endswith(SKIP_EXT):
            continue
        h = host_of(url)
        if not (h == domain or h.endswith("." + domain)):
            continue
        seen.add(url)
        anchor = " ".join(a.get_text(" ", strip=True).split())[:120]
        s = score_link(anchor, url, keywords)
        if s > 0:
            out.append((s + (1 if url.lower().endswith(".pdf") else 0), url, anchor))
    return sorted(out, key=lambda x: -x[0])


def crawl(start_url: str, domain: str, keywords: list[str], skip_urls: set[str] | None = None,
          max_pages: int = 15, budget_s: float = 12.0) -> dict:
    """Two-hop focused crawl. Returns {docs, checked, links, errors, elapsed_s}."""
    started = time.monotonic()
    skip = set(skip_urls or ())
    checked, docs, errors, contact_links = [], [], [], []

    def remaining():
        return budget_s - (time.monotonic() - started)

    home, starts = None, [start_url]
    if "://www." not in start_url:
        starts.append(start_url.replace("://", "://www.", 1))
    for url in starts:
        try:
            home = fetch(url, timeout=min(6.0, max(1.0, remaining())))
            checked.append(url)
            break
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}")
    if home is None:
        return {"docs": [], "checked": [start_url], "links": [], "errors": errors, "home_readable": False,
                "elapsed_s": round(time.monotonic() - started, 1)}
    home_readable = len(home["text"]) >= 200
    if len(home["text"]) >= 80:
        docs.append(home)

    contact_links = [(u, a) for s, u, a in extract_links(home["html"], home["url"], domain, ["admission", "contact"])
                     if not u.lower().endswith(".pdf")][:3]
    frontier = [(s, u) for s, u, _ in extract_links(home["html"], home["url"], domain, keywords) if u not in skip]
    visited = {start_url, home["url"]}

    pool = ThreadPoolExecutor(max_workers=6)
    try:
        for hop in range(2):
            batch = []
            for _, url in frontier:
                if url not in visited and len(checked) + len(batch) < max_pages:
                    batch.append(url)
                    visited.add(url)
            if not batch or remaining() <= 1:
                break
            futures = {pool.submit(fetch, u, max(1.0, min(6.0, remaining()))): u for u in batch}
            done, not_done = wait(futures, timeout=max(0.5, remaining()))
            next_frontier = []
            for f in done:
                url = futures[f]
                checked.append(url)
                try:
                    doc = f.result()
                except Exception as exc:
                    errors.append(f"{url}: {type(exc).__name__}")
                    continue
                docs.append(doc)
                if hop == 0 and doc["html"]:
                    next_frontier += [(s, u) for s, u, _ in extract_links(doc["html"], doc["url"], domain, keywords) if u not in skip]
            for f in not_done:
                errors.append(f"{futures[f]}: time budget exceeded")
                f.cancel()
            frontier = sorted(next_frontier, key=lambda x: -x[0])
    finally:
        pool.shutdown(wait=False, cancel_futures=True)  # never wait past the budget for slow downloads
    return {"docs": docs, "checked": checked, "links": contact_links, "errors": errors, "home_readable": home_readable,
            "home_url": home["url"], "elapsed_s": round(time.monotonic() - started, 1)}
