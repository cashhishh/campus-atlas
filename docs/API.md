# CampusAtlas — API Reference

The backend base URL is `http://127.0.0.1:8000`. In the dev UI the same paths are reached through the Vite proxy at `http://localhost:5173/api/...`. FastAPI also serves interactive docs at `http://127.0.0.1:8000/docs`.

Timestamps are UTC ISO-8601. Errors use FastAPI's `{"detail": "..."}` shape.

## Health

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Status, version, vector driver, AI provider order (`llm`, `llm_order`) and scheduler status |

## Colleges

| Method | Path | Description |
|---|---|---|
| GET | `/api/colleges?q=&category=` | List the registry, with optional name search and category filter |
| GET | `/api/colleges/{id}` | One college with its sources (verification, freshness, chunk counts), total chunks and the 5 most recent updates. 404 if unknown |

## Sources

| Method | Path | Description |
|---|---|---|
| GET | `/api/sources?college_id=` | All sources, each with `verification {status,label,reason}`, `freshness {state,stale,checked_hours_ago,…}`, `is_demo`, `chunks`, `last_error` |
| POST | `/api/sources` | Register a source. Body: `{college_id, source_name, source_url, source_type?, authority_level?}`. 422 for a non-http(s) URL; 404 for an unknown college |
| GET | `/api/sources/{id}` | One source (enriched) |
| GET | `/api/sources/{id}/versions` | Stored content versions (number, hash, size, preview) |
| POST | `/api/sources/{id}/disable` | Stop monitoring a source |
| POST | `/api/sources/{id}/enable` | Resume monitoring |
| POST | `/api/sources/{id}/ingest` | Fetch and ingest one source now. Returns `{changed, chunks, change_type?, summary?}`. 400 with the reason on failure |
| GET | `/api/verification/check?url=&college_id=` | Classify any URL as Official / Third-party / Unverified |

## Monitoring (Phase 5)

| Method | Path | Description |
|---|---|---|
| POST | `/api/monitor/run` | **Run check now.** Optional body `{source_ids: [..]}`. Returns the run with per-source `details`. 409 if a run is already in progress |
| GET | `/api/monitor/status` | Scheduler state: `enabled, running, interval_minutes, next_run_at, check_in_progress, stale_after_hours, last_run` |
| GET | `/api/monitor/runs?limit=20` | Run log: trigger, status, start/finish, duration, sources checked, changes, errors |
| GET | `/api/monitor/runs/{id}` | One run with per-source results |

## Change feed (Phase 5)

| Method | Path | Description |
|---|---|---|
| GET | `/api/updates?college_id=&change_type=&limit=50` | Change events, newest first: type, timestamp, source, verification, summary, `summary_mode` (`groq`/`deterministic`), added/removed passage counts |
| GET | `/api/updates/{id}` | One event, including the unified `diff` |

## Question answering and decision support

| Method | Path | Description |
|---|---|---|
| POST | `/api/ask` | Body `{query, college_ids?, intent?}`. Returns `{answer, sources[], mode: gemini\|groq\|extractive\|none, provider: gemini\|groq\|demo\|none, model, grounded, intent, college_ids, latency{retrieval_ms,generation_ms,total_ms}, notice?, demo_notice?}`. Each source has `index` (S#), `snippet`, `verification`, `freshness`. No evidence → `answer: "Not available in indexed sources."`, `grounded: false`, no LLM call. Every call is logged |
| POST | `/api/ask` (on-demand lookup) | When the index has no evidence for a single-college, non-comparison question, `live:true` (default) runs: **1** a focused crawl of the official domain (≤15 pages, ≈12 s), **2** the college's row in the official NIRF ranking tables (ranking questions), **3** a curated third-party page (careers360), ingested as THIRD-PARTY. Every answer still comes from ingested text with [S#] citations. Extra fields: `answer_label` ("Fetched live from <domain> · <date>" / "Unverified third-party · …" / "Searched N official/public page(s) · …"), `live {step, domain, topic, checked[], fetched[], cached, elapsed_s}`, `third_party_note`, `official_links[]`. If nothing is found: "Official sources don't publish this information (checked: …)." Results are cached for 24 h per college + topic. With `live:false` the response carries `live_available {college_id, domain, topic}` so the UI can show "Checking <domain>…"; that probe is not logged |
| POST | `/api/compare` | Same as `/ask` with intent `comparison` (not logged) |
| POST | `/api/compare/evidence` | Body `{college_ids: [..≤3]}`. Topic × college table (Programmes, Admissions, Fees, Placements, Campus & facilities, Rankings & accreditation): best indexed sentence + source, or "Not available in indexed sources." 422 if no known college |
| POST | `/api/recommend` | Body `{branch, location, type, hostel, placement}`. Top 8 colleges with `score`, `max_score` (80) and a `why` list. Branch points are given only when an indexed source mentions the branch |

## Analytics and admin

| Method | Path | Description |
|---|---|---|
| GET | `/api/analytics?days=14` | `totals` (colleges, indexed colleges, sources, chunks, ingestion runs/failures, change events, monitor runs, queries, answered rate, average latency), `timeline`, `verification_breakdown`, `authority_breakdown`, `freshness_breakdown`, `status_breakdown`, `chunks_by_college`, `top_queries`, `intent_breakdown`, `recent_runs` |
| GET | `/api/admin/status` | First-defence summary (counts + 8 latest updates) |
| GET | `/api/ingestion-events?limit=30` | Ingestion log with source names and run ids |

## Demo helpers (DEMO DATA only)

| Method | Path | Description |
|---|---|---|
| POST | `/api/demo/seed-knowledge` | Ingest the 4 labelled DEMO sources |
| POST | `/api/demo/sources/{id}/simulate-change` | Append a clearly labelled *simulated* notice to a DEMO source, producing a real `CONTENT_UPDATED` event with diff and summary. 400 for real sources |

## Experimental web research

| Method | Path | Description |
|---|---|---|
| POST | `/api/web-research` | Body `{question}`. Uses **Gemini + the Google Search grounding tool**, *not* the indexed sources. Returns `{answer, sources:[{title,url,domain,verification}], provider:"gemini", model, experimental:true, latency_ms}`, with official domains listed first. 503 with a friendly message if there is no key or Gemini fails |

## Example

```bash
curl -X POST http://127.0.0.1:8000/api/ask -H "Content-Type: application/json" \
     -d '{"query":"Does MAIT offer ECE?"}'
```

```json
{
  "answer": "Yes, MAIT offers Electronics and Communication Engineering … [S1]",
  "mode": "groq", "grounded": true, "intent": "academics", "college_ids": ["mait"],
  "sources": [{"index": 1, "source_name": "MAIT — Courses of Study",
               "source_url": "https://mait.ac.in/index.php/portfolio/course-of-study.html",
               "verification": {"status": "OFFICIAL", "label": "Official", "reason": "Matches the college's registered domain (mait.ac.in)"},
               "freshness": {"state": "FRESH", "checked_hours_ago": 0.4}}],
  "latency": {"retrieval_ms": 7.3, "generation_ms": 1000.2, "total_ms": 1012.0}
}
```
