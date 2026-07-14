"""
reranker.py — cross-encoder re-ranking of retrieved evidence.

First-stage retrieval (bi-encoder vector search + graph traversal) is fast but
orders passages by an approximate similarity. A cross-encoder reads the query
and each passage TOGETHER and scores their true relevance, which reorders the
candidate pool so the most relevant evidence reaches the LLM first and the
weakest is trimmed.

The reranker is optional: if it is disabled (or the model can't load), the
caller does NOT simply keep hybrid_merger's raw merge order -- that order is
graph-facts-first by construction (see hybrid_merger.py's own docstring: it
explicitly assumes a reranker downstream will re-sort before the final trim).
With reranking off, keeping that order verbatim silently starves out every
manual/incident chunk whenever a device has enough graph facts to fill
max_evidence on its own -- a real, previously-hit failure mode, not a
hypothetical one. Instead, the disabled/unavailable path interleaves graph
facts and chunks fairly, so both source types get representation in the
final evidence set regardless of how many graph facts exist.
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


def _interleave_by_type(items: list[Evidence], top_n: int) -> list[Evidence]:
    """Fair fallback ordering used whenever a real relevance re-score isn't
    available: alternates between graph facts and chunks (each keeping its
    own incoming relative order -- hop-distance for facts, vector score for
    chunks) instead of hybrid_merger's graph-first concatenation. If one
    type runs out early, the other fills the remaining slots, so nothing is
    wasted when a question is genuinely graph-only or manual-only."""
    facts = [it for it in items if isinstance(it, GraphFact)]
    chunks = [it for it in items if isinstance(it, RetrievedChunk)]
    out: list[Evidence] = []
    i = j = 0
    while len(out) < top_n and (i < len(facts) or j < len(chunks)):
        if i < len(facts):
            out.append(facts[i])
            i += 1
        if len(out) < top_n and j < len(chunks):
            out.append(chunks[j])
            j += 1
    return out


def rerank(question: str, items: list[Evidence], top_n: int) -> list[Evidence]:
    """Reorder `items` by cross-encoder relevance to `question` and return the
    top_n. Degrades to a fair type-interleaved selection (see
    _interleave_by_type) if reranking is off, unavailable, or fails --
    never to hybrid_merger's raw graph-first merge order."""
    if len(items) <= 1:
        return items[:top_n]

    model = get_reranker_model()
    if model is None:
        return _interleave_by_type(items, top_n)

    try:
        pairs = [(question, _text_of(it)) for it in items]
        scores = model.predict(pairs)
        ranked = sorted(zip(items, scores), key=lambda p: float(p[1]), reverse=True)
        log.info("reranked %d evidence items -> top %d", len(items), top_n)
        return [it for it, _ in ranked[:top_n]]
    except Exception as exc:
        log.warning("rerank failed (%s) — falling back to fair type interleave", exc)
        return _interleave_by_type(items, top_n)
