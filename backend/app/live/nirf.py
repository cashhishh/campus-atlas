"""Extract a single college's row from the official NIRF ranking pages.

The ranking tables list many colleges, so only the matching row is kept, and it
is written out with the column headers and the page heading. That keeps the rank
attributable to the right institution.
"""
import re

from bs4 import BeautifulSoup

from . import crawler

NIRF_YEAR = 2025
NIRF_PAGES = [f"https://www.nirfindia.org/Rankings/{NIRF_YEAR}/EngineeringRanking{s}.html" for s in ("", "150", "200", "300")]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def _matches(row_text: str, names: list[str]) -> bool:
    t = " " + " ".join(_norm(row_text).split()) + " "
    return any(" " + " ".join(_norm(n).split()) + " " in t for n in names if n)


def rows_for(html: str, url: str, names: list[str]) -> list[dict]:
    soup = BeautifulSoup(html or "", "html.parser")
    heading = " ".join((soup.find(["h1", "h2", "h3"]) or soup.new_tag("x")).get_text(" ", strip=True).split()) or f"NIRF India Rankings {NIRF_YEAR}"
    out = []
    for table in soup.find_all("table"):
        headers = [" ".join(th.get_text(" ", strip=True).split()) for th in table.find_all("th")]
        for tr in table.find_all("tr"):
            cells = [" ".join(td.get_text(" ", strip=True).replace("More Details", "").split()) for td in tr.find_all("td", recursive=False)]
            if not cells or not _matches(" ".join(cells), names):
                continue
            pairs = "; ".join(f"{h}: {c}" for h, c in zip(headers, cells) if c and len(c) < 120)
            name = next((c for c in cells if _matches(c, names)), cells[0])
            name = re.split(r"\s+(?:Close|\|)", name)[0].strip() or name  # drop the "More Details" popup text
            text = (f"{heading}. Official NIRF ranking table published by the Ministry of Education ({url}). "
                    f"Row for {name}: {pairs}.")
            out.append({"url": url, "title": f"NIRF {NIRF_YEAR} Engineering ranking — {name}", "text": text, "doc_type": "HTML"})
    return out


def lookup(names: list[str], budget_s: float = 10.0) -> dict:
    """Return {docs, checked, errors} for rows matching any of `names`."""
    docs, checked, errors = [], [], []
    for url in NIRF_PAGES:
        try:
            page = crawler.fetch(url, timeout=min(6.0, budget_s))
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}")
            continue
        checked.append(url)
        found = rows_for(page["html"], url, names)
        docs += found
        if found:
            break
    return {"docs": docs, "checked": checked, "errors": errors}
