r"""Fetch NIRF ranking rows + data PDFs for the pilot colleges and store structured facts.

Usage (from backend/):  .venv\Scripts\python -m scripts.build_facts
"""
import json

from app.database import SessionLocal, init_db
from app.facts.nirf_facts import build

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    print(json.dumps(build(db), indent=1, default=str))
