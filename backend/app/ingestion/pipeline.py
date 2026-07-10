"""
pipeline.py — the ingestion orchestrator.  Run with:

    python -m app.ingestion.pipeline

Flow per manual PDF:
    hash gate -> read pdf -> structure-aware chunking -> metadata
    -> embeddings (bge-large) -> Weaviate write
    -> (optional) LLM graph enrichment -> Neo4j
    -> manifest 'complete'

Also ingests every incident row (each row = one retrievable, citable chunk
whose source_id is its Incident ID) and is safe to re-run at any time:
unchanged documents are skipped, changed ones are cleanly replaced, and a
crashed run leaves a 'pending' manifest row that the next run detects,
cleans (delete-by-document_id) and redoes.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.ingestion import weaviate_store
from app.ingestion.catalog import ManualMatch, match_manuals_to_devices
from app.ingestion.chunker import chunk_document
from app.ingestion.hash_store import HashStore, content_hash
from app.ingestion.pdf_reader import read_pdf

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Manual ingestion
# ---------------------------------------------------------------------------


def _chunk_objects(match: ManualMatch, doc_hash: str) -> tuple[list[dict], list[str]]:
    """Read + chunk one manual; return (weaviate property dicts, texts).
    All device metadata is derived from the matched inventory row — nothing
    hardcoded."""
    device = match.device
    pdf_path = get_settings().project_root / "data" / "manuals_pdf" / match.filename
    pages = read_pdf(pdf_path)
    chunks = chunk_document(pages)

    now = datetime.now(timezone.utc).isoformat()
    objects, texts = [], []
    for c in chunks:
        # Include the chunk TEXT in the id so that if a manual is edited and a
        # chunk's content changes (even with the same section/ordinal), it gets
        # a new id — old vectors are replaced, not silently kept.
        chunk_id = content_hash(
            f"{device.document_id}|{c.section_title}|{c.ordinal}|{c.text}"
        )[:16]
        objects.append(
            {
                "chunk_id": chunk_id,
                "text": c.text,
                "source_type": "manual",
                "source_id": f"{device.document_name} § {c.section_title}",
                "document_id": device.document_id,
                "document_name": device.document_name,
                "device_id": device.asset_id,
                "device_name": device.device_name,
                "section_title": c.section_title,
                "page_number": c.page_number,
                "doc_hash": doc_hash,
                "ingested_at": now,
            }
        )
        texts.append(c.text)
    return objects, texts


def ingest_manual(match: ManualMatch, store: HashStore, enrich: bool) -> str:
    """Ingest one matched manual. Returns the action taken (for the report).
    The hash store makes this idempotent: unchanged files skip, changed files
    are cleanly replaced, and a crashed run is detected and redone."""
    device = match.device
    pdf_path = get_settings().project_root / "data" / "manuals_pdf" / match.filename

    doc_hash = content_hash(pdf_path.read_bytes())
    decision = store.decide(device.document_id, doc_hash)
    if decision == "unchanged":
        log.info("SKIP  %-45s (hash unchanged)", match.filename)
        return "skipped"
    if decision == "retry_pending":
        log.warning(
            "RECOVER %s: previous run crashed mid-ingest; " "cleaning partial entries.",
            device.document_id,
        )

    store.mark_pending(device.document_id, doc_hash)

    # Clean replacement: remove any old/partial entries first.
    weaviate_store.delete_document(device.document_id)

    objects, texts = _chunk_objects(match, doc_hash)
    from app.ingestion.embedder import embed_texts  # lazy: heavy model

    vectors = embed_texts(texts)
    n = weaviate_store.insert_chunks(objects, vectors)
    log.info("INGEST %-45s -> %d chunks", match.filename, n)

    # DESCRIBED_BY edges in the graph (device -> document).
    from app.graph.graph_loader import link_described_by

    link_described_by(device)

    # Optional LLM enrichment (troubleshooting concepts into the graph).
    if enrich:
        from app.extraction.extractor import enrich_document

        enrich_document(device.document_id, objects)

    store.mark_complete(device.document_id, n)
    return decision  # 'new' | 'changed' | 'retry_pending'


# ---------------------------------------------------------------------------
# Incident ingestion (each row = one chunk; source_id = Incident ID)
# ---------------------------------------------------------------------------


def incident_to_object(row: dict) -> tuple[dict, str]:
    text = (
        f"Incident {row['incident_id']} on device {row['device_id']} "
        f"({row['date']}). Problem: {row['problem']}. "
        f"Resolution: {row['resolution']}. Technician: {row['technician']}."
    )
    props = {
        "chunk_id": f"inc-{row['incident_id']}",
        "text": text,
        "source_type": "incident",
        "source_id": row["incident_id"],
        "document_id": f"incident-{row['incident_id']}",
        "document_name": f"Incident {row['incident_id']}",
        "device_id": row["device_id"],
        "device_name": row["device_id"],
        "section_title": row["problem"][:60],
        "page_number": 0,
        "doc_hash": content_hash(text),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    return props, text


def ingest_incident_row(row: dict, store: HashStore) -> str:
    props, text = incident_to_object(row)
    doc_id = props["document_id"]
    decision = store.decide(doc_id, props["doc_hash"])
    if decision == "unchanged":
        return "skipped"
    store.mark_pending(doc_id, props["doc_hash"])
    weaviate_store.delete_document(doc_id)
    from app.ingestion.embedder import embed_texts

    weaviate_store.insert_chunks([props], embed_texts([text]))
    store.mark_complete(doc_id, 1)
    return decision


def ingest_incidents_csv(store: HashStore) -> dict[str, int]:
    path = get_settings().project_root / "data" / "incidents.csv"
    counts = {"new": 0, "changed": 0, "skipped": 0, "retry_pending": 0}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            counts[ingest_incident_row(row, store)] += 1
    return counts


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------


def run_full() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("=== Ingestion pipeline starting ===")

    weaviate_store.ensure_collection()
    store = HashStore()

    # Discover manuals present in data/manuals_pdf/ and match them to devices
    # from the inventory CSV. Adding a PDF (named after its device) + a CSV row
    # is all it takes — this loop picks it up automatically, nothing hardcoded.
    matches = match_manuals_to_devices()
    log.info("Discovered %d manual(s) matched to devices", len(matches))

    manual_actions: dict[str, int] = {}
    for match in matches:
        action = ingest_manual(match, store, enrich=settings.enable_graph_enrichment)
        manual_actions[action] = manual_actions.get(action, 0) + 1

    inc_counts = ingest_incidents_csv(store)

    log.info("=== Ingestion report ===")
    log.info("Manuals:   %s", manual_actions)
    log.info("Incidents: %s", inc_counts)
    log.info("Weaviate total chunks: %d", weaviate_store.count_chunks())
    for row in store.summary():
        log.info("manifest  %-28s v%-2s %-9s chunks=%-3s %s", *row)
    store.close()
    from app.core.config import close_all_clients

    close_all_clients()  # close Neo4j + Weaviate cleanly (no resource warnings)


if __name__ == "__main__":
    run_full()
