# CampusAtlas — Technology Stack

These are the versions installed and tested on 16 Nov 2026. Backend versions come from `backend/.venv`; frontend versions come from `node_modules`.

## Backend (Python 3.12.6)

| Library / tool | Version | Purpose in CampusAtlas |
|---|---|---|
| FastAPI | 0.163.1 | REST API (26 endpoints), request validation and lifespan startup/shutdown |
| Starlette | 1.10.0 | ASGI toolkit under FastAPI; `TestClient` for API tests |
| Uvicorn | 0.54.0 | ASGI server (`uvicorn app.main:app`) |
| Pydantic | 2.14.3 | Request bodies (`Ask`, `NewSource`, `MonitorRequest`, …) |
| SQLAlchemy | 2.1.8 | ORM for 7 tables; swappable `DATABASE_URL` (SQLite by default) |
| SQLite | bundled with Python | Persistent store for registry, sources, versions, events, runs and query logs |
| APScheduler | 3.11.3 | Background interval job that re-checks every source (`MONITOR_INTERVAL_MINUTES`) |
| httpx | 0.28.1 | Fetching college pages/PDFs and calling Groq |
| truststore | 0.10.5 | Uses the operating-system certificate store (fixes sites with incomplete TLS chains, e.g. NSUT) |
| BeautifulSoup4 | 4.15.0 | HTML parsing and boilerplate removal |
| PyMuPDF (`pymupdf`) | 2.1 | PDF text extraction (DTU programmes, NIRF data PDFs) |
| python-dotenv | 1.2.4 | Loads `.env` (root and `backend/`) |
| difflib (stdlib) | Python 3.12 | Passage-level diffs between content versions |
| hashlib (stdlib) | Python 3.12 | SHA-256 content hashes for change detection |
| concurrent.futures (stdlib) | Python 3.12 | Parallel fetching during a monitoring run |
| pytest | 9.2.0 | 48 automated tests and the generated results table |
| ChromaDB (optional) | ≥ 0.5 (`requirements-ai.txt`) | Semantic vector store, used automatically when installed; otherwise the JSON + BM25 store |

## AI

| Service / model | Purpose |
|---|---|
| Groq Cloud API (OpenAI-compatible chat completions) | Context-only answers and change summaries |
| `qwen/qwen3.8-27b` (active), fallbacks `openai/gpt-oss-120b`, `openai/gpt-oss-20b` | Chosen automatically when the configured `GROQ_MODEL` is retired |
| `groq/compound-mini` | Experimental web-research mode, kept from the first defence and labelled "not source-grounded" |
| BM25 (own implementation) | Keyword relevance ranking in the local chunk store |

## Frontend (Node v22.17.1)

| Library / tool | Version | Purpose |
|---|---|---|
| React / React DOM | 19.2.8 | UI components and rendering |
| React Router DOM | 7.18.3 | Client-side routes (`/ask`, `/compare`, `/updates`, `/analytics`, `/admin`, …) |
| TypeScript | 7.0.2 | Static typing (`npm run build` type-checks first) |
| Vite | 8.2.2 | Dev server, `/api` proxy to FastAPI, production build |
| @vitejs/plugin-react | 6.1.1 | JSX/Fast Refresh |
| lucide-react | 1.37.0 | Icons (badges, metrics, buttons) |
| Google Fonts: Inter, Playfair Display | — | Typography |
| Charts | own CSS/SVG components | Bar lists, stacked timeline and segmented bars on the Analytics page (no chart library) |

## Tooling

| Tool | Version | Purpose |
|---|---|---|
| Git | 2.47.0 | Version control (one commit per step) |
| npm | 10.9.2 | Frontend dependency management |
| pip / venv | 24.2 | Backend virtual environment (`backend/.venv`) |
