"""Measure retrieval latency and AI answer latency over 20 sample queries.

Usage (from backend/):  .venv\\Scripts\\python -m scripts.benchmark
Writes docs/_performance.md (embedded into docs/test_results.md by pytest)
and docs/performance.json. Queries are NOT written to the query log.
"""
import json
import statistics
import time
from pathlib import Path

from app.ai import groq_client
from app.api.routes import _registry
from app.database import SessionLocal, init_db
from app.retrieval.rag import answer, retrieve
from app.services.vector_store import count

QUERIES = [
    "Does MAIT offer ECE?", "What is the fee structure at MAIT?", "Does MAIT have a hostel?", "Tell me about MAIT placements",
    "What is the NIRF rank band of MAIT?", "What B.Tech programmes does DTU offer?", "What is the median salary at DTU?",
    "Tell me about the DTU ECE department", "What is the history of DTU?", "Tell me about NSUT hostels",
    "How do UG admissions work at NSUT?", "What is the NIRF rank of NSUT?", "What is the hostel fee at BPIT?",
    "What is the placement record of BPIT?", "Who recruits from GTBIT?", "How do admissions work at GTBIT?",
    "What facilities does MSIT have?", "What is the intake of USICT B.Tech CSE?", "Tell me about IGDTUW placements",
    "What is the swimming pool size at DTU?",
]
DOCS = Path(__file__).resolve().parents[2] / "docs"


def pct(values, p):
    values = sorted(values)
    k = max(0, min(len(values) - 1, round(p / 100 * (len(values) - 1))))
    return values[k]


def main():
    init_db()
    db = SessionLocal()
    registry = _registry(db)
    retrieve(QUERIES[0], registry=registry)  # warm the chunk cache
    rows = []
    for q in QUERIES:
        runs = []
        for _ in range(5):
            t = time.perf_counter()
            retrieve(q, registry=registry)
            runs.append((time.perf_counter() - t) * 1000)
        extractive = answer(q, db=db, registry=registry, use_llm=False)
        time.sleep(2.5)  # stay under the Groq free-tier rate limit so latency is not distorted by 429 retries
        ai = answer(q, db=db, registry=registry, use_llm=True)
        rows.append({"query": q, "retrieval_ms": statistics.median(runs), "extractive_total_ms": extractive["latency"]["total_ms"],
                     "ai_total_ms": ai["latency"]["total_ms"], "ai_mode": ai["mode"], "grounded": ai["grounded"],
                     "sources": len(ai["sources"])})
        print(f"{rows[-1]['retrieval_ms']:7.1f} ms | {ai['latency']['total_ms']:7.1f} ms | {ai['mode']:10} | {q}")
    db.close()

    ret = [r["retrieval_ms"] for r in rows]
    ext = [r["extractive_total_ms"] for r in rows]
    llm = [r["ai_total_ms"] for r in rows if r["ai_mode"] == "groq"]
    chunks, driver = count()
    summary = {
        "queries": len(rows), "chunks_indexed": chunks, "vector_driver": driver, "llm_model": groq_client.active_model(),
        "retrieval_avg_ms": round(statistics.mean(ret), 1), "retrieval_p95_ms": round(pct(ret, 95), 1),
        "extractive_answer_avg_ms": round(statistics.mean(ext), 1),
        "ai_answer_avg_ms": round(statistics.mean(llm), 1) if llm else None,
        "ai_answer_p95_ms": round(pct(llm, 95), 1) if llm else None, "ai_calls": len(llm),
        "grounded_answers": sum(r["grounded"] for r in rows), "refusals": sum(not r["grounded"] for r in rows),
    }
    DOCS.mkdir(exist_ok=True)
    (DOCS / "performance.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    lines = [
        "## Performance (20 sample queries on the real pilot index)", "",
        f"Measured {time.strftime('%Y-%m-%d %H:%M')} on the development laptop · {chunks} chunks · {driver} · LLM: Groq `{summary['llm_model'] or 'n/a'}`.", "",
        "| Metric | Value |", "|---|---|",
        f"| Average retrieval latency (median of 5 runs per query) | {summary['retrieval_avg_ms']} ms |",
        f"| 95th percentile retrieval latency | {summary['retrieval_p95_ms']} ms |",
        f"| Average extractive answer latency (no LLM) | {summary['extractive_answer_avg_ms']} ms |",
        f"| Average AI answer latency (retrieval + Groq, {summary['ai_calls']} LLM calls) | {summary['ai_answer_avg_ms']} ms |",
        f"| 95th percentile AI answer latency | {summary['ai_answer_p95_ms']} ms |",
        f"| Grounded answers / refusals (\"Not available in indexed sources.\") | {summary['grounded_answers']} / {summary['refusals']} |", "",
        "Refusals happen without an LLM call when retrieval finds nothing (≈ retrieval time only), so they are excluded from the AI-latency average. AI latency is dominated by the Groq network round trip; on the free tier some calls wait for a 429 rate-limit retry (up to 3 s), and a call that still fails falls back to the extractive answer (mode = extractive), which raises the p95.", "",
        "| # | Query | Retrieval (ms) | AI answer (ms) | Mode | Grounded | Sources |", "|---|---|---|---|---|---|---|",
    ]
    lines += [f"| {i} | {r['query']} | {r['retrieval_ms']:.1f} | {r['ai_total_ms']:.1f} | {r['ai_mode']} | {'Yes' if r['grounded'] else 'No (refused)'} | {r['sources']} |"
              for i, r in enumerate(rows, 1)]
    (DOCS / "_performance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
