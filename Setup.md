# GridSense Office — Setup Guide

Use this guide to run the complete GridSense Office stack locally, including
the FastAPI backend, Next.js frontend, Neo4j knowledge graph, and Weaviate
vector database.

For day-to-day operation after setup, see [`Runbook.md`](./Runbook.md). For
the internal system design, see [`Architecture.md`](./Architecture.md).

---

## 1. System Overview

```text
   Browser (Next.js UI, :3000)
        │
        │ HTTP + X-Mock-User-Id
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

xAI is the primary LLM provider. Groq is configured as the fallback provider
and is invoked only when xAI encounters a qualifying transient failure:

- HTTP `429`
- Request timeout
- Connection failure
- HTTP `5xx`

Authentication and configuration errors do not trigger fallback.

Neo4j and Weaviate run in Docker. The backend and frontend can run either
inside Docker or directly on the host.

---

## 2. Prerequisites

| Software | Recommended version | Check command |
|---|---:|---|
| Docker | 24+ with Compose v2 | `docker --version` and `docker compose version` |
| Python | 3.11 or 3.12 | `python3 --version` |
| Node.js | 20+ | `node --version` |
| Git | Any supported version | `git --version` |

You also need:

- An **xAI API key**
- A **Groq API key**
- Approximately 4 GB of available RAM
- Approximately 1.3 GB of available disk space for `bge-large-en-v1.5`

---

## 3. Clone the Repository

```bash
git clone https://github.com/capstone-group1-team1/main-repo.git
cd main-repo
```

---

## 4. Configure Environment Variables

Copy the root environment template:

```bash
cp .env.example .env
```

Set the required LLM provider variables:

```env
XAI_API_KEY=your_xai_api_key
XAI_BASE_URL=your_xai_base_url
XAI_MODEL=grok-4.5

GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

Common optional settings may include:

```env
ENABLE_GRAPH_ENRICHMENT=true
RERANK_ENABLED=false
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000
```

| Variable | Required | Purpose |
|---|---:|---|
| `XAI_API_KEY` | **Yes** | Authenticates requests to the primary xAI provider |
| `XAI_BASE_URL` | **Yes** | Configures the xAI-compatible API endpoint |
| `XAI_MODEL` | **Yes** | Primary model, currently `grok-4.5` |
| `GROQ_API_KEY` | **Yes** | Authenticates requests to the Groq fallback provider |
| `GROQ_MODEL` | **Yes** | Fallback model, currently `meta-llama/llama-4-scout-17b-16e-instruct` |
| `ENABLE_GRAPH_ENRICHMENT` | No | Enables or disables LLM-assisted graph enrichment |
| `RERANK_ENABLED` | No | Enables or disables cross-encoder reranking |
| `LOG_LEVEL` | No | Controls application logging detail |
| `CORS_ORIGINS` | No | Comma-separated list of allowed frontend origins |

Never commit `.env`, API keys, or other secrets to the repository.

---

## 5. Add the Device Manuals

Place the 10 manual PDFs in:

```text
data/manuals_pdf/
```

The files must be text-based PDFs rather than image-only scans. The ingestion
pipeline extracts the text layer with `pypdf`. A pure image scan is rejected
when no extractable text is found.

Each filename should contain the corresponding device name, model, or alias
from `data/asset_inventory.csv`. Matching uses normalized containment and
prefers the longest valid match. Ambiguous filenames are skipped rather than
guessed.

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

A missing manual is skipped with a warning, and the remaining files can still
be ingested.

To add a new device later:

1. Add the device to `data/asset_inventory.csv`.
2. Add a matching manual to `data/manuals_pdf/`.
3. Run the graph loader.
4. Run the ingestion pipeline.

Both operations are idempotent and process only new or changed content.

---

## 6. Recommended Setup: Full Docker Compose

Build and start the full stack:

```bash
docker compose up -d --build
docker compose ps
```

This starts:

- Neo4j
- Weaviate
- FastAPI backend
- Next.js frontend

Wait until the required services report a healthy status.

Use `--no-cache` only when diagnosing a stale Docker image or dependency
problem:

```bash
docker compose build --no-cache api web
docker compose up -d
```

Do not use `--no-cache` for every normal build because it disables Docker's
build cache and increases build time.

---

## 7. Seed the System

The graph must be loaded before manual ingestion because manuals are linked to
existing device nodes.

Run these commands in order:

```bash
docker compose exec api python -m app.graph.graph_loader
docker compose exec api python -m app.ingestion.pipeline
```

The graph loader creates:

- Rooms
- Devices
- Relationships
- Incidents

The ingestion pipeline:

- Reads manuals
- Extracts text
- Creates semantic chunks
- Generates embeddings
- Writes chunks to Weaviate
- Links manuals to devices
- Optionally enriches Neo4j with validated troubleshooting concepts

When graph enrichment is enabled, the first ingestion may make one LLM call
per manual chunk. xAI is used first, while Groq is reserved for qualifying
transient xAI failures.

Repeated runs are safe. Unchanged content is skipped by content hash.

---

## 8. Open and Verify the Application

Open the frontend:

```text
http://localhost:3000
```

Open the FastAPI documentation:

```text
http://localhost:8000/docs
```

Check API liveness:

```bash
curl http://localhost:8000/healthz
```

Expected response:

```json
{
  "status": "ok"
}
```

Check dependency readiness:

```bash
curl -i http://localhost:8000/readyz
```

A healthy system should report ready. If Neo4j or Weaviate is unavailable,
the endpoint may return HTTP `503` with dependency details.

Check Weaviate directly:

```bash
curl -i http://localhost:8080/v1/.well-known/ready
```

Open Neo4j Browser:

```text
http://localhost:7474
```

Local development credentials may use:

```text
Username: neo4j
Password: smartoffice123
```

Change default credentials before any shared or deployed environment.

---

## 9. Test the Chat Endpoints

### Complete response

```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Mock-User-Id: u-ali" \
  -d '{"question":"The Samsung display has no signal. What should I check?"}' \
  | python3 -m json.tool
```

### Streaming response

```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-Mock-User-Id: u-ali" \
  -d '{"question":"The Samsung display has no signal. What should I check?"}'
```

Both endpoints use the same routing, retrieval, provider fallback, citation,
and confidence pipeline.

---

## 10. Run the Backend Outside Docker

Create a local virtual environment from the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Run the backend:

```bash
uvicorn app.main:app --reload --port 8000 --app-dir backend
```

Docker must still be running Neo4j and Weaviate.

---

## 11. Run the Frontend Outside Docker

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at:

```text
http://localhost:3000
```

`NEXT_PUBLIC_API_BASE_URL` is a build-time setting. Its default value should
point to:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

After changing this value, rebuild or restart the frontend as required.

---

## 12. Run the Tests

From the repository root:

```bash
PYTHONPATH=backend pytest -q backend/tests
```

The test configuration supplies dummy provider credentials where required, so
unit tests should not need live database or external provider calls.

The suite covers areas such as:

- Router rules
- Entity matching
- LLM provider fallback
- Confidence calculations
- Citation assembly
- Output protection
- Permission handling
- Ingestion behavior

---

## 13. Run Validation Checks

Before opening or merging a pull request:

```bash
python -m compileall -q backend/app backend/tests
PYTHONPATH=backend pytest -q backend/tests/test_output_guard.py backend/tests/test_llm_provider_fallback.py
docker compose config --quiet
docker compose build api web
```

These checks validate:

- Python syntax
- Output guard behavior
- xAI-to-Groq fallback behavior
- Docker Compose configuration
- API image build
- Frontend image build

---

## 14. Run the Evaluation

With the backend running and seeded:

```bash
cd eval
python -u run_eval.py --subset smoke --skip-health
python -u run_eval.py
```

Useful optional flags may include:

```text
--seeds N
--skip-ablation
--skip-ladder
--base-url URL
```

Generated reports are written to:

```text
eval/reports/
```

Failure analysis is written to:

```text
eval/failure_cases.md
```

Evaluation outputs may include:

- Grounded rate
- Correctness rate
- Routing accuracy
- Confidence calibration
- Retrieval Recall@5
- Mean Reciprocal Rank
- p95 latency
- Error analysis by route and device
- Baseline and ablation comparisons

---

## 15. Troubleshooting

| Symptom | Likely cause | Corrective action |
|---|---|---|
| Missing `XAI_API_KEY` or `GROQ_API_KEY` | Root `.env` is missing or incomplete | Add all required provider variables and restart the API |
| Missing `XAI_BASE_URL`, `XAI_MODEL`, or `GROQ_MODEL` | Provider configuration is incomplete | Add the missing values to `.env` |
| `ModuleNotFoundError: openai` inside the API container | Docker image is stale | Run `docker compose build --no-cache api`, then restart |
| `/healthz` succeeds but `/readyz` returns `503` | API is alive, but Neo4j or Weaviate is unavailable | Check `docker compose ps` and dependency logs |
| Weaviate is unreachable | REST or gRPC port is blocked | Verify ports `8080` and `50051` |
| Neo4j is unreachable | Container is unhealthy or credentials are incorrect | Inspect `docker compose logs neo4j` |
| Manual is unmatched | Filename does not map to a known device, model, or alias | Rename the file using the catalog naming rules |
| `no extractable text found` | PDF is an image-only scan | Replace it with a text-based or OCR-processed PDF |
| First request is slow | The embedding model is downloading or loading | Allow initialization to complete |
| Frontend cannot reach backend | Backend is unavailable or the build-time API URL is incorrect | Verify port `8000` and `NEXT_PUBLIC_API_BASE_URL` |
| Browser reports a CORS error | Frontend origin is not allowed | Update `CORS_ORIGINS` and restart the API |
| Enrichment is slow or consumes excessive tokens | Per-chunk enrichment is enabled | Set `ENABLE_GRAPH_ENRICHMENT=false` during development |
| Port already in use | Another process uses a required port | Stop the conflicting process or update Docker mappings |
| Docker rebuild downloads everything | Build cache was removed or disk pressure evicted layers | Check `docker system df` and clean unused images carefully |

---

## 16. Stop and Reset the Environment

Stop the stack while keeping persistent data:

```bash
docker compose down
```

Stop the stack and remove Neo4j and Weaviate volumes:

```bash
docker compose down -v
```

Remove ingestion history to force a complete re-ingestion:

```bash
rm -f data/ingest_manifest.sqlite
```

After a full reset:

```bash
docker compose up -d --build
docker compose exec api python -m app.graph.graph_loader
docker compose exec api python -m app.ingestion.pipeline
docker compose ps
```

> **Warning:** `docker compose down -v` and deleting the ingestion manifest
> are destructive local-development operations. Use them only when a full
> rebuild is intended.