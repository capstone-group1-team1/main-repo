"""
extractor.py — LLM-powered graph enrichment (Layer 2).

For each manual chunk, one shared LLM gateway call extracts troubleshooting knowledge as
STRUCTURED JSON (never Cypher): symptoms, procedures, error codes, and
relations between them from a CLOSED vocabulary.  Candidates are then
normalized, validated, and written to Neo4j through FIXED, parameterized
MERGE templates only.

Why no LLM-generated Cypher: generated Cypher is an injection surface,
cannot be semantically validated before execution, invents schema, and
breaks idempotency.  Structured objects keep the LLM doing reading
comprehension while deterministic code owns database semantics.

Every enriched node/edge carries source_chunk_id provenance, so even
graph-derived answers remain traceable to a manual page.
Enrichment is best-effort per chunk: a failed chunk is logged and skipped;
the vector side of ingestion is never affected.
"""

from __future__ import annotations

from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_neo4j_driver, get_settings
from app.core.logging import get_logger
from app.synthesis.groq_client import generate_json

log = get_logger(__name__)

# Closed vocabularies — the validator rejects anything outside these.
ENTITY_TYPES = {"Symptom", "Procedure", "ErrorCode", "Component"}
RELATIONS = {
    "RESOLVED_BY": ("Symptom", "Procedure"),
    "INDICATES": ("ErrorCode", "Symptom"),
    "HAS_COMPONENT": ("Device", "Component"),
    "REQUIRES": ("Procedure", "Component"),
}

_PROMPT = """You extract troubleshooting knowledge from a device manual chunk.

Return ONLY a JSON object with this exact shape (no prose):
{{
  "entities": [{{"name": "...", "type": "Symptom|Procedure|ErrorCode|Component"}}],
  "relations": [{{"head": "...", "relation": "RESOLVED_BY|INDICATES|HAS_COMPONENT|REQUIRES",
                  "tail": "...", "evidence": "exact short quote from the chunk"}}]
}}

Rules:
- Entity names: short noun phrases (max 8 words), lowercase.
- Only extract what the chunk actually states. "evidence" MUST be a
  verbatim substring of the chunk.
- For HAS_COMPONENT the head must be exactly: {device_name}
- Return empty lists if the chunk contains no troubleshooting knowledge.

Device: {device_name}
Chunk:
\"\"\"{chunk}\"\"\""""


def _describe_llm_error(exc: Exception) -> str:
    """tenacity's RetryError.__str__() only says 'raised ...Error', hiding
    the actual server-side reason behind a useless repr. Unwrap to the real
    underlying exception so a bad request is actually diagnosable from the
    log instead of just 'skipped: RetryError[...]'."""
    inner = exc
    last_attempt = getattr(exc, "last_attempt", None)
    if last_attempt is not None:
        try:
            inner = last_attempt.exception()
        except Exception:
            pass
    return str(inner)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _call_llm(chunk_text: str, device_name: str) -> dict:
    return generate_json(
        system="",
        user=_PROMPT.format(
            device_name=device_name,
            chunk=chunk_text[: get_settings().extraction_char_limit],
        ),
        temperature=0.0,
    )


def _validate(raw: dict, chunk_text: str, device_name: str) -> list[dict]:
    """Candidates -> validated triples.  Rejections are logged, never fatal."""
    entities = {}
    for e in raw.get("entities", []):
        name = str(e.get("name", "")).strip().lower()[:80]
        etype = str(e.get("type", "")).strip()
        if name and etype in ENTITY_TYPES:
            entities[name] = etype

    triples: list[dict] = []
    for r in raw.get("relations", []):
        head = str(r.get("head", "")).strip().lower()[:80]
        rel = str(r.get("relation", "")).strip()
        tail = str(r.get("tail", "")).strip().lower()[:80]
        evidence = str(r.get("evidence", ""))

        if rel not in RELATIONS:
            log.debug("reject: unknown relation %r", rel)
            continue
        head_t, tail_t = RELATIONS[rel]
        if head == tail:
            log.debug("reject: self-loop %r", head)
            continue
        # Whitespace-tolerant containment: collapse runs of whitespace on both
        # sides so a valid quote isn't rejected over formatting differences.
        if evidence:
            ev_norm = " ".join(evidence.lower().split())
            chunk_norm = " ".join(chunk_text.lower().split())
            if ev_norm not in chunk_norm:
                log.debug("reject: evidence not in chunk for %r", head)
                continue
        if rel == "HAS_COMPONENT":
            if head != device_name.lower():
                continue
        elif entities.get(head) != head_t:
            log.debug("reject: head type mismatch %r", head)
            continue
        if entities.get(tail) != tail_t:
            log.debug("reject: tail type mismatch %r", tail)
            continue
        triples.append(
            {
                "head": head,
                "relation": rel,
                "tail": tail,
                "head_type": head_t,
                "tail_type": tail_t,
            }
        )
    return triples


# One FIXED MERGE template per relation — the only enrichment Cypher.
# Each template UNWINDs a batch of {head, tail, chunk_id} rows so all triples
# of a given relation for the document are written in a single query, instead
# of one round-trip per triple.
_WRITE_TEMPLATES = {
    "RESOLVED_BY": """
        UNWIND $rows AS row
        MERGE (h:Symptom {name:row.head, device_id:$device_id})
        MERGE (t:Procedure {name:row.tail, device_id:$device_id})
        MERGE (h)-[r:RESOLVED_BY]->(t)
        SET r.source_chunk_id=row.chunk_id, h.source_chunk_id=row.chunk_id,
            t.source_chunk_id=row.chunk_id""",
    "INDICATES": """
        UNWIND $rows AS row
        MERGE (h:ErrorCode {name:row.head, device_id:$device_id})
        MERGE (t:Symptom {name:row.tail, device_id:$device_id})
        MERGE (h)-[r:INDICATES]->(t)
        SET r.source_chunk_id=row.chunk_id, h.source_chunk_id=row.chunk_id,
            t.source_chunk_id=row.chunk_id""",
    "HAS_COMPONENT": """
        UNWIND $rows AS row
        MATCH (h:Device {asset_id:$device_id})
        MERGE (t:Component {name:row.tail, device_id:$device_id})
        MERGE (h)-[r:HAS_COMPONENT]->(t)
        SET r.source_chunk_id=row.chunk_id, t.source_chunk_id=row.chunk_id""",
    "REQUIRES": """
        UNWIND $rows AS row
        MERGE (h:Procedure {name:row.head, device_id:$device_id})
        MERGE (t:Component {name:row.tail, device_id:$device_id})
        MERGE (h)-[r:REQUIRES]->(t)
        SET r.source_chunk_id=row.chunk_id, t.source_chunk_id=row.chunk_id""",
}


def enrich_document(document_id: str, chunk_objects: list[dict]) -> int:
    """Extract + validate + write triples for every chunk of one manual.
    Idempotent: old Layer-2 enrichment for this document's DEVICES is deleted
    first, then MERGE-written. One Neo4j session is reused for the whole
    document, and triples are written in batches per relation via UNWIND."""
    driver = get_neo4j_driver()

    # Devices covered by this document (stable scope — does NOT depend on the
    # freshly generated chunk ids, which change whenever chunk text changes).
    device_ids = sorted({c["device_id"] for c in chunk_objects})
    total = 0
    with driver.session() as s:
        # Clean replacement of Layer-2 enrichment for these devices.
        # Scoped deliberately narrowly so it can NEVER remove authoritative
        # Layer-1 data:
        #   * only enrichment labels (Symptom/Procedure/ErrorCode/Component),
        #   * only nodes that carry provenance (source_chunk_id IS NOT NULL),
        #   * only for this document's device_ids.
        # Device, Room, Incident, Document nodes and CSV-loaded relationships
        # have none of these labels (or no source_chunk_id), so they are safe.
        s.run(
            """MATCH (n)
               WHERE (n:Symptom OR n:Procedure OR n:ErrorCode OR n:Component)
                 AND n.source_chunk_id IS NOT NULL
                 AND n.device_id IN $device_ids
               DETACH DELETE n""",
            device_ids=device_ids,
        )

        # Small pacing delay between enrichment calls. Provider rate limits
        # are per-minute; one call per chunk back-to-back with no pacing
        # trips 429s repeatedly on any manual with more than a handful of
        # chunks, burning time in tenacity's exponential backoff instead of
        # just... not hitting the limit in the first place.
        import time

        delay = get_settings().extraction_call_delay_seconds

        for obj in chunk_objects:
            try:
                raw = _call_llm(obj["text"], obj["device_name"])
            except Exception as exc:  # best-effort per chunk
                log.warning(
                    "enrichment skipped for chunk %s: %s",
                    obj["chunk_id"],
                    _describe_llm_error(exc),
                )
                continue
            finally:
                time.sleep(delay)
            triples = _validate(raw, obj["text"], obj["device_name"])
            if not triples:
                continue

            # group this chunk's triples by relation, then one UNWIND per group
            by_relation: dict[str, list[dict]] = {}
            for t in triples:
                by_relation.setdefault(t["relation"], []).append(
                    {"head": t["head"], "tail": t["tail"], "chunk_id": obj["chunk_id"]}
                )
            for relation, rows in by_relation.items():
                s.run(_WRITE_TEMPLATES[relation], rows=rows, device_id=obj["device_id"])
            total += len(triples)

    log.info("Enrichment for %s: %d validated triples written", document_id, total)
    return total
