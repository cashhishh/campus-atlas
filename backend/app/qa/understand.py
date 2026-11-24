"""Query understanding: type (FACT / COMPARE / RECOMMEND / LIST), colleges, topics, sub-queries.

A cheap LLM call (Gemini -> Groq) returns JSON; it is validated against the registry and merged
with deterministic rules, which are also the fallback when no LLM is available or it is slow.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from ..ai import llm
from ..retrieval.entities import detect_colleges

TYPES = ("FACT", "COMPARE", "RECOMMEND", "LIST")
TOPIC_PATTERNS = {
    "rankings": r"\bnirf|rank|ranking|naac|nba|accredit",
    "placements": r"placement|package|salary|recruit|ctc|job",
    "fees": r"\bfee|fees|tuition|cost|afford",
    "hostel": r"hostel|accommodation|mess",
    "admissions": r"admission|cutoff|cut-off|eligib|counselling|jee|cet",
    "academics": r"\bece\b|\bcse\b|\bit\b|branch|course|programme|program|b\.?tech|intake|department",
    "campus": r"campus|facilit|library|lab|sports|infrastructure",
}
TOPIC_QUERY = {
    "rankings": "NIRF rank and score", "placements": "placement record and median salary",
    "fees": "B.Tech annual tuition fee", "hostel": "hostel fee and facilities",
    "admissions": "B.Tech admission process and eligibility", "academics": "B.Tech programmes offered and intake",
    "campus": "campus facilities",
}
LOCATIONS = ["delhi", "noida", "gurgaon", "gurugram", "ncr", "mumbai", "bangalore", "bengaluru", "chennai", "hyderabad",
             "pune", "kolkata", "jaipur", "punjab", "rajasthan", "tamil nadu", "karnataka", "uttar pradesh"]
BRANCHES = {"ece": "electronics and communication", "cse": "computer science", "it": "information technology",
            "eee": "electrical and electronics", "mechanical": "mechanical", "civil": "civil", "ai": "artificial intelligence",
            "electronics": "electronics and communication", "computer": "computer science"}

PROMPT = """Classify a student's question about Indian engineering colleges. Reply with JSON only:
{"type": "FACT|COMPARE|RECOMMEND|LIST", "colleges": ["<names or abbreviations exactly as written>"],
 "topics": ["rankings|placements|fees|hostel|admissions|academics|campus"], "subqueries": ["2-6 short search queries"]}
COMPARE = choosing between named colleges ("which is better X or Y", "X vs Y", "compare").
RECOMMEND = asking for the best/top colleges for something without naming them. LIST = asking to list colleges.
FACT = anything else about specific colleges. Do not answer the question."""


def rules(question: str, registry=None) -> dict:
    q = question.lower()
    ids, _ = detect_colleges(question, registry)
    topics = [t for t, pat in TOPIC_PATTERNS.items() if re.search(pat, q)]
    if len(ids) >= 2 or (re.search(r"\b(better|vs\.?|versus|compare|comparison|difference)\b", q) and ids):
        qtype = "COMPARE"
    elif re.search(r"\b(best|top|recommend|suggest|good)\b", q) and not ids:
        qtype = "RECOMMEND"
    elif re.search(r"\b(list|which colleges|colleges (with|that|offering|in))\b", q) and not ids:
        qtype = "LIST"
    else:
        qtype = "FACT"
    return {"type": qtype, "colleges": ids, "topics": topics, "subqueries": [], "source": "rules"}


def _llm(question: str) -> dict | None:
    text, provider, _ = llm.generate(PROMPT, question, max_tokens=300, temperature=0.0, timeout=10,
                                         prefer=llm.task_provider("understand"))
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    data = json.loads(m.group(0))
    data["provider"] = provider
    return data


def understand(question: str, registry=None, use_llm: bool = True, budget_s: float = 2.5) -> dict:
    base = rules(question, registry)
    base["location"] = next((loc for loc in LOCATIONS if re.search(rf"\b{loc}\b", question.lower())), None)
    base["branch"] = next((full for k, full in BRANCHES.items() if re.search(rf"\b{k}\b", question.lower())), None)
    confident = (bool(base["colleges"]) and (base["type"] == "COMPARE" or bool(base["topics"]))) or \
        (base["type"] == "RECOMMEND" and bool(base["branch"] or base["location"]))
    if use_llm and llm.is_configured() and not confident:  # cheap LLM call only when the rules are unsure
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            data = pool.submit(_llm, question).result(timeout=budget_s)
        except (FutureTimeout, Exception):
            data = None
        finally:
            pool.shutdown(wait=False)
        if data:
            names = " ; ".join(str(c) for c in data.get("colleges") or [])
            extra, _ = detect_colleges(names, registry) if names else ([], [])
            colleges = list(dict.fromkeys(base["colleges"] + extra))
            qtype = str(data.get("type", "")).upper()
            if qtype in TYPES:
                # rules win when they are unambiguous (two named colleges = comparison)
                base["type"] = "COMPARE" if len(colleges) >= 2 and qtype == "FACT" else qtype
            base["colleges"] = colleges
            base["topics"] = list(dict.fromkeys(base["topics"] + [t for t in data.get("topics") or [] if t in TOPIC_PATTERNS]))
            base["subqueries"] = [str(s)[:120] for s in (data.get("subqueries") or [])][:6]
            base["source"] = data.get("provider", "llm")
    if base["type"] == "COMPARE" and len(base["colleges"]) < 2:
        base["type"] = "FACT"
    if not base["subqueries"]:
        topics = base["topics"] or (["rankings", "placements", "fees", "academics"] if base["type"] == "COMPARE" else [])
        base["subqueries"] = [f"{TOPIC_QUERY[t]}" for t in topics][:6] or [question]
    return base
