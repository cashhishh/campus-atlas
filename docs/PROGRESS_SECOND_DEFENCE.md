# CampusAtlas — Progress for the Second Defence (17 Nov 2026)

## Headline numbers

| Metric | First defence (29 Aug) | Second defence (16 Nov) |
|---|---|---|
| Colleges in registry | 50 | **53** (+ IGDTUW, BPIT, GTBIT) |
| Pilot colleges with real official sources | 0 | **8** registered, **7** indexed (MAIT, DTU, NSUT, BPIT, GTBIT, MSIT, USICT); IGDTUW kept and marked missing |
| Registered sources | 4 (all `DEMO DATA`) | **46** = 42 real official sources + 4 `DEMO DATA` |
| Sources fetched and indexed successfully | 0 real | **40 real** (HTML + PDF, incl. 3 NIRF data PDFs) |
| Indexed text chunks | 4 | **341** |
| Content versions / change events stored | 0 / hash only | versioned, with diffs and summaries |
| Automated tests | 0 | **48 / 48 passing** (pytest + FastAPI TestClient) |
| API endpoints (FastAPI) | 13 | **26** |
| Average retrieval latency (20 queries) | not measured | **4.6 ms** (p95 6.4 ms) |
| Average AI answer latency (retrieval + Groq) | not measured | **1.33 s** avg (p95 3.7 s on the Groq free tier) |

Numbers come from `GET /api/analytics`, `docs/test_results.md` and `docs/performance.json`.

## First defence vs now

| Feature | Status at first defence | Status now |
|---|---|---|
| React UI ↔ FastAPI backend | Not connected: UI used static TypeScript data | **Connected** through a Vite proxy (`/api` → FastAPI), with an offline fallback |
| College registry | 50 colleges (static + DB) | 53 colleges; seeding is idempotent and adds new colleges/sources safely |
| Source registry | 4 labelled DEMO sources | 42 real official sources + the 4 DEMO sources (labels kept) |
| HTML ingestion | Implemented, used only on DEMO text | Live on 36 real pages; boilerplate removal extended |
| PDF ingestion (PyMuPDF) | Implemented, never run on a real PDF | Live on 4 real PDFs (DTU programmes, NIRF 2025 data for DTU/NSUT, GTBIT NIRF); scanned PDFs detected and marked missing |
| Chunking | Fixed 700-char slices (cut words) | Word-boundary chunks with 120-char overlap |
| Retrieval | Returned every chunk, even irrelevant ones | BM25 ranking, college detection (aliases), coverage threshold, synonyms; menu/link-list boilerplate filtered at ingestion |
| Grounding rule | Claimed; "Live" mode was ungrounded web search | **Enforced and tested**: no retrieved context → no LLM call → "Not available in indexed sources." |
| LLM | Configured model had been retired by Groq (every call failed) | Context-only Groq answers with [S1] citations, automatic model fallback, 429 retry, extractive fallback |
| Hash change detection | `NEW_SOURCE_CONTENT` / `CONTENT_UPDATED` | Kept, plus stored content versions |
| Automated monitoring scheduler | Upcoming | **Done**: APScheduler job (configurable interval), "Run check now" API + button, run log |
| Change summaries + diffs | Coming soon | **Done**: passage-level diff stored per event; Groq summary when a key is set, deterministic diff summary otherwise |
| Change Feed / Updates page | "Coming soon" placeholder | **Done**: filterable feed, summary, event type, diff viewer |
| Source verification | Not present | **Done**: Official / Third-party / Unverified by domain rules; badges in sources and citations |
| Freshness | Not present | **Done**: last checked, last changed, stale flag (72 h) |
| Analytics dashboard | Not present | **Done**: totals, change events over time, verification/freshness/authority breakdowns, chunks per college, most-asked questions, latency |
| Query logging | Not present | Every `/api/ask` call logged with intent, outcome and latency |
| Compare | Static DEMO text per college | Evidence table retrieved live per topic (programmes, admissions, fees, placements, campus, rankings); "Not available in indexed sources." when absent |
| Preference scoring | Branch points given to every college | Branch points only when an indexed source mentions the branch |
| Missing data handling | — | Unfetchable sources kept, marked `FETCH_FAILED` with the reason; answers say "Not available in indexed sources." |
| Tests | None | 48 tests; results table in `docs/test_results.md` |
| Version control | Not a git repository | Git history, one commit per step |

## What was deliberately not done

- No cutoffs, fees, placement figures or ranks were typed in. Every figure the app shows comes from an ingested official page or PDF, with a citation.
- IGDTUW's website is a JavaScript-only app, so plain fetching returns no text. The source is kept and marked missing rather than filled with third-party data.
- NSUT's fee schedules are Google Drive files, and BPIT's fee notice is a scanned image PDF. Both are therefore "Not available in indexed sources." OCR is listed as future work.
- ChromaDB integration is kept but optional. The demo runs on the deterministic BM25 JSON store, so it needs no model download.

## Future work

OCR for scanned PDFs, headless-browser fetching for JavaScript sites (IGDTUW), semantic embeddings via ChromaDB, cross-source conflict detection, email/push alerts for watched colleges, and automatic source discovery.
