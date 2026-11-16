"""Phase 5 automated source monitoring.

An APScheduler background job re-checks every registered source on a
configurable interval. Each execution is logged as a MonitorRun (start, end,
sources checked, changes found, errors). The same function powers the
"Run check now" API endpoint.
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from .. import config
from ..database import SessionLocal
from ..ingestion.pipeline import fetch_document, ingest, latest_version
from ..models.models import MonitorRun, Source

JOB_ID = "campusatlas-source-monitor"
_run_lock = threading.Lock()
_scheduler: BackgroundScheduler | None = None


def _fetch_safely(src_snapshot):
    """Network step, run in a thread pool. Returns (source_id, document | exception)."""
    source_id, src, demo_text = src_snapshot
    try:
        return source_id, fetch_document(src, demo_text)
    except Exception as exc:  # recorded later by ingest()
        return source_id, exc


def run_monitoring_cycle(trigger: str = "manual", source_ids: list[int] | None = None) -> dict:
    """Re-check sources once. Safe to call from the scheduler or an API request."""
    if not _run_lock.acquire(blocking=False):
        return {"status": "ALREADY_RUNNING", "message": "A monitoring run is already in progress."}
    db = SessionLocal()
    started = time.perf_counter()
    try:
        run = MonitorRun(trigger=trigger, status="RUNNING", started_at=datetime.utcnow())
        db.add(run)
        db.commit()

        q = db.query(Source).filter(Source.status.notin_(("DISABLED", "SNAPSHOT")))  # snapshots: on-demand only
        if source_ids:
            q = q.filter(Source.id.in_(source_ids))
        sources = q.order_by(Source.id).all()
        snapshots = []
        for s in sources:
            demo = latest_version(db, s.id) if (s.status == "DEMO_READY" or s.is_demo) else None
            snapshots.append((s.id, s, demo.text if demo else None))

        with ThreadPoolExecutor(max_workers=max(1, config.MONITOR_MAX_WORKERS)) as pool:
            fetched = dict(pool.map(_fetch_safely, snapshots))

        results, changes, errors = [], 0, 0
        for s in sources:
            doc = fetched.get(s.id)
            entry = {"source_id": s.id, "source_name": s.source_name, "college_id": s.college_id}
            try:
                if isinstance(doc, Exception):
                    raise doc
                outcome = ingest(db, s.id, monitor_run_id=run.id, prefetched=doc)
                entry.update(status="CHANGED" if outcome["changed"] else "UNCHANGED",
                             change_type=outcome.get("change_type"), summary=outcome.get("summary"))
                changes += int(outcome["changed"])
            except Exception as exc:
                if isinstance(doc, Exception):  # fetch failed before ingest(): record it
                    from ..ingestion.pipeline import record_failure

                    db.rollback()
                    record_failure(db, db.get(Source, s.id), exc, run.id)
                errors += 1
                entry.update(status="ERROR", error=f"{type(exc).__name__}: {exc}"[:300])
            results.append(entry)

        run = db.get(MonitorRun, run.id)
        run.finished_at = datetime.utcnow()
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        run.sources_checked = len(sources)
        run.changes_found = changes
        run.errors = errors
        run.status = "SUCCESS" if errors == 0 else ("FAILED" if errors == len(sources) and sources else "PARTIAL")
        run.details = json.dumps(results, default=str)
        db.commit()
        return serialize_run(run, include_details=True)
    finally:
        db.close()
        _run_lock.release()


def serialize_run(run: MonitorRun, include_details: bool = False) -> dict:
    data = {
        "id": run.id, "trigger": run.trigger, "status": run.status, "started_at": run.started_at,
        "finished_at": run.finished_at, "duration_ms": run.duration_ms, "sources_checked": run.sources_checked,
        "changes_found": run.changes_found, "errors": run.errors,
    }
    if include_details:
        data["details"] = json.loads(run.details) if run.details else []
    return data


def is_running() -> bool:
    return _run_lock.locked()


def _scheduled_job():
    run_monitoring_cycle(trigger="scheduled")


def start_scheduler() -> None:
    global _scheduler
    if not config.MONITOR_ENABLED or _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
    _scheduler.add_job(_scheduled_job, "interval", minutes=config.MONITOR_INTERVAL_MINUTES, id=JOB_ID,
                       max_instances=1, coalesce=True, replace_existing=True)
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def scheduler_status() -> dict:
    job = _scheduler.get_job(JOB_ID) if _scheduler else None
    return {
        "enabled": config.MONITOR_ENABLED,
        "running": bool(_scheduler and _scheduler.running),
        "interval_minutes": config.MONITOR_INTERVAL_MINUTES,
        "next_run_at": job.next_run_time if job else None,
        "check_in_progress": is_running(),
        "stale_after_hours": config.STALE_AFTER_HOURS,
    }
