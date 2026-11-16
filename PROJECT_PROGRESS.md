# CampusAtlas — Project Progress

## Phase 1 — Foundation — Completed
- Modular FastAPI + React architecture; the React UI now calls FastAPI through a Vite proxy
- SQLite schema with a swappable database URL and a forward-only column migration
- 53-college registry (MAIT, DTU, NSUT, IGDTUW, BPIT, GTBIT, MSIT and USICT among them)
- Source Registry with authority, status, hashes, timestamps and failure reasons

## Phase 2 — Ingestion — Completed
- Public HTML fetch and boilerplate cleaning; PDF text extraction with PyMuPDF
- Word-boundary chunking with overlap, content versions and ingestion history
- 42 real official sources for 8 pilot colleges, plus the 4 labelled `DEMO DATA` sources

## Phase 3 — Retrieval — Completed
- BM25 local store (ChromaDB used automatically when installed); source metadata travels with chunks
- College detection, relevance threshold and the enforced grounding rule ("Not available in indexed sources.")
- Context-only Groq answers with [S#] citations; extractive answer without a key

## Phase 4 — Decision Support — Completed
- Evidence-aware comparison built from indexed sources
- Explainable preference scoring; branch points require indexed evidence

## Phase 5 — Change Intelligence — Completed
- Automated monitoring scheduler (APScheduler), "Run check now" endpoint and button, monitoring run log
- Content versions, passage diffs, Groq or deterministic change summaries, Change Feed page
- Source verification (Official / Third-party / Unverified) and freshness (last checked, last changed, stale)
- Analytics dashboard and query logging with latency

## Testing — Completed
- 48 pytest tests (unit + FastAPI TestClient): see `docs/test_results.md`

## Future work
- OCR for scanned PDFs, headless fetching for JavaScript-only sites, semantic embeddings, alerts, source discovery
