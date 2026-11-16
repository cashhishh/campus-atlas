# CampusAtlas — Architecture

CampusAtlas is a source-grounded college intelligence platform. It registers official sources for each college, ingests and versions their content, and monitors them for changes. It answers questions only from what it has indexed, and it cites every source with a verification badge and a freshness indicator.

## 1. System architecture

```mermaid
flowchart LR
    subgraph Browser["Browser — React 19 + TypeScript (Vite)"]
        UI["Pages: Home · Explore · College · Ask · Compare · Find · Updates · Analytics · Data management"]
        LocalKB["Offline fallback: static registry + DEMO knowledge (localStorage)"]
    end

    subgraph Vite["Vite dev server (Node)"]
        Proxy["/api proxy → FastAPI"]
        WebPlugin["/api/web-research plugin (experimental Groq web search)"]
    end

    subgraph API["FastAPI backend (Python 3.12)"]
        Routes["api/routes.py — 26 REST endpoints"]
        Ingest["ingestion/pipeline.py — fetch · extract · clean · chunk"]
        Change["change_detection/diff.py — versions · diff · summary"]
        Monitor["monitoring/scheduler.py — APScheduler job + run log"]
        Verify["verification/rules.py — domain rules · freshness"]
        RAG["retrieval/rag.py + entities.py — college detection · grounding rule"]
        Rec["recommendations/engine.py — explainable scoring · compare evidence"]
        Analytics["analytics/service.py — dashboard aggregates"]
        Groq["ai/groq_client.py — model fallback · 429 retry"]
    end

    subgraph Storage
        SQLite[("SQLite (SQLAlchemy, swappable DATABASE_URL)")]
        Chunks[("Chunk store: ChromaDB or JSON + BM25")]
    end

    Web[("Official college sites · NIRF PDFs · GGSIPU")]
    GroqCloud[("Groq Cloud LLM")]

    UI --> Proxy --> Routes
    UI --> WebPlugin --> GroqCloud
    UI -. API offline .-> LocalKB
    Routes --> RAG & Rec & Analytics & Monitor & Ingest
    Monitor --> Ingest --> Web
    Ingest --> Change --> Groq
    Ingest --> Chunks
    Ingest --> SQLite
    RAG --> Chunks
    RAG --> Verify
    RAG --> Groq --> GroqCloud
    Rec --> RAG
    Analytics --> SQLite
    Routes --> SQLite
```

## 2. Modules

| Module | File(s) | Responsibility |
|---|---|---|
| Configuration | `app/config.py` | Merges root and backend `.env` files, anchors relative paths, and holds the monitoring, freshness and retrieval settings |
| Database | `app/database.py`, `app/models/models.py` | SQLAlchemy engine, 7 tables, and a forward-only column migration for databases created before Phase 5 |
| Seeding | `app/seed.py`, `app/pilot_sources.py` | Idempotent registry (53 colleges), 4 DEMO sources and 42 pilot sources |
| Ingestion | `app/ingestion/pipeline.py` | HTTP fetch (OS trust store), HTML boilerplate removal, PyMuPDF PDF extraction, word-boundary chunking with overlap, SHA-256 hashing, failure marking |
| Change intelligence | `app/change_detection/diff.py` | Passage-level diff (difflib), plus a Groq summary or a deterministic diff summary |
| Monitoring | `app/monitoring/scheduler.py` | APScheduler interval job, parallel fetch (thread pool), sequential DB processing, one run at a time (lock), `MonitorRun` log |
| Verification | `app/verification/rules.py` | Official / Third-party / Unverified by domain rules; freshness (fresh, stale, never checked) |
| Chunk store | `app/services/vector_store.py` | ChromaDB when installed, otherwise JSON + BM25; replaces a source's chunks as one set |
| Retrieval and QA | `app/retrieval/entities.py`, `app/retrieval/rag.py` | College alias detection, intent classification, relevance threshold, the grounding rule, Groq context-only answers, extractive fallback |
| Decision support | `app/recommendations/engine.py` | Explainable preference scoring; evidence table for comparisons |
| Analytics | `app/analytics/service.py` | Totals, timelines, breakdowns, top queries, latency |
| LLM client | `app/ai/groq_client.py` | Groq chat completions, retired-model fallback, 429 retry, reasoning-tag cleanup |
| Frontend | `frontend/src.tsx`, `frontend/src/pages/*`, `frontend/src/services/api.ts` | Routes, Phase 5 pages, badges, API client with offline fallback |

## 3. Data flow

### 3.1 Ingestion and change detection

```mermaid
flowchart TD
    A["Trigger: APScheduler interval · 'Run check now' button · POST /api/monitor/run"] --> B["Create MonitorRun (RUNNING)"]
    B --> C["Fetch all active sources in parallel (thread pool)"]
    C --> D{"Content type?"}
    D -- HTML --> E["BeautifulSoup: drop nav/header/footer/script/forms → text"]
    D -- PDF --> F["PyMuPDF: extract text from every page"]
    D -- DEMO --> G["Labelled DEMO DATA text (latest stored version)"]
    E & F & G --> H{"≥ 80 characters?"}
    H -- no --> X["Mark source FETCH_FAILED + last_error · IngestionEvent FAILED"]
    H -- yes --> I["Normalise whitespace → SHA-256 hash"]
    I --> J{"Hash changed?"}
    J -- no --> K["Update last_checked · IngestionEvent 'No content change'"]
    J -- yes --> L["Store ContentVersion n+1"]
    L --> M["Chunk (700 chars, 120 overlap) → replace the source's chunks"]
    M --> N{"First version?"}
    N -- yes --> O["UpdateEvent NEW_SOURCE_CONTENT + summary"]
    N -- no --> P["Passage diff vs previous version → Groq / deterministic summary → UpdateEvent CONTENT_UPDATED"]
    K & O & P & X --> Q["Finish MonitorRun: sources checked, changes, errors, duration, status"]
```

### 3.2 Question answering (grounding rule)

```mermaid
flowchart TD
    Q["Question"] --> D["Detect colleges (aliases + registry names) and intent"]
    D --> S["Remove college names from the search text → content terms"]
    S --> R["BM25 search, filtered to the detected colleges"]
    R --> T{"Any chunk covering ≥ 20% of the content terms?"}
    T -- no --> NA["'Not available in indexed sources.' — no LLM call"]
    T -- yes --> C["Top 5 chunks → numbered sources [S1..]"]
    C --> G{"GROQ_API_KEY set?"}
    G -- yes --> L["Groq: answer ONLY from the sources, cite [S#]"]
    G -- no / error --> E["Extractive: best-matching sentences with [S#]"]
    L & E --> V["Attach verification badge + freshness to every citation"]
    V --> LOG["Log query (intent, answered, latency) → analytics"]
```

## 4. Database schema (ER)

```mermaid
erDiagram
    COLLEGES ||--o{ SOURCES : "has"
    SOURCES ||--o{ CONTENT_VERSIONS : "versioned as"
    SOURCES ||--o{ INGESTION_EVENTS : "logged by"
    SOURCES ||--o{ UPDATE_EVENTS : "changes recorded in"
    CONTENT_VERSIONS ||--o| UPDATE_EVENTS : "old / new version"
    MONITOR_RUNS ||--o{ UPDATE_EVENTS : "detected"
    MONITOR_RUNS ||--o{ INGESTION_EVENTS : "produced"

    COLLEGES {
        string id PK
        string name
        string category
        string city
        string state
        string official_domain
        datetime created_at
    }
    SOURCES {
        int id PK
        string college_id FK
        string source_name
        string source_url
        string source_type
        string authority_level
        string status "ACTIVE | DEMO_READY | FETCH_FAILED | DISABLED"
        string content_hash
        datetime last_checked
        datetime last_changed
        text last_error
        bool is_demo
    }
    CONTENT_VERSIONS {
        int id PK
        int source_id FK
        int version_no
        string content_hash
        text text
        int char_count
        string document_title
        datetime created_at
    }
    INGESTION_EVENTS {
        int id PK
        int source_id FK
        string status "SUCCESS | FAILED"
        string document_title
        int chunks_created
        text message
        int monitor_run_id FK
        datetime created_at
    }
    UPDATE_EVENTS {
        int id PK
        string college_id
        int source_id FK
        string change_type "NEW_SOURCE_CONTENT | CONTENT_UPDATED"
        string old_hash
        string new_hash
        int old_version_id FK
        int new_version_id FK
        text summary
        string summary_mode "groq | deterministic"
        text diff
        int added_count
        int removed_count
        int monitor_run_id FK
        datetime detected_date
    }
    MONITOR_RUNS {
        int id PK
        string trigger "scheduled | manual | pilot-ingestion"
        string status "RUNNING | SUCCESS | PARTIAL | FAILED"
        datetime started_at
        datetime finished_at
        int duration_ms
        int sources_checked
        int changes_found
        int errors
        text details "JSON per-source results"
    }
    QUERY_LOGS {
        int id PK
        text query
        string normalized_query
        string intent
        string college_ids
        int hits
        bool answered
        string mode
        float retrieval_ms
        float total_ms
        datetime created_at
    }
```

Chunks live in the chunk store, not in SQLite. Each chunk carries this metadata: `college_id, source_id, source_url, source_name, source_type, authority_level, document_title, doc_type, version_no, chunk_index, is_demo, ingested_at`.

## 5. Use cases

```mermaid
flowchart LR
    Student(["Student / parent"])
    Admin(["Data administrator"])
    Scheduler(["Scheduler (system)"])

    subgraph CampusAtlas
        UC1(("Explore colleges"))
        UC2(("Ask a question with cited sources"))
        UC3(("Compare colleges on indexed evidence"))
        UC4(("Build an explainable shortlist"))
        UC5(("Read the change feed and diffs"))
        UC6(("View analytics"))
        UC7(("Register / disable a source"))
        UC8(("Run a monitoring check now"))
        UC9(("Inspect sources: verification, freshness, failures"))
        UC10(("Re-check sources on an interval"))
    end

    Student --> UC1 & UC2 & UC3 & UC4 & UC5
    Admin --> UC6 & UC7 & UC8 & UC9 & UC5
    Scheduler --> UC10
    UC10 -. includes .-> UC5
```

## 6. Sequence: an AI query

```mermaid
sequenceDiagram
    actor U as Student
    participant FE as React (Ask page)
    participant VP as Vite proxy
    participant API as FastAPI /api/ask
    participant RAG as rag.answer()
    participant VS as Chunk store (BM25)
    participant DB as SQLite
    participant G as Groq

    U->>FE: "Does MAIT offer ECE?"
    FE->>VP: POST /api/ask {query}
    VP->>API: forward
    API->>DB: load registry (ids, names)
    API->>RAG: answer(query, registry)
    RAG->>RAG: detect colleges → [mait]; intent → academics
    RAG->>VS: query("offer ece", college_ids=[mait])
    VS-->>RAG: ranked chunks + coverage
    alt no chunk above threshold
        RAG-->>API: "Not available in indexed sources." (LLM not called)
    else evidence found
        RAG->>G: system: answer ONLY from SOURCES; user: question + [S1..S5]
        G-->>RAG: "Yes … intake of 120 [S1]"
        RAG->>DB: source rows → verification + freshness per citation
        RAG-->>API: answer, sources, mode, latency
    end
    API->>DB: insert QueryLog (intent, answered, latency)
    API-->>FE: JSON
    FE-->>U: answer + citation cards (Official · Checked 2 h ago · DEMO DATA if any)
```

## 7. Sequence: scheduled monitoring run

```mermaid
sequenceDiagram
    participant S as APScheduler / "Run check now"
    participant M as run_monitoring_cycle
    participant W as College websites
    participant P as pipeline.process_text
    participant DB as SQLite
    participant VS as Chunk store
    S->>M: trigger
    M->>DB: MonitorRun(status=RUNNING)
    par fetch in parallel
        M->>W: GET source 1..n
        W-->>M: HTML / PDF
    end
    loop each source
        M->>P: extracted text
        P->>DB: compare hash; store ContentVersion if changed
        P->>VS: replace the source's chunks
        P->>DB: UpdateEvent (diff + summary) / IngestionEvent
    end
    M->>DB: MonitorRun(SUCCESS | PARTIAL, counts, duration)
```

## 8. Design decisions

- **The grounding rule is enforced in code, not only in the prompt.** If retrieval returns nothing relevant, the LLM is never called (test T22).
- **Verification is deterministic.** Domain rules are explainable and testable; an LLM does not judge authority.
- **The extractive fallback** keeps the app usable and honest without a key, during rate limits and offline.
- **Chunks are replaced per source,** so a page that removes old information can no longer be cited.
- **Fetching is parallel; DB writes are sequential.** A 46-source check takes ~7 s with no SQLite write contention.
- **Failure is data.** Unfetchable sources stay registered and are marked `FETCH_FAILED` with the reason, and answers say "Not available in indexed sources."
