# FacilityGraph AI — Operations Runbook

This runbook provides the operational procedures required to start, verify,
monitor, troubleshoot, recover, and demonstrate FacilityGraph AI.

**Audience:** Developers, operators, demo owners, and maintainers  
**Repository:** `https://github.com/capstone-group1-team1/main-repo.git`  
**Companion documentation:**

- [`README.md`](./README.md) — project overview and quick start
- [`Setup.md`](./Setup.md) — first-time installation and environment setup
- [`Architecture.md`](./Architecture.md) — internal architecture and design
- [`Executive_Briefing.md`](./Executive_Briefing.md) — non-technical overview

---

## 1. Operational Overview

FacilityGraph AI is a hybrid RAG and Knowledge Graph assistant for smart
office maintenance. The application combines:

- A Next.js user interface
- A FastAPI backend
- Neo4j for structured device, room, relationship, and incident data
- Weaviate for semantic retrieval over manuals and incidents
- xAI as the primary LLM provider
- Groq as a controlled fallback provider
- Prometheus/OpenMetrics-compatible observability endpoints

### LLM provider behavior

| Provider | Model | Role |
|---|---|---|
| xAI | `grok-4.5` | Primary LLM provider |
| Groq | `meta-llama/llama-4-scout-17b-16e-instruct` | Fallback for qualifying transient xAI failures |

Groq fallback is used only when xAI encounters one of the following transient
conditions:

- HTTP `429`
- Request timeout
- Connection failure
- HTTP `5xx`

Authentication and configuration errors do **not** trigger fallback. These
errors must be corrected in the environment configuration.

---

## 2. System Components and Addresses

| Component | Responsibility | Address |
|---|---|---|
| Frontend | Next.js user interface | `http://localhost:3000` |
| Backend API | Request orchestration, permissions, routing, retrieval, and synthesis | `http://localhost:8000` |
| API documentation | FastAPI Swagger UI | `http://localhost:8000/docs` |
| Neo4j Browser | Knowledge graph administration | `http://localhost:7474` |
| Neo4j Bolt | Application graph connection | `bolt://localhost:7687` |
| Weaviate REST | Vector database REST interface | `http://localhost:8080` |
| Weaviate gRPC | Weaviate v4 client connection | `localhost:50051` |
| xAI | Primary external LLM API | Configured through `.env` |
| Groq | External fallback LLM API | Configured through `.env` |

The frontend uses:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## 3. Required Environment Configuration

The root `.env` file must contain the configured LLM providers:

```env
XAI_API_KEY=your_xai_api_key
XAI_BASE_URL=your_xai_base_url
XAI_MODEL=grok-4.5

GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

Common optional settings include:

```env
ENABLE_GRAPH_ENRICHMENT=true
LOG_LEVEL=INFO
CORS_ORIGINS=http://localhost:3000
```

Operational requirements:

- Never commit `.env` or API keys.
- Do not hardcode secrets in source files.
- Restrict `CORS_ORIGINS` to trusted frontend origins.
- Replace default database credentials before shared or production-style use.

---

## 4. Start, Stop, and Inspect the Stack

Run these commands from the repository root.

### 4.1 Start only the data services

Use this mode when running the backend and frontend manually:

```bash
docker compose up -d neo4j weaviate
docker compose ps
```

### 4.2 Start the complete stack

This builds and starts Neo4j, Weaviate, the API, and the frontend:

```bash
docker compose up -d --build
docker compose ps
```

Wait until the required services report a healthy status.

### 4.3 View logs

```bash
docker compose logs -f api
docker compose logs -f web
docker compose logs -f neo4j
docker compose logs -f weaviate
```

To show only recent lines:

```bash
docker compose logs --tail=100 api
```

### 4.4 Restart a service

```bash
docker compose restart api
```

Replace `api` with `web`, `neo4j`, or `weaviate` as needed.

### 4.5 Stop the stack

Stop services while preserving persistent data:

```bash
docker compose down
```

Stop services and remove Neo4j and Weaviate volumes:

```bash
docker compose down -v
```

> **Warning:** `docker compose down -v` removes persisted graph and vector
> data. Use it only when a full reset is intended.

---

## 5. Health and Observability

### 5.1 Health endpoints

| Endpoint | Purpose | Expected behavior |
|---|---|---|
| `GET /healthz` | Application liveness | Confirms that the API process is running |
| `GET /readyz` | Dependency readiness | Returns `503` when Neo4j or Weaviate is unavailable |
| `GET /metrics` | Prometheus/OpenMetrics metrics | Exposes request counts, latency, and in-flight requests |
| `GET /users` | Seeded user verification | Confirms that the five mock users are available |

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

Check container health:

```bash
docker compose ps
```

Open Neo4j Browser:

```text
http://localhost:7474
```

### 5.3 Request tracing

API responses include an `X-Request-ID` header. The same identifier is written
to the backend logs and should be used to trace a request across:

- Request start and completion
- Router decision
- Retrieval operations
- LLM provider calls
- Response assembly
- Errors

Example:

```bash
curl -i http://localhost:8000/healthz
```

Copy the returned `X-Request-ID`, then search the API logs for that value.

---

## 6. Demo-Day Readiness Checklist

Complete these checks before a live demonstration:

- [ ] `.env` exists and contains valid xAI and Groq settings.
- [ ] `docker compose config --quiet` succeeds.
- [ ] All required containers are healthy.
- [ ] `/healthz` returns successfully.
- [ ] `/readyz` confirms Neo4j and Weaviate readiness.
- [ ] The frontend loads at `http://localhost:3000`.
- [ ] At least one known `GRAPH_ONLY` question succeeds.
- [ ] At least one known `RAG_ONLY` question succeeds.
- [ ] At least one known `HYBRID` question succeeds.
- [ ] Citations are visible and correctly numbered.
- [ ] Confidence badges appear as expected.
- [ ] Device and incident views load.
- [ ] API and container logs show no unresolved errors.
- [ ] A recent backup or reproducible reseeding path is available.
- [ ] The team knows who owns each technical area during Q&A.

Recommended pre-demo command sequence:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl http://localhost:8000/healthz
curl -i http://localhost:8000/readyz
python scripts/smoke_test.py
```

---

## 7. Common Operational Procedures

## 7.1 Replace a Device

**Endpoint:** `POST /devices/replace`  
**Required role:** `admin`

The replacement operation runs as a single Neo4j transaction. It:

1. Retires the old device.
2. Creates the replacement device.
3. Repoints structural relationships.
4. Creates a `REPLACED_BY` relationship.
5. Preserves the old device and its historical incidents.
6. Re-ingests a supplied replacement manual when applicable.

The old device is never deleted, preserving:

- Incident history
- Installation dates
- Retirement dates
- Replacement lineage

### Expected responses

- **Success:** Returns a `ReplacementSummary`.
- **Failure:** Returns HTTP `409` with fields such as:

```json
{
  "failed_step": "step_name",
  "reason": "failure explanation",
  "note": "transaction rolled back"
}
```

The transaction is fully rolled back on failure. No partial replacement should
require manual cleanup.

### Post-operation verification

- Confirm the old device remains queryable.
- Confirm the new device exists.
- Confirm `REPLACED_BY` is present.
- Confirm structural relationships point to the new device.
- Confirm relevant incident history remains attached to the retired device.
- Confirm the replacement manual is searchable when one was supplied.

---

## 7.2 Log an Incident

**Endpoint:** `POST /incidents`  
**Required role:** `technician` or `admin`

Operators receive HTTP `403`.

A successful incident operation:

1. Creates the incident node in Neo4j.
2. Creates the appropriate `HAS_INCIDENT` relationship.
3. Indexes the incident in Weaviate.
4. Makes the incident available for retrieval and citation.

No separate re-ingestion step is required.

### Post-operation verification

- Confirm the API returns a success response.
- Confirm the incident appears in the incident view.
- Ask a question that should retrieve the new incident.
- Confirm the answer cites the incident where relevant.

---

## 7.3 Add or Re-ingest a Manual

Place the PDF in:

```text
data/manuals_pdf/
```

Use the naming rules documented in [`Setup.md`](./Setup.md).

Run the complete seed process:

```bash
bash scripts/seed_all.sh
```

Or run only the ingestion pipeline:

```bash
cd backend
python -m app.ingestion.pipeline
```

### Ingestion behavior

| Situation | Expected behavior |
|---|---|
| Same content uploaded again | Content hash matches; duplicate ingestion is skipped |
| Same content under a different filename | Content hash matches; duplicate chunks are not created |
| Manual content changes | Old chunks are replaced and the manifest version advances |
| Process is interrupted | The item remains pending and is retried on the next run |
| Manual is missing | The pipeline logs a warning and continues |
| PDF contains no extractable text | The file is rejected and must be replaced with a text-based PDF |

When graph enrichment is enabled, ingestion may call the LLM once per manual
chunk. xAI is used first, while Groq is reserved for qualifying transient
failures.

---

## 8. Testing and Validation

### 8.1 Complete backend test suite

```bash
cd backend
pytest tests -q
```

The suite covers areas such as:

- Query routing
- Confidence calculations
- Citation assembly
- Document chunking
- Permission handling
- Output safety
- LLM provider fallback behavior

Live database and external provider calls should not be required for unit
tests when mocks and test fixtures are used.

### 8.2 Required validation checks

Run from the repository root:

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

### 8.3 Smoke test

Requires a running and seeded backend:

```bash
python scripts/smoke_test.py
```

The smoke test should verify:

- Health endpoint availability
- One request per routing mode
- Expected response structure
- Citation and confidence fields

### 8.4 Evaluation

```bash
cd eval
python run_eval.py --subset smoke
python run_eval.py
python run_eval.py --baseline
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

- Answer correctness
- Routing accuracy
- Citation validity
- Confidence calibration
- p95 latency
- Error analysis by route and device
- Baseline comparisons
- Next-iteration hypotheses

---

## 9. Rate Limits

| Endpoint group | Limit |
|---|---:|
| `POST /chat` | 20 requests per minute |
| Write endpoints | 10 requests per minute |
| All other endpoints | 120 requests per minute |

Write endpoints include:

- `POST /incidents`
- `POST /devices/replace`

Keep rate limiting enabled in shared and demo environments to protect service
availability and control xAI and Groq API usage.

When a client receives HTTP `429` from the application:

1. Stop repeated immediate retries.
2. Apply backoff.
3. Retry after the rate-limit window.
4. Check `/metrics` and API logs when unexpected traffic is suspected.

---

## 10. Troubleshooting Matrix

| Symptom | Likely cause | Corrective action |
|---|---|---|
| Answer has low confidence or no citations | No relevant evidence was retrieved, supporting evidence was insufficient, or routing selected an unsuitable single route | Inspect `router.decisions`, matched entities, retrieved evidence, and citation assembly logs |
| Incorrect retrieval route | Rules were inconclusive or entity matching did not detect the intended device or room | Inspect fired cues, route margin, fallback decision, and entity matches |
| HTTP `403` on `POST /incidents` | Current user has the `operator` role | Use a technician or admin user |
| HTTP `409` on `POST /devices/replace` | A replacement precondition failed | Read `failed_step` and `reason`; the transaction should already be rolled back |
| `/healthz` fails | API process is unavailable or failed during startup | Inspect `docker compose logs api` |
| `/readyz` returns `503` | Neo4j or Weaviate is unavailable | Run `docker compose ps`, then inspect the affected service logs |
| Weaviate connection error | REST or gRPC connectivity is unavailable | Verify ports `8080` and `50051` and confirm container health |
| Neo4j connection error | Neo4j is not healthy or credentials are incorrect | Inspect `docker compose logs neo4j` and verify the configured credentials |
| Missing `XAI_API_KEY` | Root `.env` is missing or incomplete | Set `XAI_API_KEY`, `XAI_BASE_URL`, and `XAI_MODEL` |
| Missing Groq settings | Fallback configuration is incomplete | Set `GROQ_API_KEY` and `GROQ_MODEL` |
| xAI HTTP `429`, timeout, connection failure, or HTTP `5xx` | Transient primary-provider failure | Confirm that the Groq fallback is invoked and inspect provider logs |
| xAI authentication or configuration error | Invalid key, base URL, model, or provider configuration | Correct the xAI settings; fallback should not occur |
| Frontend cannot reach backend | Backend is unavailable or `NEXT_PUBLIC_API_BASE_URL` is incorrect | Verify the API on port `8000` and check `frontend/.env` |
| Browser CORS error | Frontend origin is not permitted | Add the origin to `CORS_ORIGINS` and restart the API |
| Manual is never searchable | Ingestion failed, remained pending, or the filename did not map to a device | Re-run seeding and inspect ingestion logs |
| `no extractable text found` | Manual is an image-only scan | Replace it with a text-based or OCR-processed PDF |
| First request is slow | Embedding model is downloading or loading | Allow initialization to complete; later requests should be faster |
| Enrichment is slow or consumes excessive tokens | Per-chunk LLM enrichment is enabled | Set `ENABLE_GRAPH_ENRICHMENT=false` during development |
| Port already in use | Another process is using a required port | Stop the conflicting process or update Docker port mappings |
| HTTP `429` from FacilityGraph AI | Application rate limit exceeded | Wait for the rate-limit window and use backoff |

---

## 11. Recovery Procedures

## 11.1 Recover a single service

Restart the affected service first:

```bash
docker compose restart <service>
```

Then inspect its status and logs:

```bash
docker compose ps
docker compose logs --tail=100 <service>
```

Avoid resetting the complete environment until service-level recovery has
failed.

## 11.2 Recover from a failed device replacement

Device replacement is transactional. On failure:

1. Inspect the HTTP `409` response.
2. Confirm the old device and relationships are unchanged.
3. Review the relevant API logs using `X-Request-ID`.
4. Correct the failed precondition.
5. Retry the operation.

Do not manually repair Neo4j unless transaction rollback verification shows an
unexpected state.

## 11.3 Recover ingestion

Re-run the idempotent seed process:

```bash
bash scripts/seed_all.sh
```

The ingestion manifest detects unchanged, changed, and pending documents.

To force a complete re-ingestion:

```bash
rm -f data/ingest_manifest.sqlite
bash scripts/seed_all.sh
```

> **Caution:** Removing the manifest forces the system to process all eligible
> content again.

## 11.4 Rebuild vector data

When the Weaviate index is corrupted or intentionally reset:

```bash
docker compose down
docker volume ls
```

Use the project-specific volume names to remove only the intended Weaviate
data, then restart and reseed. For a complete local reset:

```bash
docker compose down -v
rm -f data/ingest_manifest.sqlite
docker compose up -d --build
bash scripts/seed_all.sh
```

## 11.5 Full environment reset

```bash
docker compose down -v
rm -f data/ingest_manifest.sqlite
docker compose up -d --build
bash scripts/seed_all.sh
docker compose ps
curl http://localhost:8000/healthz
curl -i http://localhost:8000/readyz
```

---

## 12. Logging and Observability

The backend writes structured operational logs to standard output.

Important log events include:

| Event | Purpose |
|---|---|
| `router.decisions` | Chosen route, router confidence, decision mechanism, and matched entities |
| Provider call events | Selected provider, model, latency, status, and token usage where available |
| Retrieval events | Vector and graph retrieval details |
| Citation assembly events | Citation mapping and unsupported-content handling |
| Confidence events | Retrieval, graph, and final confidence signals |
| Ingestion events | Document state, chunking, embedding, enrichment, and manifest updates |
| Request completion events | Status, latency, and `X-Request-ID` |

Router decision mechanisms may include:

- `rules`
- `llm_fallback`
- `default_hybrid`

Enable detailed logs:

```env
LOG_LEVEL=DEBUG
```

Use debug logging temporarily. Avoid leaving sensitive prompts, secrets, or
excessive payload details in shared logs.

### Recommended log investigation order

1. Find the `X-Request-ID`.
2. Confirm the request reached the API.
3. Inspect the routing decision.
4. Inspect graph and vector retrieval.
5. Check xAI and Groq provider events.
6. Inspect citation assembly.
7. Inspect confidence calculation.
8. Confirm the final HTTP status and latency.

---

## 13. Data Persistence and Backup

Neo4j and Weaviate use Docker named volumes.

Data is preserved when running:

```bash
docker compose down
```

Data is removed when running:

```bash
docker compose down -v
```

The current project is designed for local and demonstration environments and
does not include a complete managed backup and restore workflow.

Before production-style deployment, add:

- Scheduled Neo4j backups
- Weaviate backup procedures
- Off-host backup storage
- Restore testing
- Backup retention rules
- Secret management
- Access control and audit logging
- Environment-specific configuration

The source CSV files, manuals, and ingestion process provide a reproducible
path for rebuilding local data, but they are not a substitute for a tested
production backup strategy.

---

## 14. Security and Operational Safety

- Never commit API keys or `.env`.
- Replace default Neo4j credentials outside local development.
- Use the mock user header only in trusted development and demo environments.
- Restrict CORS origins.
- Keep rate limiting enabled.
- Do not expose Neo4j, Weaviate, or internal metrics publicly without controls.
- Avoid logging secrets, authorization headers, or complete sensitive prompts.
- Review dependency and container updates before production use.
- Treat `docker compose down -v` as a destructive command.
- Validate provider fallback behavior after changing LLM configuration.

---

## 15. Escalation and Ownership

| Area | Primary owner |
|---|---|
| Synthesis, query router, citations, confidence, and Docker | Ibrahim Yasin |
| Backend API, Neo4j, Weaviate, and permission integration | Afnan Tayem |
| End-to-end pipeline, ingestion, architecture coordination, and evaluation | Amer Almajali |
| Evaluation framework, metrics, monitoring, and baseline comparison | Mohammad Zalloum |

Before publishing or presenting this runbook, confirm that ownership still
matches the team’s current responsibilities.

### Escalation information to provide

Include the following when escalating an issue:

- Date and time
- Environment
- Affected endpoint or service
- `X-Request-ID`
- HTTP status
- Relevant log excerpt
- Recent deployment or configuration changes
- Steps already attempted
- User-visible impact

---

## 16. Quick Command Reference

```bash
# Build and start the full stack
docker compose up -d --build

# Check service status
docker compose ps

# Check API health and readiness
curl http://localhost:8000/healthz
curl -i http://localhost:8000/readyz

# Follow API logs
docker compose logs -f api

# Seed or re-ingest data
bash scripts/seed_all.sh

# Run smoke verification
python scripts/smoke_test.py

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
bash scripts/seed_all.sh
```