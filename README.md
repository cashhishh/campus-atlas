# CampusAtlas

CampusAtlas is an AI-powered, source-driven college intelligence prototype for a B.Tech Minor Project defense.

## Quick start

1. Install dependencies:

```bash
npm install
```

2. Start the application:

```bash
npm run dev
```

Open the Vite localhost address shown in the terminal. Demo Knowledge Mode works without any external service.

## Demo Mode

Demo Knowledge Mode is the default and is fully functional without an API key. It searches a local source-grounded knowledge base and returns only matching local entries with source attribution.

The Data Management page includes a clearly labelled **Prototype / Demo Ingestion** flow for configured HTML and PDF examples. It displays staged processing and saves ingestion history in browser local storage. It does not claim to crawl live websites.

## Live AI Mode (optional, Groq)

Set the server-side value in the root `.env` file:

```text
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.6-27b
GROQ_WEB_MODEL=groq/compound-mini
```

Run the project with just:

```bash
npm install
npm run dev
```

The Vite development server hosts the local `/api/ask` endpoint. It sends the normalized question and any relevant local knowledge to Groq Compound Mini, which uses current web search and returns cited sources. The prompt prioritises official college, government, admission-authority, and official PDF sources. The API key stays on the server and never reaches browser code. If Groq is unavailable or rate-limited, the UI automatically falls back to Demo Knowledge Mode.

## Architecture

```text
React + TypeScript + Vite
├── src/data/       local college registry, sources and knowledge entries
├── src/services/   retrieval, demo AI, ingestion and local storage adapters
└── src.tsx         premium responsive routes and UI
```

## Working first-defense features

- 50-college registry with search and filtering
- Detailed local demonstration profiles: DTU, MAIT, NSUT, IIT Delhi and BITS Pilani
- Source registry and source authority labels
- Source-grounded Ask CampusAtlas with source cards
- Local PDF-processing demonstration entry
- Prototype staged ingestion with local history
- Evidence-aware college comparison
- Explainable client-side college recommendations
- Responsive UI and local persistence for comparisons, searches, preferences and ingestion history

## Future phase / Coming Soon

- Continuous source monitoring
- Semantic change detection
- Live large-scale ingestion
- Automatic source discovery
- Production-scale vector database infrastructure
