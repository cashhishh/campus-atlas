"""Seed the registry (incl. pilot sources) and run one full monitoring/ingestion cycle.

Usage (from backend/):  .venv\Scripts\python -m scripts.ingest_pilot
"""
import json

from app.database import init_db
from app.monitoring.scheduler import run_monitoring_cycle

if __name__ == "__main__":
    init_db()
    run = run_monitoring_cycle(trigger="pilot-ingestion")
    print(json.dumps({k: v for k, v in run.items() if k != "details"}, default=str, indent=2))
    for d in run.get("details", []):
        print(f"{d['status']:9} {d['college_id']:7} {d['source_name']}" + (f"  -> {d['error']}" if d.get("error") else ""))
