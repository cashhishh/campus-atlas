# CampusAtlas — Test Results

Generated automatically by `pytest` on 2026-11-16 18:18 (offline: temporary DB, no network, no Groq).

**48 / 48 tests passed.**

| Test ID | Module | Description | Expected | Actual | Pass/Fail |
|---|---|---|---|---|---|
| T01 | Ingestion (HTML) | clean_html strips nav/header/footer/script/style boilerplate | Body text kept; boilerplate removed | 233 chars kept, 0 boilerplate strings | Pass |
| T02 | Ingestion (HTML) | End-to-end HTML ingestion of a new source | NEW_SOURCE_CONTENT event, version 1, chunks indexed, title extracted | NEW_SOURCE_CONTENT, v1, 1 chunk(s) | Pass |
| T03 | Ingestion (PDF) | PyMuPDF extracts text from a PDF byte stream | Extracted text contains the PDF sentence; page count 1 | 80 chars, 1 page | Pass |
| T04 | Ingestion (PDF) | End-to-end ingestion of a PDF source (content-type sniffed) | doc_type=PDF on chunks; text searchable | 1 PDF chunk(s) indexed | Pass |
| T05 | Ingestion | Unreachable source is kept but marked missing | status FETCH_FAILED, last_error set, FAILED ingestion event | status=FETCH_FAILED, event=FAILED | Pass |
| T06 | Ingestion | Near-empty extraction (JS-only page) is rejected, not indexed | IngestionError raised; no version stored | IngestionError raised, 0 versions | Pass |
| T07 | Chunking | Chunks respect the size limit and never split a word | Every chunk <= 700 chars; all tokens are whole words | 25 chunks, max 699 chars | Pass |
| T08 | Chunking | Consecutive chunks overlap to preserve context | Tail of chunk i reappears at start of chunk i+1 | overlap verified on 24 boundaries | Pass |
| T09 | Chunking | Empty and tiny inputs produce no chunks | [] for empty / whitespace / below min length | [] for all three | Pass |
| T10 | Chunking | No text is lost: every word appears in some chunk (incl. legacy chunks()) | 100% word coverage | 100% coverage | Pass |
| T11 | Change detection | Re-checking identical content creates no change event | changed=False; still 1 update event | changed=False, 1 event | Pass |
| T12 | Change detection | Changed content: new hash -> CONTENT_UPDATED with stored diff and summary | Version 2, diff has '+' lines, deterministic summary lists additions | CONTENT_UPDATED, +2/-1 passages | Pass |
| T13 | Change detection | Hash ignores whitespace-only differences | Identical SHA-256 for reformatted text | equal for whitespace, different for words | Pass |
| T14 | Change detection | compute_diff separates added and removed passages | 1 added, 1 removed, similarity < 1 | added=['Beta TWO changed.'], removed=['Beta two.'] | Pass |
| T15 | Change detection | Old chunks are replaced on update (no stale text retrievable) | Only new-version chunks remain for the source | versions in store: [2] | Pass |
| T16 | Change detection | Change simulation is limited to DEMO DATA sources | 400 for a real source; CONTENT_UPDATED for a demo source | real=400, demo=CONTENT_UPDATED | Pass |
| T17 | Retrieval | Tokenizer removes stopwords and expands abbreviations | 'Does MAIT offer ECE?' -> mait, offer, ece, electronic, communication | ['mait', 'offer', 'ece', 'electronic', 'communication'] | Pass |
| T18 | Retrieval | BM25 ranks the relevant chunk first | Top hit for 'hostel accommodation' is the BPIT hostel chunk | top=bpit score=1.0 | Pass |
| T19 | Retrieval | College filter restricts the search space | Query scoped to gtbit never returns usict chunks | 1 hit(s), all gtbit | Pass |
| T20 | Retrieval | College detection uses aliases with word boundaries | MAIT/IGDTUW detected; 'IIIT Delhi' is not mistaken for 'IIT Delhi' | aliases + boundaries OK | Pass |
| T21 | Retrieval | Intent classification | fees / placements / comparison / rankings recognised | 4/4 intents correct | Pass |
| T22 | Grounding rule | No relevant context -> fixed refusal and the LLM is NEVER called | 'Not available in indexed sources.', grounded=False, 0 sources, 0 LLM calls | answer='Not available in indexed sources.', llm_calls=0 | Pass |
| T23 | Grounding rule | With context, the extractive answer cites its source | Answer contains [S1]; citation has verification + freshness | mode=extractive, cites S1 (Official) | Pass |
| T24 | Grounding rule | LLM receives only retrieved context, numbered as sources | Prompt contains SOURCES block with the chunk; question included | prompt = question + 1 retrieved source only | Pass |
| T25 | Grounding rule | LLM failure falls back to an extractive answer from the same sources | mode=extractive with notice; still cited | fallback extractive + notice | Pass |
| T26 | Compare scoring | Location preference adds +20 with an explanation | Delhi college scores 20 and explains why; others 0 | mait=20, others=[0, 0] | Pass |
| T27 | Compare scoring | Branch points only when an indexed source mentions the branch | +30 with evidence; 0 + 'needs confirmation' without | nitk=30 (evidence), mait=0 (no evidence) | Pass |
| T28 | Compare scoring | Scores are bounded, sorted descending and explainable | 0 <= score <= 80; sorted; every result has reasons | scores=[80, 60, 45] | Pass |
| T29 | Compare evidence | Topics without indexed evidence say 'Not available in indexed sources.' | Fees cell unavailable; programmes cell cites source | Programmes=cited, Fees=Not available | Pass |
| T30 | Verification | .ac.in / .edu.in / .gov.in domains are official | OFFICIAL | 3/3 OFFICIAL | Pass |
| T31 | Verification | NIRF (nirfindia.org) is official | OFFICIAL with 'Government / statutory body' | Government / statutory body (nirfindia.org) | Pass |
| T32 | Verification | College's registered domain (non-.ac.in) is official | msit.in -> OFFICIAL only when it is MSIT's registered domain | with domain=OFFICIAL, without=UNVERIFIED | Pass |
| T33 | Verification | Aggregators are third-party; unknown domains unverified | shiksha=THIRD_PARTY, random blog=UNVERIFIED | THIRD_PARTY, THIRD_PARTY, UNVERIFIED | Pass |
| T34 | Verification | Look-alike domains are not trusted | mait.ac.in.evil.com and fakeac.in -> not OFFICIAL | both rejected | Pass |
| T35 | Freshness | Fresh / stale / never-checked states | 2h=FRESH, 100h=STALE (72h limit), None=NEVER_CHECKED | FRESH, STALE, NEVER_CHECKED | Pass |
| T36 | API | GET /health reports status, vector driver and scheduler | 200, status=ok | 200, driver=Local JSON fallback (BM25) | Pass |
| T37 | API | GET /api/colleges lists the registry incl. new pilot colleges | >= 53 colleges incl. mait, igdtuw, bpit, gtbit | 53 colleges | Pass |
| T38 | API / Scheduler | POST /api/monitor/run checks sources and logs the run | Run SUCCESS; 1 checked; run listed in /api/monitor/runs | run #1 SUCCESS, 1 change, 113 ms | Pass |
| T39 | API / Scheduler | A second run detects an update and links the event to the run | CONTENT_UPDATED event with monitor_run_id; feed shows summary | event #3 linked to run #3 | Pass |
| T40 | API / Scheduler | Failed source in a run -> run PARTIAL, error counted, source marked missing | status PARTIAL, errors=1, source FETCH_FAILED | PARTIAL, errors=1 | Pass |
| T41 | API / Scheduler | Concurrent runs are prevented | 409 while a run holds the lock | 409 Conflict | Pass |
| T42 | API / Scheduler | Scheduler job registers with the configured interval | Job present with interval; status reports next_run_at | next_run_at set, interval=15 min | Pass |
| T43 | API | POST /api/ask: validation, refusal and query logging | 422 for empty; unknown topic refused; query appears in analytics | 422, refusal, logged | Pass |
| T44 | API | GET /api/sources exposes verification, freshness and DEMO label | Every source has verification.status and freshness.state | 50 sources enriched | Pass |
| T45 | API | GET /api/analytics returns dashboard aggregates | totals, timeline (14 days), breakdowns, top_queries | 50 sources, 4 change events | Pass |
| T46 | API | Input validation on sources and compare | Bad URL -> 422; unknown colleges -> 422 | 422, 422 | Pass |
| T47 | API | POST /api/compare/evidence returns a topic x college table | Topics listed; unavailable cells say 'Not available in indexed sources.' | 0/12 cells with evidence | Pass |
| T48 | AI client | Groq client retries on 429 and skips retired models | Retired model skipped, 429 retried once, answer returned | calls=['retired/model', 'good/model', 'good/model'] | Pass |

## Performance (20 sample queries on the real pilot index)

Measured 2026-11-16 18:18 on the development laptop · 394 chunks · Local JSON fallback (BM25) · LLM: Groq `qwen/qwen3.8-27b`.

| Metric | Value |
|---|---|
| Average retrieval latency (median of 5 runs per query) | 18.1 ms |
| 95th percentile retrieval latency | 32.5 ms |
| Average extractive answer latency (no LLM) | 19.2 ms |
| Average AI answer latency (retrieval + Groq, 16 LLM calls) | 2657.6 ms |
| 95th percentile AI answer latency | 4818.5 ms |
| Grounded answers / refusals ("Not available in indexed sources.") | 17 / 3 |

Refusals happen without an LLM call when retrieval finds nothing (≈ retrieval time only), so they are excluded from the AI-latency average. AI latency is dominated by the Groq network round trip; on the free tier some calls wait for a 429 rate-limit retry (up to 3 s) and a call that still fails falls back to the extractive answer (mode "extractive"), which is why the p95 is ~5 s while uncontended calls take ~1–1.5 s.

| # | Query | Retrieval (ms) | AI answer (ms) | Mode | Grounded | Sources |
|---|---|---|---|---|---|---|
| 1 | Does MAIT offer ECE? | 7.3 | 2178.2 | groq | Yes | 4 |
| 2 | What is the fee structure at MAIT? | 22.9 | 1285.1 | groq | Yes | 1 |
| 3 | Does MAIT have a hostel? | 32.5 | 1064.8 | groq | Yes | 3 |
| 4 | Tell me about MAIT placements | 22.8 | 1527.4 | groq | Yes | 3 |
| 5 | What is the NIRF rank band of MAIT? | 35.8 | 1577.1 | groq | Yes | 1 |
| 6 | What B.Tech programmes does DTU offer? | 31.5 | 2010.5 | groq | Yes | 2 |
| 7 | What is the median salary at DTU? | 30.7 | 1128.1 | groq | Yes | 2 |
| 8 | Tell me about the DTU ECE department | 28.9 | 3922.7 | groq | Yes | 1 |
| 9 | What is the history of DTU? | 30.3 | 4818.5 | groq | Yes | 1 |
| 10 | Tell me about NSUT hostels | 10.6 | 4986.5 | groq | Yes | 1 |
| 11 | How do UG admissions work at NSUT? | 13.5 | 3889.8 | extractive | Yes | 2 |
| 12 | What is the NIRF rank of NSUT? | 6.0 | 418.4 | groq | No (refused) | 0 |
| 13 | What is the hostel fee at BPIT? | 6.1 | 3496.1 | extractive | Yes | 2 |
| 14 | What is the placement record of BPIT? | 4.6 | 1233.6 | groq | Yes | 1 |
| 15 | Who recruits from GTBIT? | 28.9 | 4353.3 | groq | Yes | 1 |
| 16 | How do admissions work at GTBIT? | 7.6 | 4357.5 | groq | Yes | 2 |
| 17 | What facilities does MSIT have? | 30.7 | 3968.0 | groq | Yes | 3 |
| 18 | What is the intake of USICT B.Tech CSE? | 2.1 | 3692.3 | groq | Yes | 2 |
| 19 | Tell me about IGDTUW placements | 0.7 | 2.2 | none | No (refused) | 0 |
| 20 | What is the swimming pool size at DTU? | 8.3 | 16.5 | none | No (refused) | 0 |

