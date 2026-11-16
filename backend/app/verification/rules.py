"""Source verification (official / third-party / unverified) and freshness rules.

Verification is decided by deterministic domain rules so it can be explained
and tested; nothing is inferred by an LLM.
"""
from datetime import datetime, timedelta
from urllib.parse import urlparse

from ..config import STALE_AFTER_HOURS

OFFICIAL = "OFFICIAL"
THIRD_PARTY = "THIRD_PARTY"
UNVERIFIED = "UNVERIFIED"

LABELS = {OFFICIAL: "Official", THIRD_PARTY: "Third-party", UNVERIFIED: "Unverified"}

# Indian academic and government second-level domains.
OFFICIAL_SUFFIXES = (".ac.in", ".edu.in", ".gov.in", ".nic.in", ".res.in", ".edu")
# Government / statutory bodies that publish college data.
OFFICIAL_HOSTS = {
    "nirfindia.org",  # National Institutional Ranking Framework (Ministry of Education)
    "aicte-india.org",
    "ugc.gov.in",
    "naac.gov.in",
    "nbaind.org",
    "josaa.nic.in",
    "jacdelhi.admissions.nic.in",
}
# Aggregators, news and encyclopedias: useful, but never authoritative.
THIRD_PARTY_HOSTS = {
    "shiksha.com", "collegedunia.com", "careers360.com", "collegedekho.com", "getmyuni.com",
    "wikipedia.org", "indiatoday.in", "timesofindia.indiatimes.com", "hindustantimes.com",
    "ndtv.com", "jagranjosh.com", "quora.com", "reddit.com", "youtube.com",
}


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _matches(host: str, domain: str) -> bool:
    domain = domain.lower().removeprefix("www.")
    return host == domain or host.endswith("." + domain)


def classify_source(url: str, official_domain: str | None = None) -> dict:
    """Return {'status', 'label', 'reason'} for a source URL."""
    host = _host(url)
    if not host:
        return {"status": UNVERIFIED, "label": LABELS[UNVERIFIED], "reason": "URL has no valid host"}
    if official_domain and _matches(host, official_domain):
        return {"status": OFFICIAL, "label": LABELS[OFFICIAL], "reason": f"Matches the college's registered domain ({official_domain})"}
    for known in OFFICIAL_HOSTS:
        if _matches(host, known):
            return {"status": OFFICIAL, "label": LABELS[OFFICIAL], "reason": f"Government / statutory body ({known})"}
    for suffix in OFFICIAL_SUFFIXES:
        if host.endswith(suffix):
            return {"status": OFFICIAL, "label": LABELS[OFFICIAL], "reason": f"Academic or government domain ({suffix})"}
    for known in THIRD_PARTY_HOSTS:
        if _matches(host, known):
            return {"status": THIRD_PARTY, "label": LABELS[THIRD_PARTY], "reason": f"Known third-party publisher ({known})"}
    return {"status": UNVERIFIED, "label": LABELS[UNVERIFIED], "reason": "Domain is not on an official or known third-party list"}


def freshness(last_checked: datetime | None, last_changed: datetime | None = None,
              now: datetime | None = None, stale_after_hours: int | None = None) -> dict:
    """Freshness indicator: FRESH, STALE (not checked recently) or NEVER_CHECKED."""
    now = now or datetime.utcnow()
    limit = stale_after_hours if stale_after_hours is not None else STALE_AFTER_HOURS
    if last_checked is None:
        return {"state": "NEVER_CHECKED", "stale": True, "checked_hours_ago": None, "changed_hours_ago": None, "stale_after_hours": limit}
    checked_age = (now - last_checked) / timedelta(hours=1)
    changed_age = (now - last_changed) / timedelta(hours=1) if last_changed else None
    stale = checked_age > limit
    return {
        "state": "STALE" if stale else "FRESH",
        "stale": stale,
        "checked_hours_ago": round(checked_age, 1),
        "changed_hours_ago": round(changed_age, 1) if changed_age is not None else None,
        "stale_after_hours": limit,
    }
