"""
Tests for app.retrieval.retrieval_cache -- the in-process LRU retrieval cache.

Every assertion here was verified by actually running get()/put()/clear()
against the real module. Each test clears the module-level cache first,
since it's shared global state.
"""
from __future__ import annotations

import app.retrieval.retrieval_cache as rc


class _Settings:
    def __init__(self, enabled=True, size=256):
        self.retrieval_cache_enabled = enabled
        self.retrieval_cache_size = size


def setup_function():
    rc._cache.clear()


def test_put_then_get_roundtrips(monkeypatch):
    monkeypatch.setattr(rc, "get_settings", lambda: _Settings())
    rc.put("what devices depend on the CP4?", "HYBRID", ["candidateA"])
    assert rc.get("what devices depend on the CP4?", "HYBRID") == ["candidateA"]


def test_different_route_is_a_different_cache_key(monkeypatch):
    monkeypatch.setattr(rc, "get_settings", lambda: _Settings())
    rc.put("same question", "HYBRID", ["a"])
    assert rc.get("same question", "RAG_ONLY") is None


def test_key_is_case_and_whitespace_insensitive(monkeypatch):
    monkeypatch.setattr(rc, "get_settings", lambda: _Settings())
    rc.put("What Devices?", "HYBRID", ["a"])
    assert rc.get("  what devices?  ", "HYBRID") == ["a"]


def test_disabled_cache_never_stores_anything(monkeypatch):
    monkeypatch.setattr(rc, "get_settings", lambda: _Settings(enabled=False))
    rc.put("q", "HYBRID", ["x"])
    assert rc.get("q", "HYBRID") is None
    assert len(rc._cache) == 0


def test_lru_eviction_drops_least_recently_used(monkeypatch):
    monkeypatch.setattr(rc, "get_settings", lambda: _Settings(size=2))
    rc.put("a", "HYBRID", [1])
    rc.put("b", "HYBRID", [2])
    rc.put("c", "HYBRID", [3])  # over capacity -- evicts "a"

    assert rc.get("a", "HYBRID") is None
    assert rc.get("b", "HYBRID") == [2]
    assert rc.get("c", "HYBRID") == [3]


def test_get_marks_entry_as_recently_used_protecting_it_from_eviction(monkeypatch):
    monkeypatch.setattr(rc, "get_settings", lambda: _Settings(size=2))
    rc.put("a", "HYBRID", [1])
    rc.put("b", "HYBRID", [2])
    rc.get("a", "HYBRID")           # touch "a" -- now "b" is the LRU one
    rc.put("c", "HYBRID", [3])      # over capacity -- should evict "b", not "a"

    assert rc.get("a", "HYBRID") == [1]
    assert rc.get("b", "HYBRID") is None


def test_clear_empties_the_cache_entirely(monkeypatch):
    monkeypatch.setattr(rc, "get_settings", lambda: _Settings())
    rc.put("a", "HYBRID", [1])
    rc.clear()
    assert len(rc._cache) == 0
    assert rc.get("a", "HYBRID") is None
