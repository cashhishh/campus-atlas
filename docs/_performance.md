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
