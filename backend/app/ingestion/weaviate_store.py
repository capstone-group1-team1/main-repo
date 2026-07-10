"""
weaviate_store.py — all Weaviate reads/writes in one module.

Collection "SmartOfficeChunk" stores every chunk with its FULL citation
metadata as properties, plus the bge-large vector (we bring our own vectors:
vectorizer = none).  Deterministic UUIDs (derived from chunk_id) plus
delete-by-document_id-before-insert make writes idempotent.
"""

from __future__ import annotations

from typing import Optional

from weaviate.classes.config import Configure, DataType, Property
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.util import generate_uuid5

from app.core.config import get_weaviate_client
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk

log = get_logger(__name__)

COLLECTION = "SmartOfficeChunk"


def ensure_collection() -> None:
    """Create the collection if absent (idempotent)."""
    client = get_weaviate_client()
    if client.collections.exists(COLLECTION):
        return
    client.collections.create(
        name=COLLECTION,
        vectorizer_config=Configure.Vectorizer.none(),
        properties=[
            Property(name="chunk_id", data_type=DataType.TEXT),
            Property(name="text", data_type=DataType.TEXT),
            Property(name="source_type", data_type=DataType.TEXT),  # manual | incident
            Property(name="source_id", data_type=DataType.TEXT),
            Property(name="document_id", data_type=DataType.TEXT),
            Property(name="document_name", data_type=DataType.TEXT),
            Property(name="device_id", data_type=DataType.TEXT),
            Property(name="device_name", data_type=DataType.TEXT),
            Property(name="section_title", data_type=DataType.TEXT),
            Property(name="page_number", data_type=DataType.INT),
            Property(name="doc_hash", data_type=DataType.TEXT),
            Property(name="ingested_at", data_type=DataType.TEXT),
        ],
    )
    log.info("Created Weaviate collection %s", COLLECTION)


def delete_document(document_id: str) -> None:
    """Remove every chunk of one document (clean replacement / recovery)."""
    col = get_weaviate_client().collections.get(COLLECTION)
    col.data.delete_many(where=Filter.by_property("document_id").equal(document_id))


def insert_chunks(objects: list[dict], vectors: list[list[float]]) -> int:
    """Insert chunk property-dicts with their vectors.  UUIDs are derived
    from chunk_id, so re-inserting the same chunk can never duplicate."""
    col = get_weaviate_client().collections.get(COLLECTION)
    with col.batch.dynamic() as batch:
        for props, vec in zip(objects, vectors):
            batch.add_object(
                properties=props,
                vector=vec,
                uuid=generate_uuid5(props["chunk_id"]),
            )
    failed = col.batch.failed_objects
    if failed:
        raise RuntimeError(f"Weaviate insert failed for {len(failed)} objects")
    return len(objects)


def count_chunks() -> int:
    col = get_weaviate_client().collections.get(COLLECTION)
    return col.aggregate.over_all(total_count=True).total_count or 0


def search(
    query_vector: list[float],
    k: int = 5,
    device_id: Optional[str] = None,
) -> list[RetrievedChunk]:
    """Vector search.  Optional device filter (from the router's extracted
    entity); if the filtered search finds < 2 hits we retry unfiltered so an
    over-strict entity match never starves retrieval."""
    col = get_weaviate_client().collections.get(COLLECTION)

    def _run(filters):
        return col.query.near_vector(
            near_vector=query_vector,
            limit=k,
            filters=filters,
            return_metadata=MetadataQuery(distance=True),
        )

    filters = Filter.by_property("device_id").equal(device_id) if device_id else None
    res = _run(filters)
    if filters is not None and len(res.objects) < 2:
        res = _run(None)  # graceful widening

    chunks: list[RetrievedChunk] = []
    for obj in res.objects:
        p = obj.properties
        similarity = 1.0 - float(obj.metadata.distance or 1.0)  # cosine
        chunks.append(
            RetrievedChunk(
                chunk_id=p["chunk_id"],
                text=p["text"],
                score=max(0.0, min(1.0, similarity)),
                source_type=p["source_type"],
                source_id=p["source_id"],
                document_id=p["document_id"],
                document_name=p["document_name"],
                device_id=p["device_id"],
                device_name=p["device_name"],
                section_title=p["section_title"],
                page_number=p.get("page_number"),
            )
        )
    return chunks
