# FacilityGraph AI — Executive Briefing

**Project type:** AI.SPIRE Capstone Project  
**Program partners:** LevelUp Economy × Istidama Consulting × Future Skills Fund  
**Team:** Amer Almajali, Afnan Tayem, Ibrahim Yasin, Mohammad Zalloum

---

## Executive Summary

FacilityGraph AI is an intelligent maintenance assistant designed for smart
office environments. It helps technicians, operators, and facility teams find
reliable answers to questions about devices, rooms, connections, manuals, and
historical incidents.

Instead of relying only on document search or only on structured data, the
system combines both:

- **Retrieval-Augmented Generation (RAG)** for searching manuals and incident
  records.
- **A Knowledge Graph** for understanding devices, rooms, relationships,
  topology, and maintenance history.

The result is a traceable troubleshooting assistant that retrieves relevant
evidence, selects the appropriate reasoning path, generates a response, and
returns citations with a user-facing confidence score.

---

## Business Problem

Smart offices contain interconnected networking, audiovisual, control, and
display equipment. When a failure occurs, the required information is often
spread across:

- Long technical manuals
- Device inventories
- Room and connection records
- Previous incident reports
- Individual staff experience

This creates several operational challenges:

- Troubleshooting takes longer than necessary.
- Knowledge is difficult to transfer between team members.
- Previous fixes are not always reused.
- Device relationships are difficult to understand from documents alone.
- Staff may receive confident-sounding answers without knowing whether they
  are supported by evidence.

FacilityGraph AI addresses these issues by bringing structured facility data,
technical documents, and incident history into one searchable and explainable
system.

---

## Proposed Solution

A user submits a natural-language question, such as:

- *Why does the meeting-room display show no signal?*
- *What is connected to the reception access point?*
- *Which incidents have affected this device?*
- *What was installed in this room last year?*

The system then:

1. Identifies relevant devices, rooms, and entities.
2. Classifies the question into the appropriate retrieval route.
3. Retrieves evidence from Neo4j, Weaviate, or both.
4. Uses the configured LLM provider to synthesize an answer.
5. Attaches citations to supporting evidence.
6. Calculates a confidence score based on retrieval quality, graph evidence,
   citation coverage, and route-specific signals.

This approach provides a more useful answer than plain document search while
remaining more transparent than a conventional black-box chatbot.

---

## Core AI Capability

FacilityGraph AI uses a hybrid retrieval architecture with three explicit
routes:

| Route | Primary use |
|---|---|
| `GRAPH_ONLY` | Device relationships, room topology, installation history, and structured facts |
| `RAG_ONLY` | Technical manuals, troubleshooting instructions, and unstructured records |
| `HYBRID` | Questions requiring both structured relationships and document evidence |

When routing confidence is insufficient, the system defaults to `HYBRID`.
This prioritizes evidence coverage over minimal latency and reduces the risk of
missing relevant information.

---

## Trust, Safety, and Explainability

Trustworthiness was treated as a core engineering requirement.

### Evidence-backed responses

The system is designed to connect generated factual content to retrieved
evidence, including:

- Vendor manuals
- Historical incidents
- Knowledge graph facts
- Device and room relationships

### Citation-aware confidence

Confidence is not based only on the language model’s output. It is calculated
from system signals such as:

- Retrieval strength
- Exact entity matching
- Graph path quality
- Availability of supporting facts
- Citation coverage
- Unsupported answer spans

Answers without sufficient citation support cannot receive a high confidence
score.

### Explicit uncertainty

When the evidence is weak, incomplete, or unavailable, the system is designed
to communicate uncertainty instead of presenting unsupported conclusions as
facts.

### Preserved operational history

Device replacement is transactional and history-preserving. Retired devices,
incident records, installation dates, and replacement relationships remain
queryable rather than being silently deleted.

### Operational traceability

The platform exposes health, readiness, and monitoring endpoints. Requests
can be traced through structured logs using a request identifier, supporting
debugging, auditing, and demonstration readiness.

---

## LLM Provider Strategy

FacilityGraph AI uses:

- **Primary provider:** xAI with `grok-4.5`
- **Fallback provider:** Groq with
  `meta-llama/llama-4-scout-17b-16e-instruct`

Groq is used only for qualifying transient xAI failures, such as:

- HTTP `429`
- Request timeout
- Connection failure
- HTTP `5xx`

Authentication and configuration errors do not trigger fallback. This avoids
masking invalid credentials or incorrect deployment settings.

---

## Current Scope

The current capstone implementation includes:

- 10 smart-office devices
- 4 rooms
- Cisco, Crestron, and Samsung equipment
- 24 documented physical and logical relationships
- 16 historical incident records
- 10 vendor manuals
- A 50-question held-out evaluation dataset
- Coverage across `GRAPH_ONLY`, `RAG_ONLY`, and `HYBRID` routes

The current scope is intentionally limited to support reliable evaluation,
clear demonstrations, and controlled iteration.

---

## Evaluation Approach

The system is evaluated using a held-out dataset that includes:

- Questions for all three routing modes
- Coverage across the available devices
- Questions answerable from manuals
- Questions answerable from graph relationships
- Questions requiring combined evidence
- Out-of-scope questions that test whether the system avoids guessing

Evaluation dimensions include:

- Answer correctness
- Routing accuracy
- Citation validity
- Confidence calibration
- Latency
- Error patterns by route and device
- Comparison against a plain-RAG baseline

The team also documents failure cases and records a next-iteration hypothesis
for each evaluation cycle. This turns errors into structured input for system
improvement.

---

## Key Operational Capabilities

FacilityGraph AI supports more than question answering.

### Device replacement

Authorized users can replace a device through a transactional workflow that:

- Retires the original device
- Creates the replacement device
- Repoints structural relationships
- Preserves historical information
- Records the replacement relationship
- Optionally ingests the new manual

### Incident logging

Technicians and administrators can add incidents that are immediately:

- Written to the knowledge graph
- Indexed in the vector database
- Available for retrieval
- Eligible for citation in future answers

### Monitoring and diagnostics

The application provides:

- Liveness checks
- Readiness checks
- Prometheus/OpenMetrics-compatible metrics
- Request IDs for tracing
- Structured routing and provider logs
- Rate limiting for shared and demo environments

---

## Current Limitations

The current implementation has several known constraints:

- The deployment is designed primarily for local and demonstration use.
- The knowledge base covers one limited smart-office environment.
- Manuals containing diagrams, tables, and scanned pages may require
  additional preprocessing.
- Evaluation depth is constrained by external API cost and rate limits.
- The platform does not yet provide a complete production backup and restore
  workflow.
- Electrical, HVAC, security, and wider building-management systems are not
  yet fully represented.
- The current mock-user mechanism is suitable for development and demos, not
  production identity management.

These limitations define the next engineering priorities rather than reducing
the value of the current proof of concept.

---

## Roadmap

Future development can extend FacilityGraph AI in several stages.

### Stage 1 — Broader facility coverage

- Add more rooms, devices, and incident histories.
- Expand into HVAC, electrical, security, access control, and building
  management systems.
- Add more vendor manuals and maintenance procedures.

### Stage 2 — Production readiness

- Replace mock users with enterprise authentication.
- Add managed secrets and environment-specific configuration.
- Implement backup, restore, and retention policies.
- Harden network access and service permissions.
- Add centralized monitoring and alerting.

### Stage 3 — Advanced intelligence

- Cross-system root-cause analysis
- Predictive maintenance
- Incident trend detection
- Automated maintenance recommendations
- Technician feedback loops
- Multi-site knowledge graphs
- Integration with ticketing and asset-management platforms

---

## Expected Value

FacilityGraph AI demonstrates how a hybrid AI architecture can improve smart
office maintenance by:

- Reducing time spent searching manuals
- Making historical incidents reusable
- Preserving technical knowledge across teams
- Improving visibility into device relationships
- Producing evidence-backed answers
- Making uncertainty visible
- Supporting faster and more consistent troubleshooting
- Providing an extensible foundation for larger facility-management use cases

---

## Bottom Line

FacilityGraph AI is not simply a chatbot over documents. It is an
evidence-driven maintenance assistant that combines semantic retrieval,
structured facility knowledge, explicit routing, citations, confidence
scoring, operational controls, and failure-aware evaluation.

The capstone shows that a hybrid RAG and Knowledge Graph architecture can
deliver answers that are more relevant, more traceable, and more operationally
useful than a conventional retrieval-only assistant.