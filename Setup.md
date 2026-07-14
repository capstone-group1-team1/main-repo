# FacilityGraph AI — Setup Guide

Use this guide to run the complete FacilityGraph AI stack locally, including
the FastAPI backend, Next.js frontend, Neo4j knowledge graph, and Weaviate
vector database.

For day-to-day operation after setup, see [`Runbook.md`](./Runbook.md). For
the internal system design, see [`Architecture.md`](./Architecture.md).

> **Frontend configuration:** The current frontend is built with Next.js,
> runs on port `3000`, and uses `NEXT_PUBLIC_API_BASE_URL` to configure the
> backend URL.

---

## 1. What You're Running

```text
   Browser (Next.js UI, :3000)
        │
        │ HTTP + X-Mock-User-Id header
        ▼
   FastAPI backend (:8000)
        │
        ├──► xAI API
        │      Primary model: grok-4.5
        │
        ├──► Groq API
        │      Fallback model:
        │      meta-llama/llama-4-scout-17b-16e-instruct
        │
        ├──► bge-large embeddings
        │      Local, in-process
        │
        ├──► Neo4j
        │      :7687 Bolt / :7474 Browser
        │      Knowledge graph
        │
        └──► Weaviate
               :8080 REST / :50051 gRPC
               Vector database
```

xAI is the primary LLM provider. Groq is used only when xAI encounters a
qualifying transient provider failure:

- HTTP `429`
- Request timeout
- Connection failure
- HTTP `5xx`

Authentication and configuration errors do not trigger the Groq fallback.

Neo4j and Weaviate run in Docker. The backend and frontend can run directly
on the host or as part of the complete Docker Compose stack.

## 2. Prerequisites

| Software | Version | Check command |
|---|---:|---|
| Docker | 24+ with Compose v2 | `docker --version` and `docker compose version` |
| Python | 3.11 or 3.12 | `python3 --version` |
| Node.js | 20+ | `node --version` |
| Git | Any supported version | `git --version` |

You also need:

- An **xAI API key** for the primary LLM provider.
- A **Groq API key** for transient-failure fallback.
- Approximately 4 GB of available RAM for Neo4j, Weaviate, and the embedding model.
- Approximately 1.3 GB of available disk space for `bge-large-en-v1.5`.

## 3. Clone the Repository

```bash
git clone https://github.com/capstone-group1-team1/main-repo.git
cd main-repo
```

## 4. Configure Environment Variables

Copy the root environment template:

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

Additional supported variables may include:

| Variable | Required | Purpose |
|---|---:|---|
| `XAI_API_KEY` | **Yes** | Authenticates requests to the primary xAI provider |
| `XAI_BASE_URL` | **Yes** | Configures the xAI-compatible API endpoint |
| `XAI_MODEL` | **Yes** | Primary model; currently `grok-4.5` |
| `GROQ_API_KEY` | **Yes** | Authenticates the Groq fallback provider |
| `GROQ_MODEL` | **Yes** | Fallback model; currently `meta-llama/llama-4-scout-17b-16e-instruct` |
| `ENABLE_GRAPH_ENRICHMENT` | No | Set to `false` to skip per-chunk LLM enrichment during iteration |
| `LOG_LEVEL` | No | Use `DEBUG` for detailed ingestion and rejection logs |
| `CORS_ORIGINS` | No | Comma-separated list of permitted frontend origins |

Never commit `.env`, API keys, or other secrets to the repository.

## 5. Start the Infrastructure Services

To start the services defined in Docker Compose:

```bash
docker compose up -d
docker compose ps
```

Wait until Neo4j and Weaviate report a healthy status.

Sanity-check Weaviate:

```bash
curl http://localhost:8080/v1/.well-known/ready
```

Open the Neo4j browser at:

```text
http://localhost:7474
```

The local development credentials may use:

```text
Username: neo4j
Password: smartoffice123
```

> **Security:** `smartoffice123` is a local development default. Change it
> before using a shared, staging, or production environment.

## 6. Add the Device Manuals

Place the 10 manual PDFs in:

```text
data/manuals_pdf/
```

The files must be text-based PDFs rather than image-only scans. The ingestion
pipeline extracts the text layer with `pypdf`. Image-only files are rejected
when no extractable text is found.

Each filename should contain the matching device name from
`data/asset_inventory.csv`. Spaces, underscores, and hyphens are supported.

Recommended filenames:

| Device | Recommended filename |
|---|---|
| Cisco ISR 1111 Router | `cisco_isr_1111_router.pdf` |
| Cisco Catalyst C9200L-24P-4G Switch | `cisco_catalyst_9200l_switch.pdf` |
| Cisco Catalyst 9115AXI Access Point | `cisco_9115axi_access_point.pdf` |
| Crestron CP4 Control Processor | `crestron_cp4.pdf` |
| Crestron TST-1080 Touch Screen | `crestron_tst_1080_touch_screen.pdf` |
| Crestron AirMedia AM-3100-WF Receiver | `crestron_am_3100_wf_receiver.pdf` |
| Crestron AirMedia AM-TX3-100 Adapter | `crestron_am_tx3_100_adapter.pdf` |
| Cisco Codec EQ | `cisco_codec_eq.pdf` |
| Cisco Ceiling Microphone Pro | `cisco_ceiling_mic_pro.pdf` |
| Samsung QMC75 Display | `samsung_qmc75_display.pdf` |

A missing PDF is skipped with a warning, and the remaining files can still be
ingested.

To add a new device later:

1. Add the device to `data/asset_inventory.csv`.
2. Add a matching PDF to `data/manuals_pdf/`.
3. Run the seeding process again.

The ingestion manifest ensures that only new or changed content is processed.

## 7. Install the Backend for Manual Development

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

Install the dependencies:

```bash
pip install --upgrade pip
pip install -r ../requirements.txt
```

The first installation may take several minutes because it installs packages
such as `torch` and `sentence-transformers`.

Run backend commands from the `backend/` directory with the virtual
environment active.

## 8. Seed the System

From the project root:

```bash
bash scripts/seed_all.sh
```

The script performs two main operations:

1. Builds the Neo4j knowledge graph from rooms, devices, relationships, and
   incident CSV files.
2. Processes manuals and incidents, creates embeddings, and writes vector
   records to Weaviate.

When graph enrichment is enabled, the first ingestion may make one LLM call
per manual chunk. xAI is used as the primary provider, and Groq is used only
for qualifying transient xAI failures.

Example ingestion summary:

```text
=== Ingestion report ===
Manuals:   {'new': 10}
Incidents: {'new': 16}
Weaviate total chunks: ~180
```

On later runs, unchanged manuals may appear as skipped because ingestion uses
content hashes.

## 9. Alternative: Run the Full Stack with Docker Compose

Build and start Neo4j, Weaviate, the API, and the web application:

```bash
docker compose up -d --build
docker compose ps
```

Seed from inside the API container:

```bash
docker compose exec api python -m app.graph.graph_loader
docker compose exec api python -m app.ingestion.pipeline
```

Open:

- Application: `http://localhost:3000`
- FastAPI documentation: `http://localhost:8000/docs`
- Neo4j browser: `http://localhost:7474`

The `data/manuals_pdf/` directory is mounted into the API container. Add the
manuals before running ingestion.

## 10. Run the Backend Manually

From the `backend/` directory with the virtual environment active:

```bash
uvicorn app.main:app --reload --port 8000
```

Verify the health endpoint:

```bash
curl http://localhost:8000/healthz
```

Example healthy response:

```json
{
  "api": "ok",
  "neo4j": "ok",
  "weaviate": "ok (183 chunks)"
}
```

Test the chat endpoint with a technician user:

```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Mock-User-Id: u-ali" \
  -d '{"question":"The Samsung display has no signal. What should I check?"}' \
  | python3 -m json.tool
```

API documentation:

```text
http://localhost:8000/docs
```

## 11. Run the Frontend Manually

```bash
cd frontend
cp .env.example .env
```

Set the backend URL:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Install and run the frontend:

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

The interface includes:

- A user-role picker
- An Ask tab with cited answers and confidence badges
- A Devices tab
- An Incidents tab

## 12. Run the Tests

Run the complete backend test suite:

```bash
cd backend
pytest tests -q
```

The test suite covers areas such as:

- Router rules
- Confidence calculations
- Citation assembly
- Document chunking
- Permission handling
- Output safety
- LLM provider fallback behavior

## 13. Run the Validation Checks

From the repository root, run:

```bash
python -m compileall -q backend/app backend/tests
PYTHONPATH=backend pytest -q backend/tests/test_output_guard.py backend/tests/test_llm_provider_fallback.py
docker compose config --quiet
docker compose build api web
```

These commands validate:

- Python syntax
- Output guard behavior
- xAI-to-Groq fallback behavior
- Docker Compose configuration
- API and frontend Docker image builds

## 14. Run the Smoke Test

With the backend running and the system seeded:

```bash
python scripts/smoke_test.py
```

The smoke test checks the health endpoint and submits one question for each
retrieval route while validating the response structure.

## 15. Run the Evaluation

With the backend running and the data stores seeded:

```bash
cd eval
python run_eval.py --subset smoke
python run_eval.py
python run_eval.py --baseline
```

The evaluation commands run:

- A six-item smoke subset
- The complete 50-item evaluation across three seeds
- A plain-RAG baseline comparison

Generated JSON and Markdown reports are stored in:

```text
eval/reports/
```

The reports include:

- Answer correctness
- Routing accuracy
- Citation validity
- Confidence calibration
- p95 latency
- Error breakdowns by route and device
- Documented failure cases and next-iteration hypotheses

## 16. Troubleshooting

| Symptom | Cause or fix |
|---|---|
| Missing `XAI_API_KEY` or xAI configuration validation error | Set `XAI_API_KEY`, `XAI_BASE_URL`, and `XAI_MODEL` in the root `.env` file |
| Missing `GROQ_API_KEY` or `GROQ_MODEL` | Add the Groq fallback credentials and model to `.env` |
| xAI returns HTTP `429`, timeout, connection failure, or HTTP `5xx` | The application should use the configured Groq fallback |
| xAI authentication or configuration error | Correct the xAI settings; these errors intentionally do not trigger fallback |
| `/healthz` reports a Neo4j error | Check `docker compose ps` and `docker compose logs neo4j` |
| `/healthz` reports a Weaviate error | Confirm that ports `8080` and `50051` are available and that Weaviate is healthy |
| Seeding reports a missing manual | Add the corresponding PDF to `data/manuals_pdf/` |
| Seeding reports no extractable text | Replace the image-only scan with a text-based PDF |
| The first request is very slow | The local embedding model may still be downloading or loading |
| Frontend cannot reach the backend | Confirm that the backend is running on port `8000` and `NEXT_PUBLIC_API_BASE_URL` is correct |
| Browser reports a CORS error | Add the frontend origin to `CORS_ORIGINS`, then restart the backend |
| Graph enrichment is slow or consumes too many tokens | Set `ENABLE_GRAPH_ENRICHMENT=false` during development |
| A required port is already in use | Stop the conflicting service or update the relevant mapping in `docker-compose.yml` |

## 17. Stop or Reset the Environment

Stop the services while keeping persistent data:

```bash
docker compose down
```

Stop the services and remove graph and vector volumes:

```bash
docker compose down -v
```

Remove ingestion history to force a complete re-ingestion:

```bash
rm -f data/ingest_manifest.sqlite
```

After a full reset:

```bash
docker compose up -d
bash scripts/seed_all.sh
```