## Performance (20 sample queries on the real pilot index)

Measured 2026-11-16 18:29 on the development laptop · 341 chunks · Local JSON fallback (BM25) · LLM: Groq `qwen/qwen3.8-27b`.

| Metric | Value |
|---|---|
| Average retrieval latency (median of 5 runs per query) | 4.6 ms |
| 95th percentile retrieval latency | 6.4 ms |
| Average extractive answer latency (no LLM) | 6.0 ms |
| Average AI answer latency (retrieval + Groq, 16 LLM calls) | 1331.7 ms |
| 95th percentile AI answer latency | 3705.0 ms |
| Grounded answers / refusals ("Not available in indexed sources.") | 16 / 4 |

Refusals happen without an LLM call when retrieval finds nothing (≈ retrieval time only), so they are excluded from the AI-latency average. AI latency is dominated by the Groq network round trip; on the free tier some calls wait for a 429 rate-limit retry (up to 3 s), and a call that still fails falls back to the extractive answer (mode = extractive), which raises the p95.

| # | Query | Retrieval (ms) | AI answer (ms) | Mode | Grounded | Sources |
|---|---|---|---|---|---|---|
| 1 | Does MAIT offer ECE? | 4.8 | 921.7 | groq | Yes | 3 |
| 2 | What is the fee structure at MAIT? | 4.5 | 843.8 | groq | Yes | 2 |
| 3 | Does MAIT have a hostel? | 4.4 | 837.9 | groq | Yes | 3 |
| 4 | Tell me about MAIT placements | 4.6 | 639.2 | groq | Yes | 2 |
| 5 | What is the NIRF rank band of MAIT? | 4.8 | 445.8 | groq | Yes | 1 |
| 6 | What B.Tech programmes does DTU offer? | 5.3 | 650.3 | groq | Yes | 2 |
| 7 | What is the median salary at DTU? | 5.5 | 825.5 | groq | Yes | 2 |
| 8 | Tell me about the DTU ECE department | 6.0 | 1213.8 | groq | Yes | 1 |
| 9 | What is the history of DTU? | 6.3 | 1004.3 | groq | Yes | 1 |
| 10 | Tell me about NSUT hostels | 2.9 | 724.9 | groq | Yes | 1 |
| 11 | How do UG admissions work at NSUT? | 3.0 | 648.8 | groq | Yes | 2 |
| 12 | What is the NIRF rank of NSUT? | 3.0 | 2830.1 | groq | No (refused) | 0 |
| 13 | What is the hostel fee at BPIT? | 4.1 | 3589.3 | extractive | Yes | 2 |
| 14 | What is the placement record of BPIT? | 3.5 | 853.8 | groq | Yes | 1 |
| 15 | Who recruits from GTBIT? | 6.4 | 3705.0 | groq | No (refused) | 0 |
| 16 | How do admissions work at GTBIT? | 6.1 | 4403.4 | groq | Yes | 2 |
| 17 | What facilities does MSIT have? | 9.6 | 3701.6 | extractive | Yes | 3 |
| 18 | What is the intake of USICT B.Tech CSE? | 1.8 | 758.9 | groq | Yes | 2 |
| 19 | Tell me about IGDTUW placements | 0.8 | 4.4 | none | No (refused) | 0 |
| 20 | What is the swimming pool size at DTU? | 5.6 | 10.1 | none | No (refused) | 0 |
