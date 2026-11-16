from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .ai import groq_client
from .api.routes import router
from .config import FRONTEND_ORIGINS
from .database import init_db
from .monitoring.scheduler import scheduler_status, start_scheduler, stop_scheduler
from .services.vector_store import driver_name


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
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
            'llm': 'groq' if groq_client.is_configured() else 'extractive (no key)', 'monitor': scheduler_status()}
