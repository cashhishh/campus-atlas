"""Question topics, crawl keywords and curated third-party pages for on-demand lookup."""
import re

# topic -> keywords used to pick links (anchor text / URL) and to keep fetched pages.
TOPIC_KEYWORDS = {
    "fees": ["fee", "fees", "fee-structure", "tuition", "prospectus", "brochure", "admission", "bulletin"],
    "hostel": ["hostel", "accommodation", "residence", "mess", "fee"],
    "placements": ["placement", "placements", "training", "t&p", "tnp", "recruit", "career", "nirf"],
    "admissions": ["admission", "admissions", "counselling", "eligibility", "prospectus", "brochure", "jac", "cet"],
    "rankings": ["nirf", "ranking", "rank", "naac", "nba", "accreditation"],
    "academics": ["programme", "program", "course", "department", "academics", "curriculum", "b.tech", "btech", "intake"],
    "campus": ["campus", "facilities", "facility", "infrastructure", "library", "sports", "hostel"],
    "general": ["about", "admission", "academics", "placement"],
}
CONTACT_KEYWORDS = ["admission", "contact"]


def detect_topic(question: str, intent: str | None = None) -> str:
    q = question.lower()
    if re.search(r"\bhostel|accommodation|mess\b", q):
        return "hostel"
    if re.search(r"\bnirf|rank|ranking|naac|nba|accredit", q):
        return "rankings"
    if re.search(r"\bfee|fees|tuition|cost\b", q):
        return "fees"
    if re.search(r"\bplacement|placements|package|salary|recruit|ctc\b", q):
        return "placements"
    if re.search(r"\badmission|cutoff|cut-off|eligib|counselling|jee|cet\b", q):
        return "admissions"
    mapping = {"fees": "fees", "placements": "placements", "admissions": "admissions", "rankings": "rankings",
               "academics": "academics", "campus": "campus"}
    return mapping.get(intent or "", "general")


# Reputable third-party pages that answer plain HTTP requests (robots.txt allows /colleges and /university
# pages; checked 16 Nov 2026). Shiksha and Wikipedia refuse automated requests, so they are not listed.
CAREERS360 = {
    "mait": "https://www.careers360.com/colleges/maharaja-agrasen-institute-of-technology-delhi",
    "bpit": "https://www.careers360.com/colleges/bhagwan-parshuram-institute-of-technology-delhi",
    "gtbit": "https://www.careers360.com/colleges/guru-tegh-bahadur-institute-of-technology-delhi",
    "msit": "https://www.careers360.com/colleges/maharaja-surajmal-institute-of-technology-delhi",
    "nsut": "https://www.careers360.com/university/netaji-subhas-university-of-technology-new-delhi",
}
CAREERS360_SUBPAGE = {"fees": "/fees", "hostel": "/fees", "placements": "/placement", "admissions": "/admission",
                      "rankings": "/ranking", "academics": "/courses", "campus": "/facilities", "general": ""}


def third_party_urls(college_id: str, topic: str) -> list[str]:
    base = CAREERS360.get(college_id)
    if not base:
        return []
    sub = CAREERS360_SUBPAGE.get(topic, "")
    return [base + sub] if sub else [base]
