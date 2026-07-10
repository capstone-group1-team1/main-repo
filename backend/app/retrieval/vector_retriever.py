"""
vector_retriever.py — the RAG branch.

Embeds the question (bge query prefix) once and searches Weaviate. If the
router matched one or more devices, we search PER DEVICE and union the results
(so a question mentioning two devices retrieves evidence for both, not just
the first). If no device matched, we do a single unfiltered search.

Returns RetrievedChunk objects (text + FULL citation metadata) plus
RetrievalSignals for confidence.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.ingestion.embedder import embed_query
from app.ingestion.weaviate_store import search
from app.models.schemas import RetrievalSignals, RetrievedChunk
from app.router.entity_matcher import MatchedEntity


def retrieve(
    question: str, entities: list[MatchedEntity], k: int | None = None
) -> tuple[list[RetrievedChunk], RetrievalSignals]:
    if k is None:
        k = get_settings().retrieval_top_k

    device_ids = [e.canonical_id for e in entities if e.kind == "device"]
    query_vec = embed_query(question)  # embed once, reuse across devices

    if not device_ids:
        chunks = search(query_vec, k=k, device_id=None)
    else:
        # search each matched device, then dedupe by chunk_id preserving the
        # best (first-seen) order.
        seen: set[str] = set()
        chunks = []
        for did in device_ids:
            for c in search(query_vec, k=k, device_id=did):
                if c.chunk_id in seen:
                    continue
                seen.add(c.chunk_id)
                chunks.append(c)

    # highest score first, so first-stage order is sensible even before rerank
    chunks.sort(key=lambda c: c.score, reverse=True)
    return chunks, RetrievalSignals(scores=[c.score for c in chunks])
