"""
Tests for app.synthesis.confidence — the three confidence signals.

Every numeric expectation here was computed by actually running the real
retrieval_confidence()/graph_confidence()/final_confidence() functions
against these exact inputs, not derived from reading the formula alone.
"""
from __future__ import annotations

from app.models.schemas import GraphSignals, RetrievalSignals
from app.synthesis.confidence import (final_confidence, graph_confidence,
                                      retrieval_confidence)


# ---------------------------------------------------------------------------
# retrieval_confidence
# ---------------------------------------------------------------------------

def test_retrieval_confidence_no_scores_is_zero():
    assert retrieval_confidence(RetrievalSignals(scores=[])) == 0.0


def test_retrieval_confidence_strong_top_hit_with_clear_gap_is_high():
    sig = RetrievalSignals(scores=[0.75, 0.40, 0.38, 0.35, 0.30])
    assert retrieval_confidence(sig) == 1.0


def test_retrieval_confidence_single_score_uses_default_gap():
    # No "rest" of the distribution to compare against -> gap defaults to
    # the fully-decisive 0.15, so a strong single top score maxes out.
    sig = RetrievalSignals(scores=[0.75])
    assert retrieval_confidence(sig) == 1.0


def test_retrieval_confidence_mediocre_close_scores_is_low():
    # Several close, unremarkable scores -- no single hit stands out.
    sig = RetrievalSignals(scores=[0.50, 0.49, 0.48, 0.47])
    assert retrieval_confidence(sig) == 0.29


# ---------------------------------------------------------------------------
# graph_confidence
# ---------------------------------------------------------------------------

def test_graph_confidence_no_facts_is_zero():
    assert graph_confidence(GraphSignals(fact_count=0)) == 0.0


def test_graph_confidence_exact_match_short_hop_many_facts_is_high():
    sig = GraphSignals(any_exact_entity_match=True, min_hop_count=1, fact_count=5)
    assert graph_confidence(sig) == 1.0


def test_graph_confidence_fuzzy_match_is_penalized():
    sig = GraphSignals(any_exact_entity_match=False, min_hop_count=1, fact_count=5)
    assert graph_confidence(sig) == 0.35


# ---------------------------------------------------------------------------
# final_confidence
# ---------------------------------------------------------------------------

def test_final_confidence_graph_only_uses_graph_signal_alone():
    result = final_confidence("GRAPH_ONLY", r_conf=None, g_conf=0.9,
                              citation_count=2, unsourced_count=0, sentence_count=2)
    assert result.final == 0.9
    assert result.graph == 0.9
    assert result.retrieval is None


def test_final_confidence_rag_only_uses_retrieval_signal_alone():
    result = final_confidence("RAG_ONLY", r_conf=0.8, g_conf=None,
                              citation_count=2, unsourced_count=0, sentence_count=2)
    assert result.final == 0.8
    assert result.retrieval == 0.8
    assert result.graph is None


def test_final_confidence_hybrid_blends_agreeing_signals():
    result = final_confidence("HYBRID", r_conf=0.8, g_conf=0.8,
                              citation_count=3, unsourced_count=0, sentence_count=3)
    assert result.final == 0.8


def test_final_confidence_hybrid_punishes_signal_disagreement():
    # Same average (0.5) as an agreeing 0.5/0.5 pair would give 0.5, but a
    # sharp disagreement between the two signals should score noticeably
    # lower than a calm agreement at the same average.
    result = final_confidence("HYBRID", r_conf=0.9, g_conf=0.1,
                              citation_count=3, unsourced_count=0, sentence_count=3)
    assert result.final == 0.3


def test_final_confidence_zero_citations_caps_at_point_25_regardless_of_base():
    # Even a perfect graph_confidence of 1.0 cannot present as confident if
    # the answer cites nothing -- this is a hard, structural safety cap.
    result = final_confidence("GRAPH_ONLY", r_conf=None, g_conf=1.0,
                              citation_count=0, unsourced_count=0, sentence_count=1)
    assert result.final == 0.25


def test_final_confidence_unsourced_spans_deduct_proportionally():
    # 1 of 2 sentences unsourced -- 0.30 * 0.5 = 0.15 deducted from a base of 1.0.
    result = final_confidence("RAG_ONLY", r_conf=1.0, g_conf=None,
                              citation_count=2, unsourced_count=1, sentence_count=2)
    assert result.final == 0.85


def test_final_confidence_level_field_is_computed_but_not_on_the_response():
    """Documents a real, verified quirk: final_confidence() computes a
    high/medium/low `level` internally and passes it to Confidence(...), but
    the Confidence schema (app.models.schemas) has no `level` field --
    pydantic v2's default extra='ignore' behavior silently drops it. This
    is harmless: the frontend's ConfidenceBadge component independently
    recomputes the same high/medium/low banding from `final` using the same
    0.75/0.4 thresholds, so nothing relies on this field existing. This test
    exists so a future refactor doesn't accidentally assume `.level` is
    present on the API response.
    """
    result = final_confidence("GRAPH_ONLY", r_conf=None, g_conf=0.9,
                              citation_count=2, unsourced_count=0, sentence_count=2)
    assert not hasattr(result, "level")
    assert "level" not in result.model_dump()
