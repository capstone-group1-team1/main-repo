# main-repo

**AI Capstone Project for Group 1 Team 1**

FacilityGraph AI is a hybrid RAG + Knowledge Graph assistant for smart office maintenance.

AI.SPIRE capstone project — LevelUp Economy × Istidama Consulting × Future Skills Fund.

FacilityGraph AI answers maintenance and facility questions such as:

- *Why does the display in the meeting room show no signal?*
- *What is connected to the reception access point?*
- *What was installed in this room last year?*

The system combines semantic search over device manuals and incident records with a structured knowledge graph of office devices, rooms, relationships, and maintenance history.

Every generated answer includes citations and a confidence score. When supporting evidence is missing, the confidence score is capped at a low level to make uncertainty visible to the user.

## Documentation

| Document | Purpose |
|---|---|
| [`Executive_Briefing.md`](./Executive_Briefing.md) | Non-technical overview of the system, its value, trust mechanisms, and current scope |
| [`Architecture.md`](./Architecture.md) | System architecture, routing logic, retrieval, synthesis, citations, confidence scoring, and module map |
| [`Setup.md`](./Setup.md) | Complete local installation and setup instructions |
| [`Runbook.md`](./Runbook.md) | Health checks, common operational tasks, troubleshooting, and recovery procedures |

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

Set the following variables in the local `.env` file:

```env
XAI_API_KEY=your_xai_api_key
XAI_BASE_URL=your_xai_base_url
XAI_MODEL=grok-4.5

GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

Never commit `.env` or any API keys to the repository.

### 3. Build and start the full stack

```bash
docker compose up -d --build
```

The Docker Compose stack starts the project services, including Neo4j, Weaviate, the FastAPI backend, and the frontend.

### 4. Seed the data stores

```bash
bash scripts/seed_all.sh
```

This command loads the knowledge graph data and ingests the available manuals and incident records.

For complete setup instructions, required filenames, environment variables, and troubleshooting guidance, see [`Setup.md`](./Setup.md).

## LLM Providers

FacilityGraph AI uses xAI with `grok-4.5` as its primary LLM provider.

Groq with `meta-llama/llama-4-scout-17b-16e-instruct` is used only when xAI has a transient provider failure, including:

- HTTP `429`
- Request timeout
- Connection failure
- HTTP `5xx`

Configuration and authentication errors do not trigger the Groq fallback.

The required provider settings are:

- `XAI_API_KEY`
- `XAI_BASE_URL`
- `XAI_MODEL`
- `GROQ_API_KEY`
- `GROQ_MODEL`

Store these values only in a local `.env` file. Never commit `.env` or API keys.

## Verification

Check that all containers are running:

```bash
docker compose ps
```

Check the backend health endpoint:

```bash
curl http://localhost:8000/health
```

Open the FastAPI documentation:

```text
http://localhost:8000/docs
```

## Validation

Run the following checks before opening or merging a pull request:

```bash
python -m compileall -q backend/app backend/tests
PYTHONPATH=backend pytest -q backend/tests/test_output_guard.py backend/tests/test_llm_provider_fallback.py
docker compose config --quiet
docker compose build api web
```

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
                                                          ▼
                                              inline citation markers
                                                          │
                                                          ▼
                                           citation assembler + confidence
                                                          │
                                                          ▼
                                                    ChatResponse
```

Each question is classified into one of three retrieval routes:

- `GRAPH_ONLY` for structured relationships, topology, devices, rooms, and historical facts.
- `RAG_ONLY` for information found primarily in manuals and unstructured documents.
- `HYBRID` when both knowledge graph and vector retrieval evidence are useful, or when the router is uncertain.

Evidence is retrieved from Neo4j and/or Weaviate, merged when necessary, and sent to the synthesis layer. xAI generates the response by default, while Groq is reserved for qualifying transient provider failures. The final response includes assembled citations and a user-facing confidence score.

See [`Architecture.md`](./Architecture.md) for the complete technical breakdown.

## Tech Stack

- **Primary LLM:** xAI using `grok-4.5`
- **Fallback LLM:** Groq using `meta-llama/llama-4-scout-17b-16e-instruct`
- **Backend:** FastAPI
- **Frontend:** Next.js
- **Knowledge Graph:** Neo4j
- **Vector Database:** Weaviate v4
- **Embeddings:** `bge-large-en-v1.5`
- **Reranker:** `bge-reranker-base`
- **Deployment:** Docker Compose
- **Monitoring:** Prometheus / OpenMetrics

## Current Scope

The current system includes:

- 10 devices across 4 rooms
- Devices from Cisco, Crestron, and Samsung
- 24 documented relationships
- 16 historical incidents
- A 50-question held-out evaluation dataset balanced across the three routing modes

## Team

- Amer Almajali
- Afnan Tayem
- Ibrahim Yasin
- Mohammad Zalloum