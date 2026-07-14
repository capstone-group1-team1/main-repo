"""
embedder.py — the ONLY place text becomes vectors (bge-large-en-v1.5, local).

One shared model instance guarantees document vectors (here) and query
vectors (retrieval) live in the same embedding space.
"""

from __future__ import annotations

from app.core.config import BGE_QUERY_PREFIX, get_embed_model, get_settings


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed document chunks (no prefix, normalized)."""
    model = get_embed_model()
    vecs = model.encode(
        texts,
        batch_size=get_settings().embed_batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [v.tolist() for v in vecs]


def embed_query(question: str) -> list[float]:
    """Embed a search query.  bge models want the instruction prefix on
    queries only — this asymmetry is the model's documented usage."""
    model = get_embed_model()
    vec = model.encode(
        BGE_QUERY_PREFIX + question, normalize_embeddings=True, show_progress_bar=False
    )
    return vec.tolist()
