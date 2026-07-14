# GridSense Office

**A hybrid RAG + Knowledge Graph assistant for smart office maintenance.**

AI.SPIRE capstone project — LevelUp Economy × Istidama Consulting × Future Skills Fund.

GridSense Office answers maintenance and facility questions such as:

- *Why does the display in the meeting room show no signal?*
- *What is connected to the reception access point?*
- *What was installed in this room last year?*

The system combines semantic search over device manuals and incident records
with a structured knowledge graph of office devices, rooms, relationships,
and maintenance history.

Every generated answer includes citations and a user-facing confidence score.
When supporting evidence is weak or missing, the confidence score is reduced
and citation-free answers are prevented from appearing highly reliable.

## Documentation

| Document | Purpose |
|---|---|
| [`Executive_Briefing.md`](./Executive_Briefing.md) | Non-technical overview of the problem, solution, value, scope, and roadmap |
| [`Architecture.md`](./Architecture.md) | System architecture, routing, retrieval, synthesis, citations, confidence, and deployment design |
| [`Setup.md`](./Setup.md) | Complete local installation, configuration, seeding, and validation instructions |
| [`Runbook.md`](./Runbook.md) | Daily operations, health checks, troubleshooting, recovery, and demo readiness |

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/capstone-group1-team1/main-repo.git
cd main-repo
```

### 2. Configure the environment

```bash
cp .env.example .env
```

Set the required LLM provider variables in `.env`:

```env
XAI_API_KEY=your_xai_api_key
XAI_BASE_URL=your_xai_base_url
XAI_MODEL=grok-4.5

GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

Never commit `.env` or API keys.

### 3. Build and start the full stack

```bash
docker compose up -d --build
docker compose ps
```

This starts Neo4j, Weaviate, the FastAPI backend, and the Next.js frontend.

### 4. Seed the knowledge stores

Load the graph first:

```bash
docker compose exec api python -m app.graph.graph_loader
```

Then ingest manuals and incidents:

```bash
docker compose exec api python -m app.ingestion.pipeline
```

Open the application:

```text
http://localhost:3000
```

Open the FastAPI documentation:

```text
http://localhost:8000/docs
```

For full setup instructions, manual naming rules, environment variables, and
troubleshooting, see [`Setup.md`](./Setup.md).

## LLM Providers

GridSense Office uses:

- **Primary provider:** xAI with `grok-4.5`
- **Fallback provider:** Groq with
  `meta-llama/llama-4-scout-17b-16e-instruct`

Groq is used only when xAI encounters a qualifying transient provider failure,
including:

- HTTP `429`
- Request timeout
- Connection failure
- HTTP `5xx`

Authentication and configuration errors do not trigger fallback.

## How It Works

```text
 Question
    │
    ▼
 Query Router ──► GRAPH_ONLY ──► graph retriever  ─┐
   (rules,        RAG_ONLY   ──► vector retriever ─┼─► evidence
    LLM fallback, HYBRID     ──► both + merger    ─┘      │
    HYBRID default)                                       ▼
                                             LLM synthesis (xAI)
                                                          │
                                          transient failure only
                                                          ▼
                                                Groq fallback
                                                          │
                                               inline [n] markers
                                                          ▼
                                           citation assembler
                                                          │
                                           confidence calculation
                                                          │
                                                          ▼
                              ChatResponse (`POST /chat`)
                              or token stream (`POST /chat/stream`)
```

Each question is classified into one of three retrieval routes:

- `GRAPH_ONLY` for structured relationships, topology, room contents, device
  history, and graph facts.
- `RAG_ONLY` for manuals, troubleshooting procedures, and unstructured
  incident evidence.
- `HYBRID` when both evidence types are useful or when routing remains
  uncertain.

Evidence is retrieved from Neo4j, Weaviate, or both. Hybrid candidates are
merged, deduplicated, and reranked before synthesis. The final output includes
validated citations and a route-aware confidence score.

See [`Architecture.md`](./Architecture.md) for the complete technical design.

## API Modes

GridSense Office supports:

- `POST /chat` for a complete response
- `POST /chat/stream` for token-by-token streaming

Both modes use the same routing, retrieval, provider fallback, citation, and
confidence pipeline.

## Tech Stack

- **Primary LLM:** xAI `grok-4.5`
- **Fallback LLM:** Groq `meta-llama/llama-4-scout-17b-16e-instruct`
- **Backend:** FastAPI
- **Frontend:** Next.js
- **Knowledge Graph:** Neo4j
- **Vector Database:** Weaviate v4
- **Search:** Hybrid dense vector + BM25
- **Embeddings:** `BAAI/bge-large-en-v1.5`
- **Reranker:** `BAAI/bge-reranker-base`
- **Deployment:** Docker Compose
- **Monitoring:** Prometheus/OpenMetrics

## Current Scope

The current capstone implementation includes:

- 10 devices across 4 rooms
- Cisco, Crestron, and Samsung equipment
- 24 documented physical and logical relationships
- 16 historical incident records
- 10 vendor manuals
- A 50-question held-out evaluation dataset
- Coverage across `GRAPH_ONLY`, `RAG_ONLY`, and `HYBRID`
- Deliberately out-of-scope questions to test whether the system avoids
  unsupported guessing

## Validation

Run the following checks before opening or merging a pull request:

```bash
python -m compileall -q backend/app backend/tests
PYTHONPATH=backend pytest -q backend/tests/test_output_guard.py backend/tests/test_llm_provider_fallback.py
docker compose config --quiet
docker compose build api web
```

With the full stack running and seeded:

```bash
python scripts/smoke_test.py
```

## Team

- Amer Almajali
- Afnan Tayem
- Ibrahim Yasin
- Mohammad Zalloum