# FacilityGraph AI — System Architecture

**System:** Hybrid RAG + Knowledge Graph Assistant for Smart Office Maintenance  
**Project:** AI.SPIRE Capstone — Group 1, Team 1  
**Repository:** `https://github.com/capstone-group1-team1/main-repo.git`  
**Status:** Capstone implementation for local and demonstration environments  

---

## 1. Executive Architecture Summary

FacilityGraph AI is an evidence-driven maintenance assistant that combines
unstructured document retrieval with structured facility knowledge.

The architecture uses two complementary knowledge systems:

- **Weaviate** stores semantically searchable content from device manuals and
  historical incident records.
- **Neo4j** stores rooms, devices, topology, relationships, lifecycle data,
  incidents, and extracted troubleshooting concepts.

An explicit query router selects one of three retrieval strategies:

| Route | Primary purpose |
|---|---|
| `GRAPH_ONLY` | Structured relationships, topology, room contents, lifecycle, and incident history |
| `RAG_ONLY` | Manual instructions, troubleshooting procedures, and document-based evidence |
| `HYBRID` | Questions requiring both structured and unstructured evidence, or cases where routing is uncertain |

Retrieved evidence is passed to the synthesis layer. xAI generates the answer
by default, while Groq is used only for qualifying transient xAI failures.
The response is then processed by the citation and confidence layers before it
is returned to the user.

The architecture is designed around five principles:

1. **Evidence before generation**
2. **Explicit and testable routing**
3. **Traceable citations**
4. **Visible uncertainty**
5. **Graceful degradation when a dependency fails**

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
│  Auth · Permissions · APIs   │
│  Rate Limits · Observability │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│         Query Router         │
│                              │
│ Entity matching → Rules →    │
│ LLM fallback → HYBRID default│
└───────┬──────────┬───────────┘
        │          │
        │          │
        ▼          ▼
┌──────────────┐  ┌──────────────┐
│    Neo4j     │  │   Weaviate   │
│ Graph facts  │  │ Manual and   │
│ and topology │  │ incident data│
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
│ Citation validation          │
│ Unsupported-span detection   │
│ Route-aware confidence       │
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│         ChatResponse         │
│ Answer · Citations · Score   │
└──────────────────────────────┘
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
                         Sanitized, traceable response
```

A retrieval cache may be keyed by the normalized question and resolved route.
This reduces repeated graph and vector searches for identical requests.

---

## 4. Query Routing Architecture

### 4.1 Entity matching

`entity_matcher.py` performs deterministic lookup against device names,
models, aliases, and room names derived from the project catalog.

Its output supports both:

- Route selection
- Graph-confidence calculation

Entity matching is performed without an LLM, making it fast, explainable, and
repeatable.

### 4.2 Rule-based classification

`rules.py` scores graph, RAG, and hybrid cue groups.

Examples of likely route signals include:

- Relationship and topology language → graph
- Troubleshooting and instruction language → RAG
- Questions combining a device relationship with a symptom → hybrid

The rule classifier returns:

- Proposed route
- Score
- Margin between the top and second-best route
- Fired cues

The live margin threshold is supplied through configuration. A compatibility
default of `0.25` may exist in the router module.

### 4.3 LLM fallback

When deterministic rules are not sufficiently decisive,
`llm_fallback.py` classifies the route.

The fallback result is accepted only when its confidence meets the configured
threshold. A compatibility default of `0.60` may exist in the router module.

Routing through the provider layer follows the same provider strategy used by
the application:

- xAI is primary.
- Groq is used only for qualifying transient xAI failures.

### 4.4 Safe default

When both rules and LLM fallback remain uncertain, the router selects
`HYBRID`.

This default favors evidence coverage over minimum latency. It may increase
retrieval and token cost, but it reduces the chance that the system excludes
a necessary evidence source.

### 4.5 Router observability

Each routing decision is logged with:

- Question or request context
- Selected route
- Router confidence
- Decision mechanism
- Matched entities
- Fired cues where available

Router confidence is an internal diagnostic signal and is not the same as the
final user-facing confidence score.

---

## 5. Retrieval Architecture

### 5.1 Vector retrieval

`vector_retriever.py` retrieves semantically relevant evidence from Weaviate.

The retrieval process may include:

- Query embedding using `BAAI/bge-large-en-v1.5`
- Dense vector similarity
- BM25 keyword matching
- Hybrid fusion controlled by `alpha`
- Device filtering when an entity is resolved
- Result limits and evidence-budget controls

The vector store contains:

- Manual chunks
- Historical incident records
- Citation metadata
- Device and document identifiers

### 5.2 Graph retrieval

`graph_retriever.py` runs named and parameterized Cypher queries against
Neo4j.

Graph retrieval is used for facts such as:

- Which devices are located in a room
- Which devices are connected
- Which system controls or uses another
- Installation and retirement history
- Device replacement lineage
- Associated incidents
- Extracted symptoms, procedures, components, and error codes

Parameterized queries reduce injection risk and make retrieval behavior easier
to test.

### 5.3 Hybrid merge

For `HYBRID` requests, `hybrid_merger.py` combines graph facts and document
chunks into one candidate evidence set.

Typical responsibilities include:

- Preserving source identity
- Removing duplicate evidence
- Prioritizing structured facts where appropriate
- Respecting the maximum evidence budget

### 5.4 Reranking

`reranker.py` uses `BAAI/bge-reranker-base` to rescore candidate evidence
based on query-passage relevance.

The reranker:

1. Receives the merged candidate pool.
2. Scores each candidate against the question.
3. Sorts by relevance.
4. Trims the final evidence set.

When reranking is disabled or unavailable, the system falls back to the merge
order instead of failing the request.

### 5.5 Graceful degradation

A failure in one retrieval branch should not automatically fail a hybrid
request.

Examples:

- Neo4j unavailable → continue with vector evidence when possible.
- Weaviate unavailable → continue with graph evidence when possible.
- Reranker unavailable → use deterministic merge order.

The final confidence score should reflect reduced evidence quality or missing
branches.

---

## 6. LLM Provider and Synthesis Architecture

### 6.1 Provider strategy

| Priority | Provider | Model | Usage |
|---|---|---|---|
| Primary | xAI | `grok-4.5` | Normal synthesis and applicable LLM operations |
| Fallback | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` | Qualifying transient xAI failures |

Groq fallback is triggered only for transient provider failures:

- HTTP `429`
- Timeout
- Connection failure
- HTTP `5xx`

The following do not trigger fallback:

- Invalid API key
- Invalid base URL
- Unsupported model configuration
- Authentication or authorization failure
- Other configuration errors

This distinction prevents deployment errors from being silently hidden.

### 6.2 Prompt construction

`prompts.py` renders retrieved evidence into numbered source blocks.

Each block includes enough identity metadata to support citation assembly,
such as:

- Source type
- Document or incident identity
- Page or chunk reference when available
- Device or room association
- Evidence text

The model is instructed to:

- Use only supplied evidence
- Attach an `[n]` marker to supported factual claims
- Avoid unsupported speculation
- State when the available sources do not cover the question

When no usable evidence exists, the application should return a controlled
insufficient-evidence response instead of asking the LLM to guess.

### 6.3 Output protection

The synthesis pipeline should apply output validation and sanitization before
returning a response.

Responsibilities may include:

- Removing invalid or unsafe output fragments
- Ensuring citation markers map to real evidence
- Preventing dangling references
- Preserving the public API schema
- Handling provider failures consistently

---

## 7. Citation and Confidence Architecture

### 7.1 Citation chain

Traceability is maintained across the complete pipeline:

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

- Parsing citation markers used by the model
- Rejecting markers that do not map to evidence
- Deduplicating citations
- Renumbering citations compactly
- Detecting factual-looking sentences without support
- Returning unsupported spans for confidence adjustment and UI visibility

### 7.2 Confidence signals

`confidence.py` calculates three related outputs:

| Signal | Purpose |
|---|---|
| Retrieval confidence | Measures the strength and separation of vector retrieval results |
| Graph confidence | Measures entity match quality, graph path quality, and available graph facts |
| Final confidence | Produces the route-aware user-facing score after citation and disagreement adjustments |

#### Retrieval confidence

A strong top result with a meaningful score gap is more decisive than several
similar, mediocre results.

#### Graph confidence

Graph confidence may consider:

- Exact entity match
- Number of facts
- Path length
- Path-length decay such as `0.85^(hops−1)`

#### Final confidence

The final score depends on the resolved route:

- `GRAPH_ONLY` emphasizes graph confidence.
- `RAG_ONLY` emphasizes retrieval confidence.
- `HYBRID` combines both and may penalize disagreement.

Post-processing rules make uncertainty structural:

- Zero citations cap the score at a low level, such as `0.25`.
- Unsupported spans reduce the score proportionally.
- Missing retrieval branches can reduce the score.
- Confidence is clamped to the valid range.

UI thresholds:

| Level | Threshold |
|---|---:|
| Low | `< 0.40` |
| Medium | `0.40–0.75` |
| High | `> 0.75` |

The final confidence score should be interpreted as an evidence-quality and
support signal, not as a mathematical probability that the answer is correct.

---

## 8. Data Architecture

### 8.1 Source data

The project uses data under `data/`:

| Source | Purpose |
|---|---|
| `asset_inventory.csv` | Devices, rooms, installation details, status, firmware, and warranty data |
| `relationships.csv` | Physical and logical relationships |
| `incidents.csv` | Historical incidents |
| `manuals_pdf/` | Official vendor manuals |

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

1. Retire the old device.
2. Create the replacement device.
3. Repoint current structural relationships.
4. Create `(old)-[:REPLACED_BY]->(new)`.
5. Preserve prior incidents and lifecycle metadata.

This supports historical questions across device generations.

### 8.4 Weaviate model

The vector database uses a collection such as `SmartOfficeChunk`.

Each object represents a manual chunk or incident and includes:

- Text content
- Source type
- Source identity
- Device association
- Document metadata
- Citation metadata
- App-supplied vector

The collection uses application-generated embeddings rather than an internal
Weaviate vectorizer.

### 8.5 Idempotent ingestion

The ingestion pipeline uses content hashing and a persistent manifest.

Expected behavior:

| Input state | Ingestion result |
|---|---|
| New content | Insert and mark complete |
| Unchanged content | Skip |
| Changed content | Replace the source-specific chunks |
| Interrupted processing | Leave pending and retry on the next run |

This prevents duplicate chunks and supports safe re-ingestion.

---

## 9. Module Map

| Area | Main files | Responsibility |
|---|---|---|
| Core configuration | `core/config.py` | Environment-backed settings and shared client factories |
| Logging | `core/logging.py` | Structured application logs and router-decision events |
| Observability | `core/observability.py` | Request IDs, health/readiness behavior, and metrics |
| Rate limiting | `core/rate_limit.py` | Shared request limits by endpoint group |
| API contracts | `models/schemas.py` | Public response models and internal evidence types |
| Authentication | `auth/mock_users.py` | Seeded development and demo users |
| Authorization | `auth/permissions.py` | Role-to-action permission checks |
| Routing | `router/entity_matcher.py` | Device, room, model, and alias matching |
| Routing | `router/rules.py` | Deterministic cue-based route scoring |
| Routing | `router/llm_fallback.py` | Route classification when rules are uncertain |
| Routing | `router/query_router.py` | Routing orchestration and safe HYBRID default |
| Ingestion | `ingestion/pdf_reader.py` | PDF text extraction |
| Ingestion | `ingestion/chunker.py` | Semantic document chunking |
| Ingestion | `ingestion/embedder.py` | Embedding generation |
| Ingestion | `ingestion/hash_store.py` | Ingestion manifest and content hashes |
| Ingestion | `ingestion/weaviate_store.py` | Weaviate persistence |
| Ingestion | `ingestion/catalog.py` | Device and room catalog derived from source data |
| Ingestion | `ingestion/pipeline.py` | End-to-end ingestion orchestration |
| Graph enrichment | `extraction/extractor.py` | Controlled extraction of troubleshooting concepts |
| Graph | `graph/graph_loader.py` | Base graph loading |
| Graph | `graph/device_replacement.py` | Transactional device replacement |
| Retrieval | `retrieval/vector_retriever.py` | Dense, BM25, and hybrid search |
| Retrieval | `retrieval/graph_retriever.py` | Parameterized Cypher retrieval |
| Retrieval | `retrieval/hybrid_merger.py` | Evidence merge and deduplication |
| Retrieval | `retrieval/reranker.py` | Cross-encoder relevance reranking |
| Synthesis | `synthesis/groq_client.py` | LLM provider gateway and provider-fallback behavior |
| Synthesis | `synthesis/prompts.py` | Evidence-aware prompt rendering |
| Synthesis | `synthesis/citation_assembler.py` | Citation validation and unsupported-span detection |
| Synthesis | `synthesis/confidence.py` | Retrieval, graph, and final confidence |
| Synthesis | `synthesis/sanitize.py` | Output sanitization and protection |
| APIs | `api/routes_chat.py` | Chat orchestration endpoint |
| APIs | `api/routes_devices.py` | Device read operations |
| APIs | `api/routes_incidents.py` | Incident operations |
| APIs | `api/routes_admin.py` | Administrative operations |

API route modules should remain thin. Business logic belongs in domain,
retrieval, graph, ingestion, and synthesis modules rather than HTTP handlers.

---

## 10. Observability Architecture

The application exposes:

| Endpoint | Purpose |
|---|---|
| `GET /healthz` | Liveness |
| `GET /readyz` | Dependency readiness |
| `GET /metrics` | Prometheus/OpenMetrics-compatible metrics |
| `GET /users` | Verification of seeded mock users |

Observability includes:

- Request counts
- HTTP status counts
- Latency histogram
- In-flight request gauge
- Structured router decisions
- Provider selection and fallback events
- Ingestion events
- Request-level correlation through `X-Request-ID`

Recommended investigation path:

1. Locate the request ID.
2. Confirm request start.
3. Inspect route selection.
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
- Administrators can perform device replacement.

Security controls include:

- Parameterized Cypher
- Environment-based secrets
- CORS configuration
- Rate limiting
- Output validation
- Transactional writes
- Request tracing

Production deployment should replace mock authentication and add:

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

Docker Compose runs:

- Neo4j
- Weaviate
- FastAPI API
- Next.js frontend

Default local addresses:

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

### 12.3 Cloud migration path

A production-style deployment can replace local services with managed
alternatives:

| Local component | Possible managed target |
|---|---|
| Neo4j container | Neo4j Aura |
| Weaviate container | Weaviate Cloud |
| FastAPI container | Managed container platform |
| Next.js container | Managed frontend or container platform |
| Local secrets | Managed secret store |
| Local metrics | Central monitoring platform |

The application is designed so connection details and provider configuration
are supplied through environment settings. Migration should therefore require
limited application-code change, although production hardening, identity,
networking, backup, and observability work would still be required.

---

## 13. Failure Modes and Resilience

| Failure | Intended behavior |
|---|---|
| Rules are uncertain | Invoke LLM route fallback |
| Router fallback remains uncertain | Use `HYBRID` |
| xAI transient provider failure | Use Groq fallback |
| xAI configuration or authentication failure | Fail visibly; do not hide the error through fallback |
| Graph retrieval fails during HYBRID | Continue with vector evidence when possible |
| Vector retrieval fails during HYBRID | Continue with graph evidence when possible |
| Reranker fails | Use deterministic merged order |
| No evidence is found | Return a controlled insufficient-evidence response |
| Citation marker is invalid | Drop or reject the dangling citation |
| Answer contains unsupported spans | Flag them and reduce final confidence |
| Device replacement fails | Roll back the full Neo4j transaction |
| Ingestion is interrupted | Mark pending and retry during the next run |

---

## 14. Key Design Decisions

### Explicit router instead of unrestricted LLM routing

Benefits:

- Deterministic behavior for common requests
- Lower cost
- Lower latency
- Testability
- Explainable fired cues
- Safe `HYBRID` fallback

### Separate graph and vector retrieval

The stores solve different information needs:

- Weaviate answers semantic document questions.
- Neo4j answers relationship and lifecycle questions.

Keeping them separate preserves the strengths of each representation.

### Route-aware confidence

A single generic score would hide whether confidence comes from documents,
graph structure, or both. Route-aware calculation makes the score more
meaningful and allows disagreement penalties for hybrid requests.

### Citation-constrained answers

The citation pipeline prevents fluent but unsupported responses from appearing
highly reliable.

### Idempotent ingestion

Hash-gated ingestion reduces duplicate data, supports incremental updates,
and makes repeated setup and demonstrations safer.

### Transactional lifecycle operations

Device replacement is treated as a domain transaction, preserving history and
preventing partially applied graph changes.

---

## 15. Known Limitations

- The knowledge base covers a limited smart-office environment.
- The system is designed primarily for local and demonstration deployment.
- Complex diagrams, images, and tables in manuals may require additional
  extraction or multimodal processing.
- Evaluation depth is constrained by external provider cost and rate limits.
- The project does not yet include enterprise authentication.
- Managed backup and disaster recovery are not yet implemented.
- The mock user header is unsuitable for untrusted public deployment.
- Cross-building and cross-site reasoning are outside the current scope.

---

## 16. Future Architecture

Potential next stages include:

### Broader domain coverage

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
- Centralized logs and metrics
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

Additional recommended checks:

```bash
cd backend
pytest tests -q
```

With the full stack running and seeded:

```bash
python scripts/smoke_test.py
```

Architecture changes should also be reflected consistently in:

- `README.md`
- `Setup.md`
- `Runbook.md`
- `Executive_Briefing.md`
- Environment templates
- Docker health checks
- Evaluation documentation