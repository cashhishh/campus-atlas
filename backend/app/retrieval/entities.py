"""Detect which colleges a question is about, and classify its intent."""
import re

ALIASES = {
    "mait": ["mait", "maharaja agrasen", "maharaja agarsen"],
    "msit": ["msit", "maharaja surajmal"],
    "dtu": ["dtu", "delhi technological", "dce", "delhi college of engineering"],
    "nsut": ["nsut", "nsit", "netaji subhas"],
    "igdtuw": ["igdtuw", "igdtu", "indira gandhi delhi technical"],
    "bpit": ["bpit", "bhagwan parshuram"],
    "gtbit": ["gtbit", "guru tegh bahadur"],
    "usict": ["usict", "university school of information"],
    "iit-delhi": ["iit delhi", "iitd", "iit-d"],
    "iiit-delhi": ["iiit delhi", "iiitd"],
    "nit-delhi": ["nit delhi"],
    "bits-pilani": ["bits pilani", "bits"],
    "nit-trichy": ["nit trichy", "nitt", "nit tiruchirappalli"],
}


def _pattern(phrase: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])")


def detect_colleges(question: str, registry: list[tuple[str, str]] | None = None) -> tuple[list[str], list[str]]:
    """Return (college_ids, matched_phrases). `registry` is [(id, name), ...]."""
    text = question.lower()
    phrases: dict[str, list[str]] = {cid: list(v) for cid, v in ALIASES.items()}
    for cid, name in registry or []:
        phrases.setdefault(cid, []).append(name.lower())
    found, matched = [], []
    for cid, options in phrases.items():
        for phrase in sorted(options, key=len, reverse=True):
            if _pattern(phrase).search(text):
                if cid not in found:
                    found.append(cid)
                matched.append(phrase)
                break
    return found, matched


def strip_phrases(question: str, phrases: list[str]) -> str:
    text = question.lower()
    for phrase in phrases:
        text = _pattern(phrase).sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def classify_intent(question: str, college_ids: list[str]) -> str:
    v = question.lower()
    if len(college_ids) > 1 or re.search(r"\b(compare|comparison|vs\.?|versus|better)\b", v):
        return "comparison"
    if re.search(r"\b(admission|admissions|eligib\w*|counselling|cutoff|jee|seat|seats|cet)\b", v):
        return "admissions"
    if re.search(r"\b(fee|fees|cost|tuition|scholarship)\b", v):
        return "fees"
    if re.search(r"\b(placement|placements|package|recruit\w*|salary)\b", v):
        return "placements"
    if re.search(r"\b(course|courses|branch|branches|programme|programmes|program|ece|cse|academics?|department)\b", v):
        return "academics"
    if re.search(r"\b(hostel|campus|facility|facilities|library|lab|labs)\b", v):
        return "campus"
    if re.search(r"\b(nirf|rank|ranking|naac|nba|accredit\w*)\b", v):
        return "rankings"
    return "general"
