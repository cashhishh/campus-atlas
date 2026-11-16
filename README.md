# CampusAtlas

CampusAtlas is a source-grounded college intelligence platform (B.Tech minor project). It registers official college sources, ingests and versions them, monitors them for changes, and answers questions **only** from indexed sources, with verification and freshness on every citation.

## Run it (Windows, from the project root)

First time only:

```powershell
npm install
python -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements-dev.txt
cd backend; .venv\Scripts\python -m scripts.ingest_pilot; cd ..
```

Every time, use two terminals:

```powershell
# Terminal 1 — API (http://127.0.0.1:8000, docs at /docs)
cd backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000

# Terminal 2 — UI (http://localhost:5173)
npm run dev
```

Useful commands (inside `backend\`):

```powershell
.venv\Scripts\python -m scripts.ingest_pilot   # seed + one full monitored ingestion of all sources
.venv\Scripts\python -m pytest -q              # 48 tests -> regenerates ..\docs\test_results.md
.venv\Scripts\python -m scripts.benchmark      # latency over 20 queries -> ..\docs\performance.json
```

If the API is not running, the UI falls back to the first-defence offline mode (static registry and DEMO knowledge).

## Configuration (`.env` in the root and/or `backend/`)

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | Primary AI provider (`gemini` or `groq`); the other is the fallback, then the grounded demo answer |
| `GEMINI_API_KEY` | – | Google Gemini key (primary provider + experimental web research) |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model; missing models fall back to `GEMINI_FALLBACK_MODELS` |
| `GROQ_API_KEY` | – | Groq fallback for context-only answers and change summaries. Without any key, answers are extractive |
| `GROQ_MODEL` | – | Preferred Groq model; retired models fall back to `GROQ_FALLBACK_MODELS` automatically |
| `MONITOR_ENABLED` | `true` | Start the APScheduler monitoring job |
| `MONITOR_INTERVAL_MINUTES` | `360` | How often every source is re-checked |
| `STALE_AFTER_HOURS` | `72` | A source not checked for this long is flagged stale |
| `DATABASE_URL` | `sqlite:///./campusatlas.db` | Any SQLAlchemy URL |
| `VECTOR_DRIVER` | `auto` | `auto` (Chroma if installed), `json` (BM25) or `chroma` |

## What is in each phase

See [PROJECT_PROGRESS.md](PROJECT_PROGRESS.md) and [docs/](docs/):
[progress since the first defence](docs/PROGRESS_SECOND_DEFENCE.md) · [architecture](docs/ARCHITECTURE.md) · [API](docs/API.md) · [tech stack](docs/TECH_STACK.md) · [test results](docs/test_results.md) · [code snippets](docs/CODE_SNIPPETS.md)

## Data honesty

- Every fact comes from an ingested source and is shown with a citation. Cutoffs, fees, placement figures and ranks are never typed in.
- Sources that cannot be fetched (IGDTUW's JavaScript-only site, scanned PDFs) stay registered, are marked missing, and questions about them return **"Not available in indexed sources."**
- The four first-defence sources keep their **DEMO DATA** label. The "Simulate change" button only works on them, and its text says it is simulated.
- When the index has no answer, CampusAtlas fetches the college's official pages on demand (then NIRF, then a labelled third-party page), ingests them and answers with citations. If nothing is found it says which pages it checked and links to the official site. It never answers from model memory. Disable with `LIVE_FETCH_ENABLED=false`.
- "Live web research" (Gemini + Google Search) is a clearly labelled, experimental, *not source-grounded* comparison; it lists official domains first.
