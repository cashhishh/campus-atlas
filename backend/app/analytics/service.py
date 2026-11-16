"""Aggregates for the analytics dashboard."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import func

from ..models.models import College, IngestionEvent, MonitorRun, QueryLog, Source, UpdateEvent
from ..services.vector_store import count, count_by_source
from ..verification.rules import classify_source, freshness


def _days(n: int) -> list[str]:
    today = datetime.utcnow().date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def build_analytics(db, days: int = 14) -> dict:
    since = datetime.utcnow() - timedelta(days=days)
    labels = _days(days)
    colleges = {c.id: c for c in db.query(College).all()}
    sources = db.query(Source).all()
    chunk_total, driver = count()
    per_source = count_by_source()

    # --- sources: verification, authority, freshness, status
    verification, authority, freshness_states, status = Counter(), Counter(), Counter(), Counter()
    for s in sources:
        domain = colleges[s.college_id].official_domain if s.college_id in colleges else None
        verification[classify_source(s.source_url or "", domain)["label"]] += 1
        authority[s.authority_level or "UNKNOWN"] += 1
        freshness_states[freshness(s.last_checked, s.last_changed)["state"]] += 1
        status[s.status or "UNKNOWN"] += 1

    # --- chunks per college
    college_of = {s.id: s.college_id for s in sources}
    per_college = Counter()
    for sid, n in per_source.items():
        per_college[college_of.get(sid, "unknown")] += n
    chunks_by_college = [{"college_id": cid, "name": colleges[cid].name if cid in colleges else cid, "chunks": n}
                         for cid, n in per_college.most_common(12)]

    # --- events over time
    changes = defaultdict(Counter)
    for e in db.query(UpdateEvent).filter(UpdateEvent.detected_date >= since).all():
        changes[e.detected_date.date().isoformat()][e.change_type] += 1
    ingests = defaultdict(Counter)
    for e in db.query(IngestionEvent).filter(IngestionEvent.created_at >= since).all():
        ingests[e.created_at.date().isoformat()][e.status] += 1
    timeline = [{
        "date": d,
        "new_content": changes[d]["NEW_SOURCE_CONTENT"], "content_updated": changes[d]["CONTENT_UPDATED"],
        "ingestion_success": ingests[d]["SUCCESS"], "ingestion_failed": ingests[d]["FAILED"],
    } for d in labels]

    # --- queries
    top_queries = [{"query": q, "count": n, "last_asked": last} for q, n, last in (
        db.query(QueryLog.normalized_query, func.count(QueryLog.id), func.max(QueryLog.created_at))
        .group_by(QueryLog.normalized_query).order_by(func.count(QueryLog.id).desc(), func.max(QueryLog.created_at).desc())
        .limit(10).all())]
    q_total = db.query(QueryLog).count()
    q_answered = db.query(QueryLog).filter(QueryLog.answered.is_(True)).count()
    avg_retrieval, avg_total = db.query(func.avg(QueryLog.retrieval_ms), func.avg(QueryLog.total_ms)).one()
    intents = Counter(i for (i,) in db.query(QueryLog.intent).all())

    runs = db.query(MonitorRun).order_by(MonitorRun.started_at.desc()).limit(10).all()

    return {
        "generated_at": datetime.utcnow(),
        "totals": {
            "colleges": len(colleges),
            "colleges_indexed": len([c for c in per_college if c in colleges]),
            "sources": len(sources),
            "chunks": chunk_total,
            "vector_driver": driver,
            "ingestion_runs": db.query(IngestionEvent).count(),
            "ingestion_failures": db.query(IngestionEvent).filter(IngestionEvent.status == "FAILED").count(),
            "change_events": db.query(UpdateEvent).count(),
            "content_updates": db.query(UpdateEvent).filter(UpdateEvent.change_type == "CONTENT_UPDATED").count(),
            "monitor_runs": db.query(MonitorRun).count(),
            "queries": q_total,
            "answered_rate": round(q_answered / q_total, 3) if q_total else None,
            "avg_retrieval_ms": round(avg_retrieval, 1) if avg_retrieval is not None else None,
            "avg_answer_ms": round(avg_total, 1) if avg_total is not None else None,
        },
        "verification_breakdown": dict(verification),
        "authority_breakdown": dict(authority),
        "freshness_breakdown": dict(freshness_states),
        "status_breakdown": dict(status),
        "timeline": timeline,
        "chunks_by_college": chunks_by_college,
        "top_queries": top_queries,
        "intent_breakdown": dict(intents),
        "recent_runs": [{"id": r.id, "started_at": r.started_at, "status": r.status, "trigger": r.trigger,
                         "sources_checked": r.sources_checked, "changes_found": r.changes_found,
                         "errors": r.errors, "duration_ms": r.duration_ms} for r in runs[::-1]],
    }
