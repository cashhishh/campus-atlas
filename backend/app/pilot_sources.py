"""Real public sources for the 8 pilot colleges (second defence, Step 2).

Every URL is an official college / university page or an official NIRF data PDF,
verified reachable on 2026-11-16. Nothing is typed in by hand: all text comes
from ingestion. Two sources are kept on purpose although they yield no text
(IGDTUW's site is JavaScript-only; BPIT's fee notice is a scanned PDF): they are
marked FETCH_FAILED and the app answers "Not available in indexed sources."
"""


def _s(college_id, name, url, source_type="OFFICIAL_COLLEGE", authority="VERY_HIGH"):
    return {"college_id": college_id, "source_name": name, "source_url": url,
            "source_type": source_type, "authority_level": authority}


NIRF = "NIRF_DATA"
PDF = "OFFICIAL_PDF"
UNI = "UNIVERSITY_PAGE"

PILOT_SOURCES: list[dict] = [
    # MAIT — Maharaja Agrasen Institute of Technology (GGSIPU affiliated)
    _s("mait", "MAIT — About the Institute", "https://mait.ac.in/index.php/abouts/about-us.html"),
    _s("mait", "MAIT — Courses of Study", "https://mait.ac.in/index.php/portfolio/course-of-study.html"),
    _s("mait", "MAIT — Fee Structure", "https://mait.ac.in/index.php/portfolio/fees.html"),
    _s("mait", "MAIT — Admissions 2026-27", "https://mait.ac.in/index.php/component/content/article/admissions-2026-27.html?catid=9&Itemid=384"),
    _s("mait", "MAIT — Hostel", "https://mait.ac.in/index.php/facilities/hostel.html"),
    _s("mait", "MAIT — Library", "https://mait.ac.in/index.php/facilities/library.html"),
    _s("mait", "MAIT — About Placements", "https://mait.ac.in/index.php/placements/about-placements.html"),
    _s("mait", "MAIT — NIRF", "https://mait.ac.in/index.php/component/content/article/nirf.html?catid=9&Itemid=384"),
    # DTU — Delhi Technological University
    _s("dtu", "DTU — History", "https://dtu.ac.in/Web/About/history.php"),
    _s("dtu", "DTU — Academics (UG)", "https://dtu.ac.in/Web/Academics"),
    _s("dtu", "DTU — Details of UG Programmes (PDF)", "https://dtu.ac.in/Web/Programs_dtu.pdf", PDF),
    _s("dtu", "DTU — Dept. of Electronics & Communication", "https://dtu.ac.in/Web/Departments/Electronics/about"),
    _s("dtu", "DTU — Dept. of Computer Science & Engg.", "https://dtu.ac.in/Web/Departments/CSE/about"),
    _s("dtu", "NIRF 2025 — DTU data submitted by institution (PDF)", "https://www.nirfindia.org/nirfpdfcdn/2025/pdf/Engineering/IR-E-U-0098.pdf", NIRF),
    # NSUT — Netaji Subhas University of Technology
    _s("nsut", "NSUT — About NSUT", "https://www.nsut.ac.in/en/about-nsut-0"),
    _s("nsut", "NSUT — Educational Programmes", "https://www.nsut.ac.in/en/educational-programmes"),
    _s("nsut", "NSUT — UG Admission", "https://www.nsut.ac.in/en/ug-admission"),
    _s("nsut", "NSUT — Hostels", "https://www.nsut.ac.in/en/hostels"),
    _s("nsut", "NIRF 2025 — NSUT data submitted by institution (PDF)", "https://www.nirfindia.org/nirfpdfcdn/2025/pdf/Engineering/IR-E-C-6379.pdf", NIRF),
    # IGDTUW — site is a JavaScript single-page app: kept, will be marked missing
    _s("igdtuw", "IGDTUW — Official website", "https://www.igdtuw.ac.in/"),
    # BPIT — Bhagwan Parshuram Institute of Technology
    _s("bpit", "BPIT — About", "https://bpitindia.ac.in/about/"),
    _s("bpit", "BPIT — Fee Structure", "https://bpitindia.ac.in/fee-structure-2/"),
    _s("bpit", "BPIT — Girls' Hostel", "https://bpitindia.ac.in/girls-hostal-2/"),
    _s("bpit", "BPIT — Placement Record", "https://bpitindia.ac.in/placement-record/"),
    _s("bpit", "BPIT — Accreditation", "https://bpitindia.ac.in/accreditation/"),
    _s("bpit", "BPIT — Annual fee for first year 2026-27 (scanned PDF)", "https://bpitindia.ac.in/wp-content/uploads/2026/07/Annual-fee-for-first-year-2026-27_compressed.pdf", PDF),
    # GTBIT — Guru Tegh Bahadur Institute of Technology
    _s("gtbit", "GTBIT — About Us", "https://www.gtbit.ac.in/about-us"),
    _s("gtbit", "GTBIT — Admission Procedures", "https://www.gtbit.ac.in/admission-procedure"),
    _s("gtbit", "GTBIT — Training & Placement", "https://www.gtbit.ac.in/placement"),
    _s("gtbit", "GTBIT — Fee & Scholarship", "https://www.gtbit.ac.in/scholarship"),
    _s("gtbit", "GTBIT — NIRF data (PDF)", "https://www.gtbit.ac.in/assets/pdf/NIRF.pdf", NIRF),
    # MSIT — Maharaja Surajmal Institute of Technology (registered domain msit.in)
    _s("msit", "MSIT — About", "https://msit.in/about"),
    _s("msit", "MSIT — Facilities", "https://msit.in/facilities"),
    _s("msit", "MSIT — Placements", "https://msit.in/placements"),
    _s("msit", "MSIT — NIRF", "https://msit.in/nirf"),
    _s("msit", "MSIT — Affiliation / Accreditation", "https://msit.in/affiliation"),
    # USICT — University School of Information, Communication & Technology, GGSIPU
    _s("usict", "USICT — Home", "https://www.ipu.ac.in/usict/index.php", UNI),
    _s("usict", "USICT — Academic Programmes", "https://www.ipu.ac.in/usict/Programmes.php", UNI),
    _s("usict", "USICT — Placement Cell", "https://www.ipu.ac.in/usict/placement.php", UNI),
    _s("usict", "USICT — Laboratories", "https://www.ipu.ac.in/usict/Laboratories.php", UNI),
    _s("usict", "GGSIPU — Hostel Facilities (university-wide)", "https://www.ipu.ac.in/hostels.php", UNI, "HIGH"),
    _s("usict", "GGSIPU — Admissions 2026-27", "https://www.ipu.ac.in/adm2026/adm2026main.php", UNI, "HIGH"),
]
