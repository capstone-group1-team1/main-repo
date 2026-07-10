"""
retrieval_cache.py — a small in-process LRU cache for retrieval results.

The same question asked twice (a demo, a retry, an eval re-run) otherwise
re-embeds the query and re-hits Weaviate + Neo4j every time. Since retrieval
is deterministic for a given (question, route), we cache the merged candidate
evidence keyed on that pair.

Kept deliberately simple: an OrderedDict-backed LRU with a configurable size,
guarded so caching can be turned off entirely via settings. It stores the
already-merged candidate list (before reranking), so a cache hit still gets a
fresh rerank — which is cheap and keeps ordering correct if the reranker
config changes.
"""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_cache: "OrderedDict[str, list]" = OrderedDict()
_lock = Lock()


def _key(question: str, route: str) -> str:
    return f"{route}::{question.strip().lower()}"


def get(question: str, route: str):
    """Return cached candidates for this (question, route) or None."""
    if not get_settings().retrieval_cache_enabled:
        return None
    key = _key(question, route)
    with _lock:
        if key not in _cache:
            return None
        _cache.move_to_end(key)  # mark most-recently-used
        log.info("retrieval cache hit: %s", key)
        return _cache[key]


def put(question: str, route: str, candidates: list) -> None:
    """Store candidates, evicting the least-recently-used if over capacity."""
    settings = get_settings()
    if not settings.retrieval_cache_enabled:
        return
    key = _key(question, route)
    with _lock:
        _cache[key] = candidates
        _cache.move_to_end(key)
        while len(_cache) > settings.retrieval_cache_size:
            _cache.popitem(last=False)  # evict LRU


def clear() -> None:
    """Drop everything — call after re-ingestion so stale evidence isn't served."""
    with _lock:
        _cache.clear()
    log.info("retrieval cache cleared")
