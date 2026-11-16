r"""Rebuild the local database and chunk store from scratch, then run one full ingestion.

Use after changing extraction/cleaning logic, so the change feed only shows real
website changes. Usage (from backend/):  .venv\Scripts\python -m scripts.rebuild_index
"""
from app.database import Base, engine, init_db
from app.models import models  # noqa: F401
from app.services import vector_store
from app.monitoring.scheduler import run_monitoring_cycle

if __name__ == "__main__":
    Base.metadata.drop_all(bind=engine)
    vector_store._save([])
    init_db()
    run = run_monitoring_cycle(trigger="pilot-ingestion")
    print({k: v for k, v in run.items() if k != "details"})
    for d in run["details"]:
        if d["status"] == "ERROR":
            print("ERROR", d["source_name"], "->", d["error"])
