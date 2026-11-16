# CampusAtlas — Project Progress

## Phase 1 — Foundation — Completed
- Modular FastAPI + React architecture
- SQLite schema designed for a swappable database URL
- 50-college basic registry; no detailed claims are seeded
- Source Registry with authority, status, hashes and timestamps

## Phase 2 — Ingestion — Completed for configured sources
- Public HTML fetch and boilerplate cleaning
- Public PDF text extraction with PyMuPDF
- Text chunk creation, content versions and ingestion history
- Four labelled `DEMO DATA` configured sources for first-defense demonstration

## Phase 3 — Retrieval — Completed
- ChromaDB integration with a dependable local JSON fallback
- Retrieval ranked by local relevance; source metadata travels with chunks
- Strictly context-only Groq provider path; source-grounded demo response without a key

## Phase 4 — Decision Support — Completed
- Evidence-aware comparison UI
- Explainable preference scoring, without invented match percentages

## Phase 5 — Change Intelligence & Scale — In Progress / Upcoming
- Basic hash-based `NEW_SOURCE_CONTENT` and `CONTENT_UPDATED` events: completed
- Automated monitoring scheduler: upcoming
- Semantic change summaries, source verification, large-scale discovery and analytics: coming soon
