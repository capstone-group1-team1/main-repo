"""
retrieval_baselines.py — the retrieval baseline ladder (Module 12 §4 / R2).

Four retrieval configurations over the SAME Weaviate collection, compared on
the SAME metric (Recall@k: does a chunk from the gold manual appear in the
top-k?), so each stage's contribution is isolated:

  1. BM25 only        — literature-standard keyword baseline (Module 12's own
                         example baseline for RAG: "keyword BM25 retrieval").
  2. Dense only        — pure vector/semantic search (bge-large embeddings).
  3. Hybrid            — BM25 + dense fused (Weaviate's query.hybrid, the
                         production default — see weaviate_store.search()).
  4. Hybrid + reranker — hybrid candidates re-scored by the production
                         cross-encoder (app.retrieval.reranker).

This module talks to Weaviate directly rather than going through
app.ingestion.weaviate_store.search(), because that function always does
hybrid-or-fallback — it has no "BM25 only" or "dense only" mode, and adding
one there would complicate the production code path for an eval-only need.
Everything here is READ-ONLY against the already-ingested collection.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings, get_weaviate_client  # noqa: E402
from app.ingestion.embedder import embed_query  # noqa: E402
from app.ingestion.weaviate_store import COLLECTION  # noqa: E402

STAGES = ["bm25", "dense", "hybrid", "hybrid_reranked"]


def _collection():
    return get_weaviate_client().collections.get(COLLECTION)


def bm25_search(question: str, k: int = 5) -> list[dict]:
    """Stage 1: pure keyword search, no vector at all."""
    from weaviate.classes.query import MetadataQuery

    res = _collection().query.bm25(
        query=question, limit=k, return_metadata=MetadataQuery(score=True)
    )
    return [
        dict(o.properties, score=float(o.metadata.score or 0.0)) for o in res.objects
    ]


def dense_search(question: str, k: int = 5) -> list[dict]:
    """Stage 2: pure vector/semantic search, no keyword signal at all."""
    from weaviate.classes.query import MetadataQuery

    vec = embed_query(question)
    res = _collection().query.near_vector(
        near_vector=vec, limit=k, return_metadata=MetadataQuery(distance=True)
    )
    return [
        dict(o.properties, score=1.0 - float(o.metadata.distance or 1.0))
        for o in res.objects
    ]


def hybrid_search(question: str, k: int = 5, alpha: float | None = None) -> list[dict]:
    """Stage 3: BM25 + dense fused in one Weaviate call (production default)."""
    from weaviate.classes.query import MetadataQuery

    if alpha is None:
        alpha = get_settings().hybrid_search_alpha
    vec = embed_query(question)
    res = _collection().query.hybrid(
        query=question,
        vector=vec,
        alpha=alpha,
        limit=k,
        return_metadata=MetadataQuery(score=True),
    )
    return [
        dict(o.properties, score=float(o.metadata.score or 0.0)) for o in res.objects
    ]


def hybrid_reranked_search(question: str, k: int = 5, pool: int = 20) -> list[dict]:
    """Stage 4: hybrid retrieves a larger candidate POOL, the production
    cross-encoder reranker re-scores it, then it's trimmed to k. This is
    exactly what the live /chat RAG branch does (vector_retriever + reranker),
    just isolated here without the graph branch or device filtering."""
    from app.models.schemas import RetrievedChunk
    from app.retrieval import reranker as reranker_module

    candidates_raw = hybrid_search(question, k=pool)
    candidates = [
        RetrievedChunk(
            chunk_id=c["chunk_id"],
            text=c["text"],
            score=c.get("score", 0.0),
            source_type=c["source_type"],
            source_id=c["source_id"],
            document_id=c["document_id"],
            document_name=c["document_name"],
            device_id=c["device_id"],
            device_name=c["device_name"],
            section_title=c["section_title"],
            page_number=c.get("page_number"),
        )
        for c in candidates_raw
    ]
    ranked = reranker_module.rerank(question, candidates, top_n=k)
    return [c.model_dump() for c in ranked]


_SEARCH_FN = {
    "bm25": bm25_search,
    "dense": dense_search,
    "hybrid": hybrid_search,
    "hybrid_reranked": hybrid_reranked_search,
}


def recall_at_k(retrieved: list[dict], gold_document_id: str | None) -> bool:
    """Did any retrieved chunk come from the gold manual? Undefined (None
    treated as vacuously satisfied) for questions with no gold document —
    i.e. GRAPH_ONLY items, which this retrieval ladder doesn't apply to."""
    if gold_document_id is None:
        return None
    return any(c.get("document_id") == gold_document_id for c in retrieved)


def reciprocal_rank(
    retrieved: list[dict], gold_document_id: str | None
) -> float | None:
    """1 / (rank of the first gold-document chunk, 1-indexed), or 0.0 if the
    gold document never appears in `retrieved` at all. None (like
    recall_at_k) for questions with no gold document. This is stricter than
    recall_at_k: two stages can have identical Recall@5 (gold document
    appeared SOMEWHERE in the top 5) while differing sharply on MRR (one
    puts it at rank 1, the other at rank 5) -- MRR is what actually reflects
    whether the LLM sees the right evidence FIRST, since evidence order
    matters for what a token-budget-limited prompt actually includes."""
    if gold_document_id is None:
        return None
    for rank, c in enumerate(retrieved, start=1):
        if c.get("document_id") == gold_document_id:
            return round(1.0 / rank, 3)
    return 0.0


def run_ladder(heldout_rag_items: list[dict], k: int = 5) -> dict:
    """Run all four stages over every RAG-answerable held-out item (i.e.
    items carrying a gold_document_id) and report Recall@k AND MRR per
    stage."""
    results = {stage: [] for stage in STAGES}
    for item in heldout_rag_items:
        gold = item["metadata"].get("gold_document_id")
        if gold is None:
            continue
        for stage in STAGES:
            retrieved = _SEARCH_FN[stage](item["input"], k=k)
            hit = recall_at_k(retrieved, gold)
            rr = reciprocal_rank(retrieved, gold)
            results[stage].append(
                {"id": item["id"], "hit": bool(hit), "reciprocal_rank": rr}
            )

    summary = {}
    for stage, rows in results.items():
        n = len(rows)
        hits = sum(1 for r in rows if r["hit"])
        mrr = round(sum(r["reciprocal_rank"] for r in rows) / n, 3) if n else 0.0
        summary[stage] = {
            "recall_at_k": round(hits / n, 3) if n else 0.0,
            "mrr": mrr,
            "n": n,
        }
    return {"k": k, "summary": summary, "per_item": results}
