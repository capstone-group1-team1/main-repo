"""
Tests for app.router.query_router.route() -- the orchestration layer that
ties entity matching, rules, and the LLM fallback classifier together.

Every assertion here was verified by actually running route() with the
rules/llm_fallback classify() functions monkeypatched (isolating this
module's own branching logic from theirs, which have their own test files).
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.router import llm_fallback, rules
from app.router.entity_matcher import MatchedEntity


@dataclass
class _FakeClassifyResult:
    route: str
    score: float
    margin: float


def test_confident_rules_result_is_used_directly(monkeypatch):
    import app.router.query_router as qr

    monkeypatch.setattr(rules, "classify", lambda q: _FakeClassifyResult(
        route="GRAPH_ONLY", score=2.0, margin=0.5))
    monkeypatch.setattr(qr, "match", lambda q: [])

    decision = qr.route("what depends on CP4?")

    assert decision.route == "GRAPH_ONLY"
    assert decision.mechanism == "rules"
    # 0.5 + margin(0.5), capped at 1.0
    assert decision.router_confidence == 1.0


def test_unsure_rules_falls_through_to_confident_llm_fallback(monkeypatch):
    import app.router.query_router as qr

    monkeypatch.setattr(rules, "classify", lambda q: _FakeClassifyResult(
        route="HYBRID", score=0.1, margin=0.05))  # margin below threshold
    monkeypatch.setattr(llm_fallback, "classify", lambda q: ("RAG_ONLY", 0.85))
    monkeypatch.setattr(qr, "match", lambda q: [])

    decision = qr.route("ambiguous question")

    assert decision.route == "RAG_ONLY"
    assert decision.mechanism == "llm_fallback"
    assert decision.router_confidence == 0.85


def test_both_rules_and_llm_fallback_unsure_defaults_to_hybrid(monkeypatch):
    import app.router.query_router as qr

    monkeypatch.setattr(rules, "classify", lambda q: _FakeClassifyResult(
        route="HYBRID", score=0.1, margin=0.05))
    monkeypatch.setattr(llm_fallback, "classify", lambda q: ("RAG_ONLY", 0.3))
    monkeypatch.setattr(qr, "match", lambda q: [])

    decision = qr.route("very ambiguous question")

    assert decision.route == "HYBRID"
    assert decision.mechanism == "default_hybrid"


def test_llm_fallback_unavailable_defaults_to_hybrid_not_a_crash(monkeypatch):
    """This is the safety net for the exact failure mode this project hit
    in practice: the LLM provider being unreachable must degrade the router
    to a safe default, never raise an exception up through /chat."""
    import app.router.query_router as qr

    monkeypatch.setattr(rules, "classify", lambda q: _FakeClassifyResult(
        route="HYBRID", score=0.1, margin=0.05))

    def _raise(question):
        raise llm_fallback.FallbackUnavailable("provider unreachable")

    monkeypatch.setattr(llm_fallback, "classify", _raise)
    monkeypatch.setattr(qr, "match", lambda q: [])

    decision = qr.route("question during an outage")

    assert decision.route == "HYBRID"
    assert decision.mechanism == "default_hybrid"
    assert decision.router_confidence == 0.3


def test_matched_entities_are_carried_through_regardless_of_mechanism(monkeypatch):
    import app.router.query_router as qr

    entity = MatchedEntity(surface="cp4", canonical_id="CP4-001", kind="device")
    monkeypatch.setattr(qr, "match", lambda q: [entity])
    monkeypatch.setattr(rules, "classify", lambda q: _FakeClassifyResult(
        route="GRAPH_ONLY", score=2.0, margin=0.5))

    decision = qr.route("what depends on the cp4?")

    assert decision.entities == [entity]
