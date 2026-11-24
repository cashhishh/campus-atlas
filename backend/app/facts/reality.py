"""Field reality: what actually happened to a college's graduates, from its own NIRF data PDF.

Colleges advertise the *highest* package. The NIRF "data submitted by institution" PDF has to state,
per graduating batch: students graduating, students placed, median salary and students who went
for higher studies. From that we derive the numbers a student really needs:

  placement rate      = placed / graduating
  higher-studies rate = higher studies / graduating
  neither             = graduating - placed - higher studies   (no job offer through the college, no PG)
  median salary trend over the last three batches

Every number is cited to the official PDF, and is set against the "highest package" claims found
in the college's own indexed pages - the gap between the two is the field reality.
"""
import re

from ..models.models import College, ContentVersion, Source

_ROW = re.compile(r"(20\d\d-\d\d)\s+(\d+)\s+(\d+)\s+(\d{5,9})\s*(?:\(([^)]*)\))?\s+(\d+)")
_HIGHEST = re.compile(r"(highest|maximum|max\.?|top)\s+(package|ctc|salary|offer)[^.\n]{0,60}?"
                      r"(₹|rs\.?|inr)?\s*([\d.]+)\s*(lpa|lakhs?|lacs?|l\b|crores?|cr\b)", re.I)


def _lakh(n: float) -> str:
    return f"₹{n / 100000:.1f} L".replace(".0 L", " L")


def _rows(text: str) -> list[dict]:
    start = text.find("UG [4 Years Program(s)]: Placement")
    if start < 0:
        start = text.find("Placement & Higher Studies")
    if start < 0:
        return []
    end = text.find("PG [2 Year", start + 10)
    section = text[start:end if end > 0 else start + 3000]
    rows, seen = [], set()
    for year, grad, placed, salary, _words, higher in _ROW.findall(section):
        if year in seen:  # first table = UG 4-year; later repeats are other programmes
            continue
        seen.add(year)
        g, p, h = int(grad), int(placed), int(higher)
        if not g or p > g:
            continue
        rows.append({"year": year, "graduating": g, "placed": p, "median": int(salary), "higher": h,
                     "placement_pct": round(100 * p / g, 1), "higher_pct": round(100 * h / g, 1),
                     "neither": max(0, g - p - h), "neither_pct": round(100 * max(0, g - p - h) / g, 1)})
    return sorted(rows, key=lambda r: r["year"])


def _claims(college_id: str) -> list[dict]:
    """'Highest package' statements in the college's own indexed pages (the marketing number)."""
    from ..services.vector_store import all_chunks

    out = []
    for ch in all_chunks():
        meta = ch.get("metadata") or {}
        if meta.get("college_id") != college_id or meta.get("source_type") in ("NIRF_DATA", "NIRF_RANKING", "THIRD_PARTY_REFERENCE"):
            continue
        for m in _HIGHEST.finditer(ch.get("text") or ""):
            val, unit = float(m.group(4)), m.group(5).lower()
            lakh = val * 100 if unit.startswith("cr") else val
            if 3 <= lakh <= 300:
                out.append({"lakh": lakh, "text": m.group(0)[:140], "meta": meta})
    return sorted(out, key=lambda c: -c["lakh"])[:1]


def reality(db, college_id: str) -> dict | None:
    """Placement reality for one college, or None when no NIRF data PDF is indexed."""
    for src in db.query(Source).filter(Source.college_id == college_id, Source.source_type == "NIRF_DATA").all():
        v = db.query(ContentVersion).filter_by(source_id=src.id).order_by(ContentVersion.version_no.desc()).first()
        rows = _rows(v.text if v else "")
        if not rows:
            continue
        college = db.get(College, college_id)
        try:
            claim = _claims(college_id)
        except Exception:
            claim = []
        return {"college_id": college_id, "college": college.name if college else college_id, "rows": rows,
                "latest": rows[-1], "source": src, "claim": claim[0] if claim else None}
    return None


def summary_text(r: dict) -> str:
    """One citable paragraph (used as LLM context and in answers)."""
    L = r["latest"]
    parts = [f"Field reality for {r['college']} from its official NIRF data (UG 4-year B.Tech, {L['year']} batch): "
             f"{L['graduating']:,} graduated, {L['placed']:,} were placed ({L['placement_pct']}%), "
             f"{L['higher']:,} went for higher studies ({L['higher_pct']}%), and {L['neither']:,} ({L['neither_pct']}%) "
             f"were neither reported as placed nor in higher studies. Median salary of placed students: {_lakh(L['median'])} per annum."]
    if len(r["rows"]) > 1:
        parts.append("Trend: " + "; ".join(f"{x['year']}: {x['placement_pct']}% placed, median {_lakh(x['median'])}" for x in r["rows"]) + ".")
    if r.get("claim"):
        c = r["claim"]
        parts.append(f"For contrast, the college's own website advertises a highest package of about ₹{c['lakh']:g} L "
                     f"(\"{c['text']}\") — the highest offer goes to one student; the median above is what a typical placed student gets.")
    return " ".join(parts)


def table_cells(r: dict | None) -> dict:
    if not r:
        return {}
    L = r["latest"]
    return {
        "placed": (f"{L['placement_pct']}% placed ({L['placed']:,}/{L['graduating']:,}, {L['year']})", L["placement_pct"]),
        "neither": (f"{L['neither_pct']}% ({L['neither']:,}) — not placed, not in higher studies", L["neither_pct"]),
        "trend": ("; ".join(f"{x['year'][2:]}: {_lakh(x['median'])}, {x['placement_pct']:.0f}%" for x in r["rows"]), None),
    }


# ---------------------------------------------------------------- teachers & campus (NIRF data PDF)
_FAC = re.compile(r"(\d+)\s+([A-Z][A-Za-z .'()-]+?)\s+(\d{2})\s+(.{3,60}?)\s+(Male|Female|Transgender|Other)\s+(.{2,40}?)\s+"
                  r"(\d{1,4})\s+(Yes|No)\s+(\d\d-\d\d-\d{4})\s+(--|\d\d-\d\d-\d{4})\s+"
                  r"(Regular|Adhoc|Ad-hoc|Contractual|Visiting|Other|Permanent|Temporary|Contract|Guest)", re.S)
_STRENGTH = re.compile(r"Total Actual Student Strength.*?UG \[4 Years Program\(s\)\]\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", re.S)
_LAB = re.compile(r"New Equipment and software for Laboratories\s+(\d{4,})")
_LIB = re.compile(r"Library \( Books, Journals and e-Resources only\)\s+(\d{3,})")


def _latest_nirf_text(db, college_id: str):
    for src in db.query(Source).filter(Source.college_id == college_id, Source.source_type == "NIRF_DATA").all():
        v = db.query(ContentVersion).filter_by(source_id=src.id).order_by(ContentVersion.version_no.desc()).first()
        if v and v.text and "Faculty" in v.text:
            return src, v.text
    return None, ""


def campus(db, college_id: str) -> dict | None:
    """Teachers and student body from the NIRF data PDF: faculty count, PhD share, ad-hoc share,
    seniority, student-faculty ratio, gender ratio, out-of-state share, lab/library spend per student."""
    src, text = _latest_nirf_text(db, college_id)
    if not src:
        return None
    out: dict = {"source": src}
    m = _STRENGTH.search(text)
    if m:
        male, female, total, within, outside = (int(x) for x in m.groups())
        if total and male + female == total:
            out["students"] = {"total": total, "female": female, "female_pct": round(100 * female / total, 1),
                               "outside_state_pct": round(100 * outside / total, 1)}
    i = text.find("Faculty Details")
    rows = [r for r in _FAC.findall(text[i:])] if i >= 0 else []
    current = [r for r in rows if r[7] == "Yes"]
    if len(current) >= 10:
        phd = sum(bool(re.search(r"ph\.?\s?d", r[5], re.I)) for r in current)
        adhoc = sum(r[10].lower() not in ("regular", "permanent") for r in current)
        prof = sum(r[3].strip() in ("Professor", "Associate Professor") for r in current)
        exp = sorted(int(r[6]) / 12 for r in current)
        out["faculty"] = {"count": len(current), "phd_pct": round(100 * phd / len(current), 1), "phd": phd,
                          "adhoc_pct": round(100 * adhoc / len(current), 1), "adhoc": adhoc,
                          "senior_pct": round(100 * prof / len(current), 1),
                          "median_experience_years": round(exp[len(exp) // 2], 1),
                          "left_recently": sum(r[7] == "No" for r in rows)}
        if out.get("students"):
            out["faculty"]["student_ratio"] = round(out["students"]["total"] / len(current), 1)
    lab, lib = _LAB.search(text), _LIB.search(text)
    if out.get("students") and (lab or lib):
        n = out["students"]["total"]
        out["spend"] = {"lab_per_student": round(int(lab.group(1)) / n) if lab else None,
                        "library_per_student": round(int(lib.group(1)) / n) if lib else None}
    return out if len(out) > 1 else None


def campus_text(name: str, c: dict) -> str:
    bits = []
    f, s, sp = c.get("faculty"), c.get("students"), c.get("spend")
    if f:
        bits.append(f"Teachers at {name} (official NIRF data): {f['count']} current faculty; {f['phd_pct']}% hold a PhD; "
                    f"{f['senior_pct']}% are Professors/Associate Professors (the rest mostly Assistant Professors); "
                    f"{f['adhoc_pct']}% are ad-hoc/contractual; median teaching experience {f['median_experience_years']} years"
                    + (f"; student-faculty ratio about {f['student_ratio']}:1 (AICTE norm 20:1)" if f.get("student_ratio") else "")
                    + (f"; {f['left_recently']} faculty listed as having left" if f.get("left_recently") else "") + ".")
    if s:
        bits.append(f"Student body: {s['total']:,} UG students, {s['female_pct']}% women, {s['outside_state_pct']}% from outside the state.")
    if sp and (sp.get("lab_per_student") or sp.get("library_per_student")):
        bits.append("Spend per student last year: " + ", ".join(x for x in [
            f"₹{sp['lab_per_student']:,} on new lab equipment/software" if sp.get("lab_per_student") else "",
            f"₹{sp['library_per_student']:,} on library" if sp.get("library_per_student") else ""] if x) + ".")
    return " ".join(bits)
