"""
Tests for the two helpers routes_chat.py shares between POST /chat and
POST /chat/stream: _get_evidence() (cache-first retrieval + rerank) and
_finalize() (citation assembly + confidence, given a complete answer text).

NOTE ON VERIFICATION: unlike this project's other new test files, these
were NOT executed end-to-end in the authoring sandbox -- routes_chat.py's
import chain pulls in slowapi, starlette's StreamingResponse, and every
retrieval module, which wasn't practical to fully stub outside a real
environment. These were instead written by tracing the exact source of
_get_evidence()/_finalize() line by line. Treat this file as a strong
starting point to run for real (`pytest backend/tests/test_routes_chat_helpers.py`)
rather than a pre-verified guarantee like the rest of this test suite.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from app.models.schemas import GraphFact, GraphSignals, RetrievalSignals, RetrievedChunk


def _chunk(chunk_id="c1", text="Some evidence text."):
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        score=0.9,
        source_type="manual",
        source_id=chunk_id,
        document_id="d1",
        document_name="Doc",
        device_id="dev1",
        device_name="Dev",
        section_title="S",
    )


class _FakeDecision:
    def __init__(self, route, entities=None):
        self.route = route
        self.entities = entities or []


@pytest.fixture
def routes_chat(monkeypatch):
    import app.api.routes_chat as rc

    return rc


def test_get_evidence_uses_cached_candidates_when_present(routes_chat, monkeypatch):
    """A cache hit must skip vector_retriever/graph_retriever entirely --
    only the rerank step should still run (see the module's own comment:
    'a cache hit still gets a fresh rerank')."""
    cached_chunk = _chunk("cached-1")
    monkeypatch.setattr(
        routes_chat.retrieval_cache,
        "get",
        lambda q, route: {
            "candidates": [cached_chunk],
            "r_sig": RetrievalSignals(scores=[0.9]),
            "g_sig": GraphSignals(),
        },
    )
    vector_retriever_called = Mock()
    monkeypatch.setattr(
        routes_chat.vector_retriever, "retrieve", vector_retriever_called
    )
    monkeypatch.setattr(routes_chat.reranker, "rerank", lambda q, cands, top_n: cands)
    monkeypatch.setattr(
        routes_chat, "get_settings", lambda: type("S", (), {"max_evidence": 10})()
    )

    decision = _FakeDecision("RAG_ONLY")
    evidence, r_sig, g_sig = routes_chat._get_evidence("some question", decision)

    vector_retriever_called.assert_not_called()
    assert evidence == [cached_chunk]


def test_get_evidence_on_cache_miss_retrieves_and_caches_the_result(
    routes_chat, monkeypatch
):
    monkeypatch.setattr(routes_chat.retrieval_cache, "get", lambda q, route: None)
    put_calls = []
    monkeypatch.setattr(
        routes_chat.retrieval_cache,
        "put",
        lambda q, route, data: put_calls.append((q, route, data)),
    )
    fresh_chunk = _chunk("fresh-1")
    monkeypatch.setattr(
        routes_chat.vector_retriever,
        "retrieve",
        lambda q, entities: ([fresh_chunk], RetrievalSignals(scores=[0.8])),
    )
    monkeypatch.setattr(routes_chat.reranker, "rerank", lambda q, cands, top_n: cands)
    monkeypatch.setattr(
        routes_chat, "get_settings", lambda: type("S", (), {"max_evidence": 10})()
    )

    decision = _FakeDecision("RAG_ONLY")
    evidence, r_sig, g_sig = routes_chat._get_evidence("some question", decision)

    assert evidence == [fresh_chunk]
    assert len(put_calls) == 1  # result was cached for next time


def test_get_evidence_degrades_gracefully_when_a_retrieval_branch_raises(
    routes_chat, monkeypatch
):
    """A HYBRID question where the graph branch fails must still return
    whatever the vector branch found, not blow up the whole request --
    the module's own comment: 'Degrade rather than fail'."""
    monkeypatch.setattr(routes_chat.retrieval_cache, "get", lambda q, route: None)
    monkeypatch.setattr(routes_chat.retrieval_cache, "put", lambda *a: None)
    good_chunk = _chunk("good-1")
    monkeypatch.setattr(
        routes_chat.vector_retriever,
        "retrieve",
        lambda q, entities: ([good_chunk], RetrievalSignals(scores=[0.8])),
    )
    monkeypatch.setattr(
        routes_chat.graph_retriever,
        "retrieve",
        Mock(side_effect=Exception("neo4j unreachable")),
    )
    monkeypatch.setattr(routes_chat.reranker, "rerank", lambda q, cands, top_n: cands)
    monkeypatch.setattr(
        routes_chat, "get_settings", lambda: type("S", (), {"max_evidence": 10})()
    )

    decision = _FakeDecision("HYBRID")
    evidence, r_sig, g_sig = routes_chat._get_evidence("some question", decision)

    # Graph branch failed but vector branch's result still made it through.
    assert good_chunk in evidence
