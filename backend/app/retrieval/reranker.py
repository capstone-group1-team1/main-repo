"""
reranker.py — cross-encoder re-ranking of retrieved evidence.

First-stage retrieval (bi-encoder vector search + graph traversal) is fast but
orders passages by an approximate similarity. A cross-encoder reads the query
and each passage TOGETHER and scores their true relevance, which reorders the
candidate pool so the most relevant evidence reaches the LLM first and the
weakest is trimmed.

The reranker is optional: if it is disabled (or the model can't load) the
caller keeps the original merge order, so retrieval never hard-fails on this.
"""

from __future__ import annotations

from app.core.config import get_reranker_model, get_settings
from app.core.logging import get_logger
from app.models.schemas import GraphFact, RetrievedChunk

log = get_logger(__name__)

Evidence = GraphFact | RetrievedChunk


def _text_of(item: Evidence) -> str:
    """The comparable text for an evidence item. Chunks carry their passage;
    graph facts carry a human-readable sentence (`text`) and a path rendering
    (`path_str`). Prefer those real fields; only fall back to str(item) if
    there is genuinely no usable text, so the cross-encoder never scores a
    stringified Pydantic object."""
    if isinstance(item, RetrievedChunk):
        return item.text
    # GraphFact: prefer the human-readable sentence, then the path string.
    return getattr(item, "text", None) or getattr(item, "path_str", None) or str(item)


def rerank(question: str, items: list[Evidence], top_n: int) -> list[Evidence]:
    """Reorder `items` by cross-encoder relevance to `question` and return the
    top_n. Degrades to `items[:top_n]` if reranking is off or unavailable."""
    if len(items) <= 1:
        return items[:top_n]

    model = get_reranker_model()
    if model is None:
        return items[:top_n]

    try:
        pairs = [(question, _text_of(it)) for it in items]
        scores = model.predict(pairs)
        ranked = sorted(zip(items, scores), key=lambda p: float(p[1]), reverse=True)
        log.info("reranked %d evidence items -> top %d", len(items), top_n)
        return [it for it, _ in ranked[:top_n]]
    except Exception as exc:
        log.warning("rerank failed (%s) — keeping merge order", exc)
        return items[:top_n]
