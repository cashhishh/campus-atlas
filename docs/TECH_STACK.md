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
| google-genai (Google Gen AI SDK) | 3.3.0 | Official Gemini client: primary AI provider for grounded answers and change summaries; Google Search grounding tool for the experimental web research |
| pytest | 9.2.0 | 56 automated tests and the generated results table |
| ChromaDB (optional) | ≥ 0.5 (`requirements-ai.txt`) | Semantic vector store, used automatically when installed; otherwise the JSON + BM25 store |

## AI

The provider chain is **Gemini → Groq → grounded demo (extractive) answer**. Set `LLM_PROVIDER=groq` to make Groq primary. Every provider receives the same strict grounding prompt and must cite sources as [S1], [S2] …

| Service / model | Purpose |
|---|---|
| Google Gemini API via `google-genai` (primary) | Context-only answers and change summaries. Default `GEMINI_MODEL=gemini-3.5-flash`, fallback `gemini-3.1-flash-lite` (`gemini-2.5-flash` is retired for new keys; `gemini-3.8-flash` was overloaded with 503/504 on 16 Nov). 10 s per call (the API minimum); one short retry on 429, then a 60 s cool-down for that model; on timeout/5xx it moves to the next model, then to Groq |
| Gemini + Google Search grounding tool | Experimental "live web research" button: prefers official domains (.ac.in, .edu.in, .gov.in, nirfindia.org), shows source URLs with verification badges, and is labelled "not source-grounded" |
| Groq Cloud API (OpenAI-compatible, fallback) | Used when Gemini fails or has no key. `qwen/qwen3.8-27b` (active), fallbacks `openai/gpt-oss-120b`, `openai/gpt-oss-20b` |
| Grounded demo response (no LLM) | Extractive sentences from the retrieved sources with [S#] citations. Used when no provider is available |
| `groq/compound-mini` (retired from the UI) | First-defence web research. `server/apiPlugin.mjs` is kept in the repo but no longer mounted |
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
