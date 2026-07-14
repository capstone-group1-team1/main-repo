# GridSense Office — Operations Runbook

This runbook defines the operational procedures for starting, verifying,
monitoring, troubleshooting, recovering, and demonstrating GridSense Office.

**Audience:** Developers, operators, demo owners, and maintainers  
**Repository:** `https://github.com/capstone-group1-team1/main-repo.git`  
**Companion documentation:**

- [`README.md`](./README.md) — project overview and quick start
- [`Setup.md`](./Setup.md) — first-time installation and configuration
- [`Architecture.md`](./Architecture.md) — internal system architecture
- [`Executive_Briefing.md`](./Executive_Briefing.md) — non-technical overview

---

## 1. Operational Overview

GridSense Office is a hybrid RAG and Knowledge Graph assistant for smart
office maintenance.

The system combines:

- A Next.js frontend
- A FastAPI backend
- Neo4j for structured facility knowledge
- Weaviate for semantic retrieval
- xAI as the primary LLM provider
- Groq as the fallback LLM provider
- Prometheus/OpenMetrics-compatible observability
- Role-based access controls
- Citation validation and confidence scoring

### LLM provider strategy

| Provider | Model | Role |
|---|---|---|
| xAI | `grok-4.5` | Primary LLM provider |
| Groq | `meta-llama/llama-4-scout-17b-16e-instruct` | Fallback for qualifying transient xAI failures |

Groq fallback is used only when xAI encounters:

- HTTP `429`
- Request timeout
- Connection failure
- HTTP `5xx`

Authentication and configuration errors do not trigger fallback.

---

## 2. System Components

| Component | Responsibility | Address |
|---|---|---|
| Frontend | Next.js user interface | `http://localhost:3000` |
| Backend API | Routing, retrieval, synthesis, permissions, and orchestration | `http://localhost:8000` |
| API documentation | FastAPI Swagger UI | `http://localhost:8000/docs` |
| Neo4j Browser | Graph administration and inspection | `http://localhost:7474` |
| Neo4j Bolt | Application graph connection | `bolt://localhost:7687` |
| Weaviate REST | Vector database REST endpoint | `http://localhost:8080` |
| Weaviate gRPC | Weaviate v4 client connection | `localhost:50051` |
| xAI | Primary external LLM API | Configured through `.env` |
| Groq | External fallback LLM API | Configured through `.env` |

The frontend uses:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## 3. Required Environment Configuration

The root `.env` file must include:

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

Operational requirements:

- Never commit `.env` or API keys.
- Do not hardcode secrets in tracked files.
- Restrict `CORS_ORIGINS` to trusted frontend origins.
- Replace default database credentials before shared or production-style use.
- Restart or recreate the API container after environment changes.

---

## 4. Start, Stop, and Inspect the Stack

Run these commands from the repository root.

### 4.1 Start Neo4j and Weaviate only

Use this mode when running the backend and frontend manually:

```bash
docker compose up -d neo4j weaviate
docker compose ps
```

### 4.2 Start the complete stack

```bash
docker compose up -d --build
docker compose ps
```

This starts:

- Neo4j
- Weaviate
- FastAPI backend
- Next.js frontend

Use a no-cache build only when diagnosing stale dependencies or images:

```bash
docker compose build --no-cache api web
docker compose up -d
```

### 4.3 View logs

```bash
docker compose logs -f api
docker compose logs -f web
docker compose logs -f neo4j
docker compose logs -f weaviate
```

Show only recent lines:

```bash
docker compose logs --tail=100 api
```

### 4.4 Restart one service

```bash
docker compose restart api
```

Replace `api` with `web`, `neo4j`, or `weaviate` as required.

### 4.5 Stop the stack

Preserve persistent data:

```bash
docker compose down
```

Remove Neo4j and Weaviate volumes:

```bash
docker compose down -v
```

> **Warning:** `docker compose down -v` is destructive and removes persisted
> graph and vector data.

---

## 5. Health and Observability

### 5.1 Health endpoints

| Endpoint | Purpose | Expected behavior |
|---|---|---|
| `GET /healthz` | Liveness | Returns `{"status":"ok"}` when the API process is running |
| `GET /readyz` | Dependency readiness | Returns `503` when Neo4j or Weaviate is unavailable |
| `GET /metrics` | Prometheus/OpenMetrics metrics | Exposes request counts, latency, and in-flight requests |
| `GET /users` | Seeded-user verification | Confirms the five mock users are loaded |

Examples:

```bash
curl http://localhost:8000/healthz
curl -i http://localhost:8000/readyz
curl http://localhost:8000/metrics
curl http://localhost:8000/users
```

### 5.2 Direct dependency checks

Check Weaviate readiness:

```bash
curl -i http://localhost:8080/v1/.well-known/ready
```

Check service status:

```bash
docker compose ps
```

Open Neo4j Browser:

```text
http://localhost:7474
```

### 5.3 Request tracing

Every API response includes an `X-Request-ID` header.

Use the request ID to trace:

- Request start and completion
- Routing decision
- Graph retrieval
- Vector retrieval
- LLM provider selection
- Fallback behavior
- Citation assembly
- Confidence calculation
- Final response or exception

Example:

```bash
curl -i http://localhost:8000/healthz
```

Copy the returned `X-Request-ID`, then search the API logs for the same value.

---

## 6. Demo-Day Readiness Checklist

Complete these checks before a live demonstration:

- [ ] `.env` exists and contains valid xAI and Groq settings.
- [ ] `docker compose config --quiet` succeeds.
- [ ] Required containers are healthy.
- [ ] `/healthz` succeeds.
- [ ] `/readyz` confirms Neo4j and Weaviate readiness.
- [ ] The frontend loads at `http://localhost:3000`.
- [ ] `POST /chat` succeeds.
- [ ] `POST /chat/stream` streams correctly.
- [ ] A known `GRAPH_ONLY` question succeeds.
- [ ] A known `RAG_ONLY` question succeeds.
- [ ] A known `HYBRID` question succeeds.
- [ ] Citations are visible and correctly mapped.
- [ ] Confidence badges appear as expected.
- [ ] Devices and incidents load.
- [ ] API logs contain no unresolved errors.
- [ ] The team knows the owner of each technical area.

Recommended sequence:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl http://localhost:8000/healthz
curl -i http://localhost:8000/readyz
PYTHONPATH=backend pytest -q backend/tests
```

---

## 7. Common Operational Procedures

### 7.1 Replace a Device

**Endpoint:** `POST /devices/replace`  
**Required role:** `admin`

The replacement operation runs as one Neo4j transaction.

It:

1. Validates the request and replacement device.
2. Retires the old device.
3. Creates or activates the replacement device.
4. Repoints live-topology relationships:
   - `CONNECTED_TO`
   - `CONTROLS`
   - `USES`
5. Copies the current room placement to the new device.
6. Keeps the old `CONTAINS` relationship for historical placement.
7. Creates `(old)-[:REPLACED_BY]->(new)`.
8. Preserves incidents, install dates, and retirement dates.
9. Re-ingests the replacement manual when applicable.

The old device is never deleted.

If `manual_pdf_filename` is supplied, the replacement device must already
exist in `asset_inventory.csv`. This validation occurs before graph mutation.

#### Expected responses

- **Success:** Returns a `ReplacementSummary`.
- **Failure:** Returns HTTP `409` with fields such as:

```json
{
  "failed_step": "step_name",
  "reason": "failure explanation",
  "note": "transaction rolled back"
}
```

The transaction is fully rolled back on failure.

#### Post-operation verification

- Confirm the old device remains queryable.
- Confirm the new device exists.
- Confirm `REPLACED_BY` exists.
- Confirm live-topology relationships point to the new device.
- Confirm historical room placement remains available.
- Confirm old incidents remain attached to the retired device.
- Confirm the replacement manual is searchable when supplied.

---

### 7.2 Log an Incident

**Endpoint:** `POST /incidents`  
**Required role:** `technician` or `admin`

Operators receive HTTP `403`.

The operation:

1. Creates the incident in Neo4j.
2. Creates the `HAS_INCIDENT` relationship.
3. Attempts to index the incident in Weaviate.
4. Makes the incident available for future retrieval and citation.

If Weaviate indexing fails, the incident remains stored in Neo4j. The vector
indexing step can be retried during a later ingestion run.

#### Post-operation verification

- Confirm the API returns success.
- Confirm the incident appears in the incident view.
- Ask a question that should retrieve the incident.
- Confirm the answer cites the incident where relevant.

---

### 7.3 Add or Re-ingest a Manual

Place the PDF in:

```text
data/manuals_pdf/
```

For an existing device:

```bash
docker compose exec api python -m app.ingestion.pipeline
```

For a new device, load the graph first:

```bash
docker compose exec api python -m app.graph.graph_loader
docker compose exec api python -m app.ingestion.pipeline
```

#### Ingestion behavior

| Situation | Expected behavior |
|---|---|
| Same content uploaded again | Content hash matches; duplicate ingestion is skipped |
| Same content under another filename | Duplicate chunks are not created |
| Manual content changes | Old source-specific chunks are replaced |
| Process is interrupted | The item remains pending and is retried |
| Manual is missing | A warning is logged and processing continues |
| PDF contains no text layer | The file is rejected |

When graph enrichment is enabled, ingestion may call the LLM per manual chunk.
xAI is primary, and Groq is reserved for qualifying transient failures.

---

## 8. Testing and Evaluation

### 8.1 Unit tests

Run from the repository root:

```bash
PYTHONPATH=backend pytest -q backend/tests
```

The suite covers areas such as:

- Router rules
- Held-out routing behavior
- LLM provider fallback
- Streaming fallback behavior
- Confidence calculations
- Citation assembly
- Permission handling
- Output protection

Unit tests should not require live databases or external provider calls when
test fixtures and mocks are active.

### 8.2 Focused validation

```bash
python -m compileall -q backend/app backend/tests
PYTHONPATH=backend pytest -q backend/tests/test_output_guard.py backend/tests/test_llm_provider_fallback.py
docker compose config --quiet
docker compose build api web
```

### 8.3 Evaluation

Fast evaluation:

```bash
cd eval
python -u run_eval.py --subset smoke --skip-health
```

Full evaluation:

```bash
python -u run_eval.py
```

Useful optional flags may include:

```text
--seeds N
--skip-ablation
--skip-ladder
--base-url URL
```

Reports are written to:

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

## 9. Rate Limits

| Endpoint group | Limit |
|---|---:|
| `POST /chat` and `POST /chat/stream` | 20 requests per minute |
| Write endpoints | 10 requests per minute |
| All other endpoints | 120 requests per minute |

Write endpoints include:

- `POST /incidents`
- `POST /devices/replace`

Keep rate limiting enabled in shared and demo environments to protect service
availability and control xAI and Groq usage.

When the application returns HTTP `429`:

1. Stop immediate repeated retries.
2. Apply backoff.
3. Retry after the rate-limit window.
4. Inspect `/metrics` and API logs if traffic is unexpected.

---

## 10. Troubleshooting Matrix

| Symptom | Likely cause | Corrective action |
|---|---|---|
| Low confidence or no citations | Weak retrieval, missing evidence, or unsuitable route | Inspect `router.decisions`, matched entities, retrieval results, and citation logs |
| Incorrect route | Rules were inconclusive or entity matching failed | Inspect fired cues, route margin, fallback decision, and entity matches |
| HTTP `403` on `POST /incidents` | User role is `operator` | Use a technician or admin user |
| HTTP `409` on `POST /devices/replace` | Replacement precondition failed | Read `failed_step` and `reason`; verify rollback |
| `/healthz` fails | API process failed or did not start | Inspect `docker compose logs api` |
| `/readyz` returns `503` | Neo4j or Weaviate is unavailable | Run `docker compose ps`, then inspect dependency logs |
| Weaviate connection error | REST or gRPC connectivity is unavailable | Verify ports `8080` and `50051` |
| Neo4j connection error | Container is unhealthy or credentials are wrong | Inspect `docker compose logs neo4j` |
| Missing xAI configuration | Root `.env` is incomplete | Set `XAI_API_KEY`, `XAI_BASE_URL`, and `XAI_MODEL` |
| Missing Groq configuration | Fallback settings are incomplete | Set `GROQ_API_KEY` and `GROQ_MODEL` |
| xAI returns `429`, timeout, connection failure, or `5xx` | Transient primary-provider failure | Confirm that Groq fallback is invoked |
| xAI authentication or configuration error | Invalid key, URL, or model | Correct the xAI configuration; fallback should not occur |
| `ModuleNotFoundError` inside the API container | Docker image is stale | Rebuild the API image with `--no-cache` |
| Manual is not linked to a device | Filename does not map to a device, model, or alias | Rename the file using the catalog convention |
| `no extractable text found` | PDF is an image-only scan | Replace it with a text-based or OCR-processed PDF |
| Ingestion remains pending | Previous run was interrupted | Re-run the ingestion pipeline |
| Frontend cannot reach backend | Backend is unavailable or API URL is incorrect | Verify port `8000` and rebuild the frontend after URL changes |
| Browser CORS error | Frontend origin is not permitted | Update `CORS_ORIGINS` and restart the API |
| First request is slow | Embedding model is loading or downloading | Allow initialization to finish |
| Enrichment is slow or expensive | Per-chunk LLM enrichment is enabled | Set `ENABLE_GRAPH_ENRICHMENT=false` during development |
| `/chat` is unusually slow | Provider retries, fallback, cold model, or reranker overhead | Inspect API logs and confirm `RERANK_ENABLED` |
| Port already in use | Another process uses a required port | Stop the conflicting process or update Docker mappings |
| Docker rebuild downloads everything | Build cache was evicted or removed | Check `docker system df` and clean unused images carefully |

---

## 11. Recovery Procedures

### 11.1 Recover one service

```bash
docker compose restart <service>
docker compose ps
docker compose logs --tail=100 <service>
```

Attempt service-level recovery before resetting the full environment.

### 11.2 Recover from a failed device replacement

1. Read the HTTP `409` response.
2. Find the `X-Request-ID`.
3. Inspect the related API logs.
4. Confirm that the old graph state remains intact.
5. Correct the failed precondition.
6. Retry the operation.

Do not manually repair Neo4j unless rollback verification reveals an
unexpected state.

### 11.3 Recover ingestion

```bash
docker compose exec api python -m app.ingestion.pipeline
```

For a new device:

```bash
docker compose exec api python -m app.graph.graph_loader
docker compose exec api python -m app.ingestion.pipeline
```

The manifest detects unchanged, changed, and pending documents.

### 11.4 Full reset

```bash
docker compose down -v
rm -f data/ingest_manifest.sqlite
docker compose up -d --build
docker compose exec api python -m app.graph.graph_loader
docker compose exec api python -m app.ingestion.pipeline
docker compose ps
curl http://localhost:8000/healthz
curl -i http://localhost:8000/readyz
```

> **Important:** `data/ingest_manifest.sqlite` is a bind-mounted file rather
> than a Docker volume. Removing Docker volumes alone does not reset the
> ingestion manifest.

---

## 12. Logging and Observability

The backend writes structured operational logs to standard output.

Important events include:

| Event | Purpose |
|---|---|
| `router.decisions` | Selected route, router confidence, mechanism, and matched entities |
| Provider events | Selected provider, model, retries, fallback, latency, and status |
| Retrieval events | Graph and vector retrieval behavior |
| Citation events | Marker validation and unsupported-span detection |
| Confidence events | Retrieval, graph, and final confidence signals |
| Ingestion events | Document status, chunking, embedding, enrichment, and manifest updates |
| Request completion | Status, latency, and `X-Request-ID` |

Router mechanisms may include:

- `rules`
- `llm_fallback`
- `default_hybrid`

Enable detailed logs:

```env
LOG_LEVEL=DEBUG
```

Use debug logging temporarily. Avoid exposing secrets or excessive sensitive
payload details in shared logs.

### Recommended investigation order

1. Find the `X-Request-ID`.
2. Confirm the request reached the API.
3. Inspect entity matching and routing.
4. Inspect graph and vector retrieval.
5. Check xAI and Groq provider events.
6. Inspect citation assembly.
7. Inspect confidence calculation.
8. Confirm the final status and latency.

---

## 13. Data Persistence and Backup

Neo4j and Weaviate use Docker named volumes.

Data is preserved with:

```bash
docker compose down
```

Data is removed with:

```bash
docker compose down -v
```

The current deployment is intended for local and demonstration use and does
not include a complete managed backup and restore process.

Before production-style use, add:

- Scheduled Neo4j backups
- Weaviate backup procedures
- Off-host storage
- Restore testing
- Retention rules
- Secret management
- Audit logging
- Environment-specific access controls

Source CSV files, manuals, and the ingestion process provide a reproducible
local rebuild path, but they are not a substitute for a tested production
backup strategy.

---

## 14. Security and Operational Safety

- Never commit API keys or `.env`.
- Replace default Neo4j credentials outside local development.
- Use mock-user headers only in trusted development and demo environments.
- Restrict CORS origins.
- Keep rate limiting enabled.
- Do not expose Neo4j, Weaviate, or metrics publicly without controls.
- Avoid logging secrets, authorization headers, or sensitive prompts.
- Treat `docker compose down -v` as destructive.
- Validate provider fallback after LLM configuration changes.
- Review dependency and container updates before production use.

---

## 15. Escalation and Ownership

| Area | Primary owner |
|---|---|
| Synthesis, query router, citations, confidence, and Docker | Ibrahim Yasin |
| Backend API, Neo4j, Weaviate, and permission integration | Afnan Tayem |
| End-to-end pipeline, ingestion, architecture coordination, and evaluation | Amer Almajali |
| Evaluation framework, metrics, monitoring, and baseline comparison | Mohammad Zalloum |

When escalating an issue, provide:

- Date and time
- Environment
- Affected service or endpoint
- `X-Request-ID`
- HTTP status
- Relevant logs
- Recent code or configuration changes
- Steps already attempted
- User-visible impact

---

## 16. Quick Command Reference

```bash
# Start the complete stack
docker compose up -d --build

# Check service status
docker compose ps

# Check API health and readiness
curl http://localhost:8000/healthz
curl -i http://localhost:8000/readyz

# Follow API logs
docker compose logs -f api

# Load the graph
docker compose exec api python -m app.graph.graph_loader

# Ingest manuals and incidents
docker compose exec api python -m app.ingestion.pipeline

# Run unit tests
PYTHONPATH=backend pytest -q backend/tests

# Run focused validation
python -m compileall -q backend/app backend/tests
PYTHONPATH=backend pytest -q backend/tests/test_output_guard.py backend/tests/test_llm_provider_fallback.py
docker compose config --quiet

# Stop while preserving data
docker compose down

# Full destructive reset
docker compose down -v
rm -f data/ingest_manifest.sqlite
docker compose up -d --build
docker compose exec api python -m app.graph.graph_loader
docker compose exec api python -m app.ingestion.pipeline