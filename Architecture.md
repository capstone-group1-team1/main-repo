# GridSense Office — System Architecture

**System:** Hybrid RAG + Knowledge Graph Assistant for Smart Office Maintenance  
**Project:** AI.SPIRE Capstone — Group 1, Team 1  
**Repository:** `https://github.com/capstone-group1-team1/main-repo.git`  
**Status:** Capstone implementation for local and demonstration environments  
**Last updated:** 14 July 2026

---

## 1. Architecture Overview

GridSense Office is an evidence-driven maintenance assistant that combines
unstructured document retrieval with structured facility knowledge.

The system uses two complementary knowledge stores:

- **Weaviate** stores semantically searchable content from device manuals and
  historical incident records.
- **Neo4j** stores devices, rooms, topology, lifecycle information, incidents,
  and extracted troubleshooting concepts.

An explicit query router selects one of three retrieval strategies:

| Route | Primary purpose |
|---|---|
| `GRAPH_ONLY` | Device relationships, room topology, lifecycle history, and structured facts |
| `RAG_ONLY` | Manual instructions, troubleshooting procedures, and unstructured incident evidence |
| `HYBRID` | Questions requiring both structured and unstructured evidence, or cases where routing remains uncertain |

Retrieved evidence is passed through merge and optional reranking stages before
the synthesis layer generates an answer. xAI is the primary LLM provider;
Groq is used only for qualifying transient xAI failures.

The final response is processed by citation validation and confidence scoring
before it is returned either as a complete response or as a token stream.

### Architectural principles

1. **Retrieve evidence before generation**
2. **Use explicit, testable routing**
3. **Preserve source identity end to end**
4. **Expose uncertainty through confidence scoring**
5. **Degrade gracefully when one dependency fails**
6. **Keep operational behavior observable and traceable**

---

## 2. High-Level Architecture

```text
┌──────────────────────────────┐
│         Next.js UI           │
│       localhost:3000         │
└──────────────┬───────────────┘
               │ HTTP
               │ X-Mock-User-Id
               ▼
┌──────────────────────────────┐
│        FastAPI Backend       │
│       localhost:8000         │
│                              │
│ Auth · Permissions · APIs    │
│ Rate Limits · Observability  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│         Query Router         │
│                              │
│ Entity Match → Rules →       │
│ LLM Fallback → HYBRID        │
└───────┬──────────┬───────────┘
        │          │
        │          │
        ▼          ▼
┌──────────────┐  ┌──────────────┐
│    Neo4j     │  │   Weaviate   │
│ Graph facts  │  │ Manuals and  │
│ and topology │  │ incidents    │
└───────┬──────┘  └──────┬───────┘
        │                 │
        └────────┬────────┘
                 ▼
┌──────────────────────────────┐
│ Retrieval Merge + Reranking  │
│ Deduplication · Evidence cap │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│      LLM Provider Layer      │
│                              │
│ Primary: xAI / grok-4.5      │
│ Fallback: Groq / Llama 4     │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ Citation + Confidence Layer  │
│ Marker validation            │
│ Unsupported-span detection   │
│ Route-aware confidence       │
└──────────────┬───────────────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
POST /chat      POST /chat/stream
Full response   SSE token stream
```

---

## 3. End-to-End Request Flow

```text
User question
    │
    ▼
Authentication and permission check
    │
    ▼
Input sanitization
    │
    ▼
Entity matching
    │
    ▼
Rule-based route scoring
    │
    ├── confident ───────────────► selected route
    │
    └── uncertain
            │
            ▼
       LLM route fallback
            │
            ├── confident ───────► selected route
            │
            └── uncertain ───────► HYBRID
                                      │
                                      ▼
                          Graph and/or vector retrieval
                                      │
                                      ▼
                          Cache lookup or cache update
                                      │
                                      ▼
                           Deduplication and reranking
                                      │
                                      ▼
                              Evidence-aware prompt
                                      │
                                      ▼
                          xAI primary synthesis request
                                      │
                         transient failure only
                                      ▼
                               Groq fallback
                                      │
                                      ▼
                         Citation assembly and checks
                                      │
                                      ▼
                          Route-aware confidence score
                                      │
                                      ▼
                           Sanitized final response
```

The retrieval cache is keyed by the question and resolved route. It stores the
merged candidate evidence before reranking, allowing cache hits to be reranked
again using the current query and configuration.

---

## 4. Query Routing Architecture

### 4.1 Entity matching

`entity_matcher.py` performs deterministic matching against device names,
models, aliases, and room names derived from the project catalog.

Its output supports:

- Route selection
- Device- or room-specific retrieval
- Graph-confidence calculation
- Explainable logging

The matcher does not require an LLM, making it fast, repeatable, and easy to
test.

### 4.2 Rule-based classification

`rules.py` scores graph, RAG, and hybrid cue groups.

Typical signals include:

- Relationship or topology language → graph
- Manual, troubleshooting, or procedure language → RAG
- Combined relationship and symptom language → hybrid

The classifier returns:

- Proposed route
- Route score
- Margin between the top and second-best route
- Fired cues

The live threshold comes from configuration:

```text
ROUTER_RULE_MARGIN_THRESHOLD
```

The compatibility default is `0.25`.

### 4.3 LLM fallback

When deterministic rules are not sufficiently decisive,
`llm_fallback.py` classifies the route through the shared LLM gateway.

The fallback result is accepted only when its confidence meets:

```text
ROUTER_FALLBACK_CONF_THRESHOLD
```

The compatibility default is `0.60`.

### 4.4 Safe default

When both the rules and LLM fallback remain uncertain, the router selects
`HYBRID`.

This choice may increase retrieval latency and token usage, but it reduces the
risk of excluding a relevant evidence source.

If the LLM route classifier itself fails, the router logs the failure and
selects `HYBRID` rather than failing the user request.

### 4.5 Router observability

Every routing decision is logged with:

- Selected route
- Router confidence
- Decision mechanism
- Matched entities
- Fired cues, where available

Decision mechanisms may include:

- `rules`
- `llm_fallback`
- `default_hybrid`

Router confidence is an internal diagnostic signal. It is separate from the
final confidence score shown to the user.

---

## 5. Retrieval Architecture

### 5.1 Vector retrieval

`vector_retriever.py` retrieves semantically relevant evidence from Weaviate.

The retrieval process may include:

- Query embedding with `BAAI/bge-large-en-v1.5`
- Dense vector similarity
- BM25 keyword matching
- Hybrid fusion controlled by `alpha`
- Device filtering when an entity is resolved
- Configurable result and evidence limits

The vector store contains:

- Manual chunks
- Historical incidents
- Source metadata
- Device and document identifiers
- Citation metadata

### 5.2 Graph retrieval

`graph_retriever.py` runs named, parameterized Cypher queries against Neo4j.

It retrieves facts such as:

- Devices located in a room
- Device-to-device connections
- Control and usage relationships
- Installation and retirement history
- Device replacement lineage
- Associated incidents
- Extracted symptoms, procedures, components, and error codes

Parameterized Cypher improves safety, repeatability, and testability.

### 5.3 Hybrid merge

For `HYBRID` requests, `hybrid_merger.py` combines graph facts and document
chunks into one candidate evidence set.

Its responsibilities include:

- Preserving source identity
- Deduplicating equivalent evidence
- Removing enrichment facts already represented by retrieved text
- Prioritizing structured facts where appropriate
- Respecting candidate-pool and evidence-budget limits

### 5.4 Retrieval cache

`retrieval_cache.py` provides an in-process LRU cache keyed by:

```text
(question, resolved route)
```

The cache is a performance optimization only. Disabling it should not change
the expected answer semantics.

The cached value is the merged candidate list before reranking, so each cache
hit can still pass through the current reranking logic.

### 5.5 Reranking

`reranker.py` uses `BAAI/bge-reranker-base` to rescore candidate evidence by
query-passage relevance.

The reranker:

1. Receives the candidate pool.
2. Scores each candidate against the question.
3. Sorts candidates by relevance.
4. Trims the final evidence set.

Reranking is currently disabled by default through:

```env
RERANK_ENABLED=false
```

The project evaluation showed only a modest Recall@5 improvement relative to
the added latency for this deployment. The feature remains available through
configuration without requiring code changes.

If the reranker is disabled or fails to load, the pipeline falls back to the
deterministic merge order.

### 5.6 Graceful degradation

A failure in one retrieval branch does not automatically fail a hybrid
request.

Examples:

- Neo4j unavailable → continue with vector evidence when possible.
- Weaviate unavailable → continue with graph evidence when possible.
- Reranker unavailable → use merge order.
- Cache unavailable or disabled → perform normal retrieval.

The final confidence score should reflect reduced evidence quality or missing
retrieval branches.

---

## 6. LLM Provider and Synthesis Architecture

### 6.1 Shared provider gateway

`groq_client.py` is the shared LLM gateway. The filename is retained from an
earlier provider design, but the module now handles both providers.

| Priority | Provider | Model | Usage |
|---|---|---|---|
| Primary | xAI | `grok-4.5` | Normal LLM requests |
| Fallback | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` | Qualifying transient xAI failures |

The gateway is used for:

- Answer synthesis
- Router LLM fallback
- Graph enrichment extraction
- Structured JSON generation
- Streaming answer generation

### 6.2 Fallback contract

Groq fallback is triggered only for transient xAI failures:

- HTTP `429`
- Request timeout
- Connection failure
- HTTP `5xx`

Fallback is not triggered for:

- Invalid API key
- Invalid base URL
- Unsupported model
- Authentication or authorization failure
- Malformed configuration
- Invalid caller request

This distinction prevents configuration errors from being silently hidden.

### 6.3 Streaming behavior

The gateway supports both:

- One-shot generation
- Streaming generation

For streaming responses, fallback is attempted only before the first token is
yielded. If a provider fails after streaming begins, the response is not
restarted with a second provider because that could duplicate content or
produce an inconsistent answer.

### 6.4 Prompt construction

`prompts.py` renders evidence into numbered source blocks.

Each block includes source identity such as:

- Source type
- Document or incident identity
- Page or chunk reference, where available
- Device or room association
- Evidence text

The model is instructed to:

- Use only supplied evidence
- Add an `[n]` marker to supported factual claims
- Avoid unsupported speculation
- State when the evidence does not cover the question

When no usable evidence exists, the application returns a controlled
insufficient-evidence response instead of asking the LLM to guess.

### 6.5 Output protection

`output_guard.py` protects structured and user-facing output by:

- Removing model-generated `<think>...</think>` blocks
- Validating JSON-mode responses
- Rejecting malformed structured output before callers trust it

`sanitize.py` provides lightweight prompt-injection protection by neutralizing
common override phrases in both the user question and retrieved evidence.

These controls reduce risk but are not a substitute for full production
security review.

---

## 7. Citation and Confidence Architecture

### 7.1 Citation chain

Traceability is maintained throughout the pipeline:

```text
Source file or graph fact
        │
        ▼
Ingestion metadata
        │
        ▼
Retrieved evidence object
        │
        ▼
Numbered prompt block
        │
        ▼
LLM [n] marker
        │
        ▼
Citation assembler
        │
        ▼
Public citation in ChatResponse
```

`citation_assembler.py` is responsible for:

- Parsing citation markers
- Rejecting markers that do not map to supplied evidence
- Deduplicating citations
- Renumbering citations compactly
- Detecting factual-looking sentences without support
- Returning unsupported spans for confidence adjustment

### 7.2 Confidence signals

`confidence.py` calculates three related values:

| Signal | Purpose |
|---|---|
| Retrieval confidence | Measures the strength and separation of vector results |
| Graph confidence | Measures entity match quality, path quality, and graph facts |
| Final confidence | Produces the route-aware user-facing score |

#### Retrieval confidence

A strong top result with a meaningful score gap is more decisive than several
similar, mediocre results.

#### Graph confidence

Graph confidence may consider:

- Exact entity matching
- Fact count
- Path length
- Path-length decay such as `0.85^(hops−1)`

#### Final confidence

The final score depends on the route:

- `GRAPH_ONLY` emphasizes graph confidence.
- `RAG_ONLY` emphasizes retrieval confidence.
- `HYBRID` combines both and may penalize disagreement.

Post-processing rules include:

- Zero citations cap the final score at `0.25`.
- Unsupported spans reduce the score proportionally.
- Missing retrieval branches may reduce the score.
- The final value is clamped to the valid range.

UI thresholds:

| Level | Threshold |
|---|---:|
| Low | `< 0.40` |
| Medium | `0.40–0.75` |
| High | `> 0.75` |

The frontend derives the displayed confidence band from the final numeric
score. The API confidence schema carries retrieval, graph, and final values.

The final confidence score is an evidence-support signal, not a mathematical
probability that the answer is correct.

---

## 8. Data Architecture

### 8.1 Source data

| Source | Purpose |
|---|---|
| `data/asset_inventory.csv` | Devices, rooms, installation details, status, firmware, and warranty data |
| `data/relationships.csv` | Physical and logical relationships |
| `data/incidents.csv` | Historical incidents |
| `data/manuals_pdf/` | Official vendor manuals |

Current capstone scope:

- 10 devices
- 4 rooms
- 24 documented relationships
- 16 incidents
- 10 manuals

### 8.2 Neo4j model

Primary node labels include:

- `Room`
- `Device`
- `Document`
- `Incident`
- `Symptom`
- `Procedure`
- `ErrorCode`
- `Component`

Primary relationships include:

- `CONTAINS`
- `CONNECTED_TO`
- `CONTROLS`
- `USES`
- `DESCRIBED_BY`
- `HAS_INCIDENT`
- `REPLACED_BY`
- `RESOLVED_BY`
- `INDICATES`
- `HAS_COMPONENT`
- `REQUIRES`

### 8.3 Temporal device lifecycle

Devices are not silently deleted.

A replacement operation runs as one Neo4j transaction:

1. Validate the replacement request.
2. Retire the old device.
3. Create or activate the replacement device.
4. Repoint live topology relationships:
   - `CONNECTED_TO`
   - `CONTROLS`
   - `USES`
5. Copy current room placement to the new device.
6. Keep the retired device's `CONTAINS` relationship as historical placement.
7. Create `(old)-[:REPLACED_BY]->(new)`.
8. Preserve prior incidents and lifecycle metadata.

This supports questions about both current and historical device placement.

### 8.4 Weaviate model

The vector database uses a collection such as:

```text
SmartOfficeChunk
```

Each object represents a manual chunk or incident and includes:

- Text content
- Source type
- Source identity
- Device association
- Document metadata
- Citation metadata
- Application-supplied vector

Weaviate uses application-generated embeddings rather than an internal
vectorizer.

### 8.5 Idempotent ingestion

The ingestion pipeline uses content hashes and a persistent manifest.

| Input state | Result |
|---|---|
| New content | Insert and mark complete |
| Unchanged content | Skip |
| Changed content | Replace source-specific chunks |
| Interrupted processing | Leave pending and retry later |

This prevents duplicate chunks and supports incremental updates.

---

## 9. Module Map

| Area | Main files | Responsibility |
|---|---|---|
| Core configuration | `core/config.py` | Environment-backed settings and cached client factories |
| Logging | `core/logging.py` | Structured logs and router-decision events |
| Observability | `core/observability.py` | Metrics middleware, request IDs, and operational instrumentation |
| Rate limiting | `core/rate_limit.py` | Shared `slowapi` limiter and endpoint limits |
| API contracts | `models/schemas.py` | Public response models and internal evidence types |
| Authentication | `auth/mock_users.py` | Seeded development and demo users |
| Authorization | `auth/permissions.py` | Role-to-action permission checks |
| Routing | `router/entity_matcher.py` | Device, model, alias, and room matching |
| Routing | `router/rules.py` | Deterministic cue-based route scoring |
| Routing | `router/llm_fallback.py` | LLM route classification when rules are uncertain |
| Routing | `router/query_router.py` | Routing orchestration and HYBRID default |
| Ingestion | `ingestion/pdf_reader.py` | PDF text extraction |
| Ingestion | `ingestion/chunker.py` | Semantic chunking |
| Ingestion | `ingestion/embedder.py` | Embedding generation |
| Ingestion | `ingestion/hash_store.py` | Manifest and content hashes |
| Ingestion | `ingestion/weaviate_store.py` | Weaviate persistence |
| Ingestion | `ingestion/catalog.py` | Device and room catalog from source data |
| Ingestion | `ingestion/pipeline.py` | End-to-end ingestion orchestration |
| Graph enrichment | `extraction/extractor.py` | Controlled troubleshooting-concept extraction |
| Graph | `graph/graph_loader.py` | Base graph loading |
| Graph | `graph/device_replacement.py` | Transactional device replacement |
| Retrieval | `retrieval/vector_retriever.py` | Dense, BM25, and hybrid search |
| Retrieval | `retrieval/graph_retriever.py` | Parameterized Cypher retrieval |
| Retrieval | `retrieval/hybrid_merger.py` | Evidence merge and deduplication |
| Retrieval | `retrieval/retrieval_cache.py` | In-process LRU retrieval cache |
| Retrieval | `retrieval/reranker.py` | Optional cross-encoder reranking |
| Synthesis | `synthesis/groq_client.py` | Shared LLM provider gateway |
| Synthesis | `synthesis/output_guard.py` | Reasoning-block removal and JSON validation |
| Synthesis | `synthesis/sanitize.py` | Lightweight prompt-injection defense |
| Synthesis | `synthesis/prompts.py` | Evidence-aware prompt rendering |
| Synthesis | `synthesis/citation_assembler.py` | Citation validation and unsupported-span detection |
| Synthesis | `synthesis/confidence.py` | Retrieval, graph, and final confidence |
| APIs | `api/routes_chat.py` | Complete and streaming chat orchestration |
| APIs | `api/routes_devices.py` | Device read operations |
| APIs | `api/routes_incidents.py` | Incident operations |
| APIs | `api/routes_admin.py` | Administrative operations |

API route modules should remain thin. Business logic belongs in routing,
retrieval, graph, ingestion, and synthesis modules.

---

## 10. Observability Architecture

The application exposes:

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Liveness |
| `GET /readyz` | Neo4j and Weaviate readiness |
| `GET /metrics` | Prometheus/OpenMetrics-compatible metrics |
| `GET /users` | Seeded mock-user verification |

Observability includes:

- Request counts
- HTTP status counts
- Latency histogram
- In-flight request gauge
- Router decisions
- Provider selection and fallback events
- Ingestion events
- Request-level correlation through `X-Request-ID`

Recommended investigation sequence:

1. Locate the request ID.
2. Confirm the request reached the API.
3. Inspect entity matching and routing.
4. Inspect graph and vector retrieval.
5. Check provider selection and fallback.
6. Inspect citations and confidence.
7. Confirm final status and latency.

---

## 11. Security and Access Control

The capstone uses role-based permissions with seeded mock users.

Typical permissions include:

- Operators can ask questions and view data.
- Technicians can log incidents.
- Administrators can replace devices.

Current controls include:

- Parameterized Cypher
- Environment-based secrets
- CORS configuration
- Rate limiting
- Input sanitization
- Output validation
- Transactional writes
- Request tracing

Production deployment should add:

- Enterprise identity integration
- Secure secret management
- TLS
- Restricted database exposure
- Audit logging
- Network policies
- Backup encryption
- Environment-specific access controls

---

## 12. Deployment Architecture

### 12.1 Local and demo deployment

Docker Compose runs four services:

- `neo4j`
- `weaviate`
- `api`
- `web`

Default addresses:

| Service | Address |
|---|---|
| Frontend | `http://localhost:3000` |
| API | `http://localhost:8000` |
| API docs | `http://localhost:8000/docs` |
| Neo4j Browser | `http://localhost:7474` |
| Weaviate REST | `http://localhost:8080` |

### 12.2 Environment configuration

LLM configuration:

```env
XAI_API_KEY=your_xai_api_key
XAI_BASE_URL=your_xai_base_url
XAI_MODEL=grok-4.5

GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

Frontend configuration:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### 12.3 Container images

- The frontend uses a multi-stage Docker build.
- The builder compiles the Next.js application.
- The runtime image ships only the required standalone output.
- The backend currently uses a Python 3.11 slim image with required build
  dependencies for machine-learning packages.

### 12.4 Cloud migration path

Potential managed targets include:

| Local component | Possible managed target |
|---|---|
| Neo4j container | Neo4j Aura |
| Weaviate container | Weaviate Cloud |
| FastAPI container | Managed container platform |
| Next.js container | Managed frontend or container platform |
| Local secrets | Managed secret store |
| Local metrics | Central monitoring platform |

Most connection details are environment-driven, but production migration
still requires work in identity, networking, backups, security, and
observability.

---

## 13. Failure Modes and Resilience

| Failure | Intended behavior |
|---|---|
| Rules are uncertain | Invoke the LLM route fallback |
| Router fallback remains uncertain | Use `HYBRID` |
| Router LLM call fails | Log the failure and use `HYBRID` |
| xAI transient provider failure | Use Groq fallback |
| xAI configuration or authentication failure | Fail visibly; do not hide the error |
| Graph retrieval fails during HYBRID | Continue with vector evidence when possible |
| Vector retrieval fails during HYBRID | Continue with graph evidence when possible |
| Reranker is disabled or fails | Use deterministic merge order |
| Cache is disabled or misses | Perform normal retrieval |
| No evidence is found | Return a controlled insufficient-evidence response |
| Citation marker is invalid | Reject the dangling citation |
| Answer contains unsupported spans | Flag them and reduce confidence |
| Device replacement fails | Roll back the Neo4j transaction |
| Ingestion is interrupted | Mark pending and retry later |
| Streaming fails before first token | Attempt provider fallback |
| Streaming fails after tokens begin | End without restarting on another provider |

---

## 14. Key Design Decisions

### Explicit router instead of unrestricted LLM routing

Benefits:

- Lower cost
- Lower latency for common requests
- Deterministic behavior
- Testable route rules
- Explainable fired cues
- Safe HYBRID fallback

### Shared LLM gateway

All LLM-dependent features use one provider contract, so retries, fallback,
timeouts, logging, and error handling remain consistent.

### Separate graph and vector retrieval

The stores solve different information needs:

- Weaviate handles semantic document evidence.
- Neo4j handles relationships, lifecycle, and topology.

### Optional reranking based on measured value

The reranker remains available, but is disabled by default because its measured
recall improvement did not justify the additional latency for the current
deployment.

### Route-aware confidence

The final score reflects the type of evidence used and can penalize
disagreement between graph and retrieval signals.

### Citation-constrained answers

Citation validation prevents unsupported references from being accepted and
prevents citation-free answers from appearing highly reliable.

### Idempotent ingestion

Hash-gated ingestion supports incremental updates, avoids duplicate chunks,
and repairs interrupted processing.

### Transactional lifecycle operations

Device replacement preserves history and prevents partially applied graph
updates.

### Evaluation without an LLM judge

Grounding and correctness are measured through semantic similarity against
evidence and human-written references. This reduces cost and improves
repeatability, while introducing known limitations that must be interpreted
carefully.

---

## 15. Known Limitations

- The knowledge base covers a limited smart-office environment.
- The system is designed primarily for local and demonstration deployment.
- Complex diagrams, images, and tables may require additional extraction.
- Evaluation depth is constrained by provider cost and rate limits.
- Semantic-similarity evaluation may miss some factual errors.
- Enterprise authentication is not implemented.
- Managed backup and disaster recovery are not implemented.
- Mock-user headers are unsuitable for public deployment.
- Cross-building and cross-site reasoning are outside the current scope.

---

## 16. Future Architecture

### Broader facility coverage

- HVAC
- Electrical systems
- Access control
- Security systems
- Building management systems
- Additional networking and AV assets

### Production hardening

- Enterprise identity
- Managed secrets
- TLS
- Private networking
- Centralized logging and metrics
- Alerting
- Automated backups
- Restore testing
- CI/CD and environment promotion

### Advanced intelligence

- Cross-system root-cause analysis
- Predictive maintenance
- Incident trend detection
- Technician feedback loops
- Automated ticket creation
- Asset-management integration
- Multi-site knowledge graphs
- Multimodal manual processing

---

## 17. Architecture Validation

Run the following checks before merging architecture-affecting changes:

```bash
python -m compileall -q backend/app backend/tests

PYTHONPATH=backend pytest -q \
  backend/tests/test_output_guard.py \
  backend/tests/test_llm_provider_fallback.py

docker compose config --quiet
docker compose build api web
```

Run the full backend tests:

```bash
PYTHONPATH=backend pytest -q backend/tests
```

With the stack running and seeded, verify both chat modes:

```bash
curl -s http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -H "X-Mock-User-Id: u-ali" \
  -d '{"question":"The Samsung display has no signal. What should I check?"}'

curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -H "X-Mock-User-Id: u-ali" \
  -d '{"question":"The Samsung display has no signal. What should I check?"}'
```

Architecture changes should also be reflected consistently in:

- `README.md`
- `Setup.md`
- `Runbook.md`
- `Executive_Briefing.md`
- `.env.example`
- Docker health checks
- Evaluation documentation