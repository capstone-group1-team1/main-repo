# GridSense Office — Executive Briefing

**Project type:** AI.SPIRE Capstone Project  
**Program partners:** LevelUp Economy × Istidama Consulting × Future Skills Fund  
**Team:** Amer Almajali, Afnan Tayem, Ibrahim Yasin, Mohammad Zalloum

---

## Executive Summary

GridSense Office is an AI-powered maintenance assistant for smart office
environments. It helps technicians, operators, and facility teams answer
questions about devices, rooms, connections, technical manuals, and historical
incidents.

The system combines two complementary sources of knowledge:

- **Retrieval-Augmented Generation (RAG)** for searching technical manuals and
  incident records.
- **A Knowledge Graph** for understanding devices, rooms, relationships,
  topology, installation history, and replacement history.

By combining both approaches behind an explicit query router, GridSense Office
can provide answers that are more relevant, traceable, and operationally useful
than a conventional document-only chatbot.

---

## The Business Problem

Smart offices contain interconnected networking, audiovisual, control, and
display equipment. When an issue occurs, the required information is often
distributed across:

- Long technical manuals
- Device inventories
- Room and connection records
- Historical incident reports
- Individual staff experience

This creates several operational challenges:

- Troubleshooting takes longer than necessary.
- Previous solutions are difficult to find and reuse.
- Technical knowledge may remain with individual team members.
- Device relationships are difficult to understand from documents alone.
- Users may receive confident-sounding answers without clear evidence.

GridSense Office brings these information sources into one searchable and
explainable system.

---

## How the Solution Works

A user submits a natural-language question, such as:

- *Why does the meeting-room display show no signal?*
- *What is connected to the reception access point?*
- *Which incidents have affected this device?*
- *What was installed in this room last year?*

The system then:

1. Identifies relevant devices, rooms, and entities.
2. Classifies the question into the appropriate retrieval route.
3. Retrieves evidence from Neo4j, Weaviate, or both.
4. Uses the primary AI provider to generate an evidence-based response.
5. Falls back to a secondary provider when a qualifying transient failure
   occurs.
6. Validates citations and calculates a user-facing confidence score.
7. Returns the answer either as a complete response or as a streamed response.

---

## Core AI Capability

GridSense Office uses three explicit retrieval routes:

| Route | Primary purpose |
|---|---|
| `GRAPH_ONLY` | Device relationships, room topology, lifecycle information, and structured facts |
| `RAG_ONLY` | Technical manuals, troubleshooting instructions, and unstructured incident evidence |
| `HYBRID` | Questions requiring both structured and document-based evidence |

When the router is uncertain, the system defaults to `HYBRID`. This may use
more resources, but it reduces the risk of excluding a relevant evidence
source.

---

## What Makes the System Trustworthy

Trustworthiness was treated as a core engineering requirement.

### Evidence-backed responses

The system is designed to connect factual statements to supporting evidence,
including:

- Vendor manuals
- Historical incidents
- Knowledge graph facts
- Device and room relationships

### Citation validation

The model uses numbered citation markers that are checked against the evidence
actually supplied to it. Invalid or unsupported references are not silently
accepted.

### Confidence scoring

The user-facing confidence score considers signals such as:

- Retrieval strength
- Exact entity matching
- Graph path quality
- Availability of supporting facts
- Citation coverage
- Unsupported answer spans

A citation-free response cannot appear highly confident.

### Explicit uncertainty

When the available evidence is weak or incomplete, the system is designed to
communicate uncertainty rather than present unsupported conclusions as facts.

### Preserved operational history

When a device is replaced, the previous device is not silently deleted.
Installation dates, retirement dates, incidents, room history, and replacement
relationships remain queryable.

### Graceful provider fallback

GridSense Office uses:

- **Primary provider:** xAI with `grok-4.5`
- **Fallback provider:** Groq with
  `meta-llama/llama-4-scout-17b-16e-instruct`

Groq is used only for qualifying transient xAI failures such as HTTP `429`,
timeouts, connection failures, or HTTP `5xx` responses. Authentication and
configuration errors do not trigger fallback.

### Operational visibility

The system exposes:

- Liveness and readiness checks
- Prometheus/OpenMetrics-compatible metrics
- Request latency and error information
- Request IDs for end-to-end tracing
- Structured routing and provider logs

---

## Current Scope

The current capstone implementation includes:

- 10 smart-office devices
- 4 rooms
- Cisco, Crestron, and Samsung equipment
- 24 documented physical and logical relationships
- 16 historical incident records
- 10 official vendor manuals
- A 50-question held-out evaluation dataset
- Coverage across `GRAPH_ONLY`, `RAG_ONLY`, and `HYBRID`
- Deliberately out-of-scope questions to test whether the system avoids
  unsupported guessing

The scope is intentionally controlled so the team can evaluate the system
reliably and demonstrate the complete architecture clearly.

---

## Evaluation Approach

The evaluation framework measures the system at several levels.

### Answer quality

Answers are assessed for:

- Grounding in the retrieved evidence
- Semantic similarity to expected expert answers
- Correct handling of out-of-scope questions

### Routing quality

The framework measures whether each question is assigned to the correct route:

- `GRAPH_ONLY`
- `RAG_ONLY`
- `HYBRID`

### Retrieval quality

The team evaluates whether the correct evidence is retrieved and how highly it
is ranked using metrics such as:

- Recall@5
- Mean Reciprocal Rank

### Trust and operations

Additional evaluation areas include:

- Citation validity
- Confidence calibration
- p95 latency
- Error analysis by route and device
- Baseline and ablation comparisons

The system is compared against simpler retrieval approaches to measure the
value added by explicit routing, graph retrieval, citations, and confidence
controls.

Evaluation reports are generated in JSON and Markdown, and the team maintains
documented failure cases with hypotheses for future improvement.

---

## Key Operational Capabilities

GridSense Office supports more than question answering.

### Device replacement

Authorized administrators can replace a device through a transactional
workflow that:

- Retires the original device
- Creates or activates the replacement
- Repoints live topology relationships
- Preserves historical room placement
- Records the `REPLACED_BY` relationship
- Keeps historical incidents queryable
- Optionally ingests the replacement manual

### Incident logging

Technicians and administrators can add incidents that are:

- Stored in Neo4j
- Indexed in Weaviate when available
- Searchable in future requests
- Eligible for citation in later answers

If vector indexing temporarily fails, the incident remains preserved in the
knowledge graph and can be indexed later.

### Streaming responses

The platform supports both:

- `POST /chat` for complete responses
- `POST /chat/stream` for token-by-token delivery

This improves perceived responsiveness during demonstrations and interactive
use.

---

## Expected Value

GridSense Office demonstrates how a hybrid AI architecture can improve smart
office maintenance by:

- Reducing time spent searching manuals
- Making historical incidents reusable
- Preserving technical knowledge across teams
- Improving visibility into device relationships
- Supporting faster and more consistent troubleshooting
- Producing evidence-backed answers
- Making uncertainty visible
- Providing a scalable foundation for broader facility-management use cases

---

## Known Limitations

The current implementation has several constraints:

- The deployment is designed primarily for local and demonstration use.
- The knowledge base covers one limited smart-office environment.
- Complex diagrams, images, tables, and scanned manuals may require additional
  preprocessing.
- Evaluation depth is constrained by external provider cost and rate limits.
- Enterprise authentication is not yet implemented.
- A complete managed backup and restore workflow is not yet available.
- Electrical, HVAC, security, and wider building-management systems are not
  yet fully represented.

These limitations define the next engineering priorities rather than reducing
the value of the current proof of concept.

---

## Roadmap

### Stage 1 — Broader facility coverage

- Add more rooms, devices, manuals, and incident history.
- Expand into HVAC, electrical, security, access control, and building
  management systems.
- Improve extraction from diagrams, tables, and scanned documents.

### Stage 2 — Production readiness

- Replace mock users with enterprise authentication.
- Add managed secrets and environment-specific configuration.
- Implement backup, restore, and retention policies.
- Add centralized monitoring, alerts, and audit logging.
- Harden service permissions and network access.

### Stage 3 — Advanced intelligence

- Cross-system root-cause analysis
- Predictive maintenance
- Incident trend detection
- Technician feedback loops
- Automated ticket creation
- Asset-management integration
- Multi-site knowledge graphs

---

## Bottom Line

GridSense Office is not simply a chatbot over technical documents. It is an
evidence-driven maintenance assistant that combines semantic retrieval,
structured facility knowledge, explicit routing, provider resilience,
validated citations, confidence scoring, streaming responses, and operational
monitoring.

The capstone demonstrates that a hybrid RAG and Knowledge Graph architecture
can deliver answers that are more relevant, more traceable, and more useful
for real maintenance workflows than a conventional retrieval-only assistant.