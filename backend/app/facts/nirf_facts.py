"""Structured NIRF facts (rank / band / score / median salary / intake) with citations.

Sources:
  * NIRF India Rankings 2025 (Engineering) tables on nirfindia.org -> rank + score, or rank band
  * NIRF "data submitted by institution" PDFs (on nirfindia.org or the college's own site)
    -> UG 4-year median salary per graduating year, UG sanctioned intake
Every fact keeps the source it came from so answers can cite it.
"""
import re

from ..live import crawler, nirf
from ..models.models import CollegeFact, ContentVersion, Source

# Official NIRF 2025 data PDFs for pilot colleges that are not already registered sources.
NIRF_DATA_PDFS = {
    "mait": ("MAIT — NIRF 2025 Engineering data (PDF)", "https://mait.ac.in/images/nirf/nirf25/ENGG-MAHARAJA_AGRASEN_INSTITUTE_OF_TECHNOLOGY20250108-.pdf"),
    "msit": ("MSIT — NIRF 2025 Engineering data (PDF)", "https://msit.in/media/uploads/2025/06/18/nirf-2025-engineering.pdf"),
    "bpit": ("BPIT — NIRF 2025 data (PDF)", "https://bpitindia.ac.in/wp-content/uploads/2025/02/Bhagwan-Parshuram-Institute-of-Technology20250117-_compressed.pdf"),
}
BAND_PAGES = {"150": "101-150", "200": "151-200", "300": "201-300"}
PILOT = ["mait", "dtu", "nsut", "igdtuw", "bpit", "gtbit", "msit", "usict"]
# Names as they appear in NIRF tables (USICT is ranked as part of GGSIPU).
NIRF_NAMES = {"usict": ["Guru Gobind Singh Indraprastha University"], "nsut": ["Netaji Subhas University of Technology"]}

_ROW = re.compile(r"(20\d\d-\d\d)\s+(\d+)\s+(\d+)\s+(\d{5,9})\s*(?:\(([^)]*)\))?\s+(\d+)")


def parse_data_pdf(text: str) -> dict:
    """Extract UG-4-year median salaries (by graduating year) and sanctioned UG intake."""
    out = {"median_salary": [], "ug_intake": None}
    m = re.search(r"Sanctioned \(Approved\) Intake.*?UG \[4 Years Program\(s\)\]\s+(\d+)", text, re.S)
    if m:
        out["ug_intake"] = int(m.group(1))
    start = text.find("UG [4 Years Program(s)]: Placement")
    if start < 0:
        start = text.find("Placement & Higher Studies")
    if start >= 0:
        end = text.find("PG [2 Year", start + 10)
        section = text[start:end if end > 0 else start + 3000]
        for year, graduating, placed, salary, words, higher in _ROW.findall(section):
            out["median_salary"].append({"year": year, "graduating": int(graduating), "placed": int(placed),
                                         "median": int(salary), "words": words.strip()})
    return out


def _latest_text(db, source_id: int) -> str:
    v = db.query(ContentVersion).filter_by(source_id=source_id).order_by(ContentVersion.version_no.desc()).first()
    return v.text if v else ""


def _put(db, college_id, field, value, num, year, src, evidence):
    db.query(CollegeFact).filter_by(college_id=college_id, field=field).delete()
    db.add(CollegeFact(college_id=college_id, field=field, value=str(value), num=num, year=year,
                       source_id=src.id if src else None, source_url=src.source_url if src else None,
                       source_name=src.source_name if src else None, evidence=evidence[:400]))


def _snapshot_source(db, college_id, doc):
    src = db.query(Source).filter_by(college_id=college_id, source_url=doc["url"]).first()
    if src is None:
        src = Source(college_id=college_id, source_name=doc["title"], source_url=doc["url"], source_type="NIRF_RANKING",
                     authority_level="VERY_HIGH", status="SNAPSHOT", is_demo=False)
        db.add(src)
        db.commit()
        db.refresh(src)
    return src


def build(db, colleges: list[str] | None = None, ingest_pdfs: bool = True) -> dict:
    """Fetch/parse NIRF data and store CollegeFact rows. Returns a per-college report."""
    from ..ingestion.pipeline import ingest, process_text
    from ..models.models import College

    report = {}
    pages = {}
    for url in nirf.NIRF_PAGES:  # fetch each ranking page once
        try:
            pages[url] = crawler.fetch(url, timeout=15)["html"]
        except Exception:
            pages[url] = ""
    for cid in colleges or PILOT:
        college = db.get(College, cid)
        if not college:
            continue
        names = NIRF_NAMES.get(cid, []) + [college.name]
        rep = report.setdefault(cid, {})
        # 1. rank / band from the ranking tables
        for url, html in pages.items():
            rows = nirf.rows_for(html, url, names)
            if not rows:
                continue
            row = rows[0]
            src = _snapshot_source(db, cid, row)
            try:
                process_text(db, src, row["text"], row["title"], "HTML")
            except Exception:
                db.rollback()
            band = next((b for k, b in BAND_PAGES.items() if url.endswith(f"Ranking{k}.html")), None)
            if band:
                _put(db, cid, "nirf_band", band, float(band.split("-")[0]), "2025", src,
                     f"Listed in the NIRF 2025 Engineering rank band {band}")
                rep["nirf_band"] = band
            else:
                rank = re.search(r"Rank: (\d+)", row["text"])
                score = re.search(r"Score: ([\d.]+)", row["text"])
                if rank:
                    _put(db, cid, "nirf_rank", rank.group(1), float(rank.group(1)), "2025", src, row["text"][-200:])
                    rep["nirf_rank"] = int(rank.group(1))
                if score:
                    _put(db, cid, "nirf_score", score.group(1), float(score.group(1)), "2025", src, row["text"][-200:])
                    rep["nirf_score"] = float(score.group(1))
            break
        # 2. data PDF -> median salary + intake
        if ingest_pdfs and cid in NIRF_DATA_PDFS:
            name, url = NIRF_DATA_PDFS[cid]
            src = db.query(Source).filter_by(college_id=cid, source_url=url).first()
            if src is None:
                src = Source(college_id=cid, source_name=name, source_url=url, source_type="NIRF_DATA",
                             authority_level="VERY_HIGH", status="ACTIVE", is_demo=False)
                db.add(src)
                db.commit()
                db.refresh(src)
            if not src.content_hash:
                try:
                    ingest(db, src.id)
                except Exception as exc:
                    rep["pdf_error"] = f"{type(exc).__name__}"
        for src in db.query(Source).filter(Source.college_id == cid, Source.source_type == "NIRF_DATA").all():
            data = parse_data_pdf(_latest_text(db, src.id))
            if data["median_salary"]:
                latest = data["median_salary"][-1]
                _put(db, cid, "median_salary_ug", latest["median"], float(latest["median"]), latest["year"], src,
                     f"UG 4-year graduates of {latest['year']}: {latest['placed']} placed of {latest['graduating']}; "
                     f"median salary Rs {latest['median']:,} per annum")
                rep["median_salary_ug"] = {r["year"]: r["median"] for r in data["median_salary"]}
            if data["ug_intake"]:
                _put(db, cid, "ug_intake", data["ug_intake"], float(data["ug_intake"]), "2023-24", src,
                     f"Sanctioned UG 4-year intake: {data['ug_intake']}")
                rep["ug_intake"] = data["ug_intake"]
            if data["median_salary"]:
                break
        db.commit()
    return report


def facts_for(db, college_id: str) -> dict:
    return {f.field: f for f in db.query(CollegeFact).filter_by(college_id=college_id).all()}
