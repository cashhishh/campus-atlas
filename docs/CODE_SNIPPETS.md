# Code Snippets for the Implementation Chapter

These are the eight snippets that best represent CampusAtlas, in the order the report should present them. For each one: copy the given line range, then use the caption and talking point. All paths are relative to `backend/` except #8.

| # | Snippet | File and lines | Caption / what it shows |
|---|---|---|---|
| 1 | **Grounding rule** in `answer()` | `app/retrieval/rag.py` lines 104–147 (the key branch is `if not hits:` at line 114) | If retrieval finds no relevant chunk, the function returns "Not available in indexed sources." and the LLM is never called. Otherwise the top 5 chunks become numbered sources [S1…] and the answer cites them. This is the project's central guarantee (tests T22–T25). |
| 2 | **Change detection with versions, diff and summary** in `process_text()` | `app/ingestion/pipeline.py` lines 164–232 | Normalise → SHA-256 → compare with the stored hash. On a change: store a `ContentVersion`, re-chunk, replace the source's chunks, diff against the previous version and write an `UpdateEvent` with a summary. |
| 3 | **Monitoring cycle** in `run_monitoring_cycle()` + `start_scheduler()` | `app/monitoring/scheduler.py` lines 35–91 and 113–120 | A run lock, a `MonitorRun` row, parallel fetching in a thread pool, sequential DB processing, per-source error capture, and a final status of SUCCESS, PARTIAL or FAILED. The APScheduler interval job reuses the same function. |
| 4 | **Source verification rules** in `classify_source()` + `freshness()` | `app/verification/rules.py` lines 47–82 | Deterministic, explainable trust: registered college domain → official bodies (NIRF, AICTE, UGC…) → `.ac.in/.edu.in/.gov.in` → known aggregators (third-party) → unverified. Freshness flags sources not checked within 72 h. |
| 5 | **Passage diff and summariser** in `compute_diff()` + `summarize_change()` | `app/change_detection/diff.py` lines 16–75 | `difflib.SequenceMatcher` over sentence-like passages gives added and removed lists plus a unified diff. Groq writes a 1–2 sentence summary from only those passages; otherwise a deterministic summary is used. |
| 6 | **BM25 retrieval with coverage score** in `_bm25()` + `query()` | `app/services/vector_store.py` lines 154–199 | A from-scratch BM25 (k1 = 1.4, b = 0.75) mixed with query-term coverage gives a 0–1 relevance score. The coverage value drives the grounding threshold. |
| 7 | **Word-boundary chunking with overlap** in `chunk_text()` | `app/ingestion/pipeline.py` lines 100–120 | Builds ~700-character chunks that never split a word and overlap by ~120 characters, so facts at chunk edges stay retrievable (tests T07–T10). |
| 8 | **Evidence-aware compare and explainable scoring** in `recommend()` + `compare_evidence()` | `backend/app/recommendations/engine.py` lines 25–77; UI in `frontend/src/pages/backendViews.tsx` (`EvidenceTable`) | Each score point has a reason. Branch points are given only when an indexed source mentions the branch. The compare table shows the best indexed sentence per topic, or "Not available in indexed sources." |

## Optional extras (if the chapter needs more)

- `app/ai/groq_client.py`, `chat()`: retired-model fallback and HTTP 429 retry, which make a third-party LLM dependency resilient.
- `tests/conftest.py`: the `meta` marker and the `pytest_sessionfinish` hook that generate `docs/test_results.md` automatically.
- `frontend/src/pages/phase5.tsx`, `MonitorPanel`: the "Run check now" button, the sources table with badges and the run log.
