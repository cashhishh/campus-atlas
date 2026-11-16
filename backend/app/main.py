import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from . import config
from .ai import llm
from .api.routes import router
from .config import FRONTEND_ORIGINS
from .database import init_db
from .monitoring.scheduler import run_monitoring_cycle, scheduler_status, start_scheduler, stop_scheduler
from .services import vector_store
from .services.vector_store import driver_name

log = logging.getLogger("campusatlas")
# React build: FRONTEND_DIST, else frontend/dist next to backend/ (local) or /app/frontend/dist (Docker).
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", config.ROOT_DIR / "frontend" / "dist"))


def _bootstrap_if_empty() -> None:
    """Fresh deployment (empty chunk store): run the pilot ingestion once, in the background."""
    if not config.MONITOR_ENABLED or vector_store.count()[0] > 0:
        return

    def run():
        log.info("Empty index - running initial pilot ingestion in the background")
        result = run_monitoring_cycle(trigger="pilot-ingestion")
        log.info("Initial ingestion finished: %s", {k: v for k, v in result.items() if k != "details"})

    threading.Thread(target=run, name="initial-ingestion", daemon=True).start()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()  # creates tables and seeds colleges/sources (idempotent)
    _bootstrap_if_empty()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title='CampusAtlas API', version='0.2.0', lifespan=lifespan,
              description='Source-grounded college intelligence: registry, ingestion, retrieval, decision support and change intelligence.')
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS + ['http://127.0.0.1:5173'], allow_credentials=True,
                   allow_methods=['*'], allow_headers=['*'])
app.include_router(router, prefix='/api')


@app.get('/health')
def health():
    return {'status': 'ok', 'product': 'CampusAtlas', 'version': app.version, 'vector_driver': driver_name(),
            'llm': (llm.configured_providers() or ['demo (no key)'])[0], 'llm_order': llm.configured_providers(), 'monitor': scheduler_status()}


# Single-service deployment: serve the built React app; any non-API path falls back to index.html
# so client-side routes (react-router) work on refresh. Skipped when there is no build (local dev uses Vite).
if (FRONTEND_DIST / "index.html").exists():
    _dist = FRONTEND_DIST.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        file = (_dist / full_path).resolve()
        if full_path and file.is_file() and file.is_relative_to(_dist):
            return FileResponse(file)
        return FileResponse(_dist / "index.html")
