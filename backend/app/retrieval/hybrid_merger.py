"""
hybrid_merger.py — composes the candidate evidence list for HYBRID answers.

Graph facts go first (the causal/dependency frame), then manual/incident
chunks (the how-to detail). Two kinds of duplication are removed:

  1. an enrichment fact whose source_chunk_id equals a retrieved chunk's id
     (the chunk already contains that text), and
  2. near-identical chunks (same normalized text) that different device
     filters or multi-device retrieval can surface twice.

It returns up to `rerank_candidate_pool` items — a POOL, not the final list —
so the cross-encoder reranker downstream has enough candidates to reorder
before the list is trimmed to `max_evidence`.
"""

from __future__ import annotations

import re

from app.core.config import get_settings
from app.models.schemas import GraphFact, RetrievedChunk

Evidence = GraphFact | RetrievedChunk


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def merge(chunks: list[RetrievedChunk], facts: list[GraphFact]) -> list[Evidence]:
    chunk_ids = {c.chunk_id for c in chunks}

    # (1) drop enrichment facts already contained in a retrieved chunk
    kept_facts = [
        f
        for f in facts
        if f.source_chunk_id is None or f.source_chunk_id not in chunk_ids
    ]

    # (2) de-duplicate chunks by normalized text (keep first / highest-ranked)
    seen: set[str] = set()
    unique_chunks: list[RetrievedChunk] = []
    for c in chunks:
        key = _norm(c.text)
        if key in seen:
            continue
        seen.add(key)
        unique_chunks.append(c)

    merged: list[Evidence] = [*kept_facts, *unique_chunks]
    return merged[: get_settings().rerank_candidate_pool]
