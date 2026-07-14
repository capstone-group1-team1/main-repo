"""
Tests for metrics.py's semantic-only grounding check (no LLM judge — see the
module docstring in metrics.py for why the LLM judge was removed this
session: it doubled LLM calls per item, which was the dominant cost to both
eval runtime and Groq's daily quota).

Run from eval/: python -m pytest test_metrics.py -v
(or plain `python test_metrics.py` — see the __main__ block at the bottom,
since this repo's eval/ isn't always run under pytest directly.)
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def _run_all():
    import metrics

    # --- is_decline ---
    assert metrics.is_decline("The available sources do not cover this question.")
    assert not metrics.is_decline("Reset the receiver by holding the button.")
    print("test_is_decline: PASS")

    # --- semantic_grounding_score / _cosine pure math ---
    assert abs(metrics._cosine([1, 0, 0], [1, 0, 0]) - 1.0) < 1e-9
    assert abs(metrics._cosine([1, 0, 0], [0, 1, 0])) < 1e-9
    print("test_cosine_similarity_math: PASS")

    with patch("metrics.embed_query", lambda t: [1.0, 0.0]), patch(
        "app.ingestion.embedder.embed_texts", lambda ts: [[1.0, 0.0] for _ in ts]
    ):
        score = metrics.semantic_grounding_score("some answer", ["matching evidence"])
        assert abs(score - 1.0) < 1e-6
    print("test_semantic_grounding_score_identical_vectors: PASS")

    assert metrics.semantic_grounding_score("answer", []) == 0.0
    print("test_semantic_grounding_score_no_evidence: PASS")

    # --- check_grounded: no LLM call anywhere in this path ---
    with patch("metrics.embed_query", lambda t: [1.0, 0.0]), patch(
        "app.ingestion.embedder.embed_texts", lambda ts: [[1.0, 0.0] for _ in ts]
    ):
        result = metrics.check_grounded(
            "answer text", ["evidence text"], semantic_threshold=0.5
        )
        assert result["grounded"] is True
        assert "llm_score" not in result  # confirms the LLM judge field is gone
        assert result["semantic_score"] == 1.0
    print("test_check_grounded_no_llm_field_present: PASS")

    with patch("metrics.embed_query", lambda t: [1.0, 0.0]), patch(
        "app.ingestion.embedder.embed_texts", lambda ts: [[0.0, 1.0] for _ in ts]
    ):
        result = metrics.check_grounded(
            "unrelated answer", ["unrelated evidence"], semantic_threshold=0.5
        )
        assert result["grounded"] is False
    print("test_check_grounded_below_threshold_not_grounded: PASS")

    # --- declines are excluded (grounded=None), not scored either way ---
    result = metrics.check_grounded(
        "The available sources do not cover this question.", ["some evidence"]
    )
    assert result["grounded"] is None
    print("test_check_grounded_decline_excluded: PASS")

    # --- grounded_rate: declines excluded from the denominator ---
    records = [
        {"grounded_check": {"grounded": True}},
        {"grounded_check": {"grounded": False}},
        {"grounded_check": {"grounded": None}},  # declined — excluded
    ]
    assert metrics.grounded_rate(records) == 0.5  # 1 grounded / 2 scored
    print("test_grounded_rate_excludes_declines: PASS")

    # --- failure_cases: sorts by correctness_score (declines included --
    # a wrongly-declined answer must still surface as a failure, which
    # sorting by grounded_check alone would miss entirely since declines
    # have grounded=None) ---
    fail_records = [
        {
            "id": "q1",
            "input": "x",
            "answer": "a",
            "expected": "e",
            "metadata": {"route": "RAG_ONLY"},
            "actual_route": "GRAPH_ONLY",
            "grounded_check": {
                "grounded": False,
                "semantic_score": 0.2,
                "reason": "bad",
            },
            "correctness_check": {
                "correct": False,
                "correctness_score": 0.1,
                "reason": "bad",
            },
        }
    ]
    cases = metrics.failure_cases(fail_records)
    assert len(cases) == 1 and cases[0]["correctness_score"] == 0.1
    assert cases[0]["semantic_score"] == 0.2
    assert "llm_score" not in cases[0]
    print("test_failure_cases_uses_correctness_score: PASS")

    # --- check_correctness / correctness_rate ---
    # NOTE: semantic_correctness_score() does a LOCAL import of embed_query
    # inside its own function body (distinct from the module-level import
    # check_grounded's code path uses) -- so it must be patched at its
    # source (app.ingestion.embedder.embed_query), not via metrics.embed_query.
    # Using two DIFFERENT texts with deliberately different patched vectors,
    # not identical strings -- identical strings would pass this test even
    # if the patch target were wrong, since cosine(x, x) == 1.0 regardless.
    def _fake_embed_query(text):
        return [1.0, 0.0] if "matching" in text else [0.0, 1.0]

    with patch("app.ingestion.embedder.embed_query", _fake_embed_query):
        result = metrics.check_correctness("matching answer", "matching expected")
        assert result["correct"] is True
        assert result["correctness_score"] == 1.0

        result2 = metrics.check_correctness("matching answer", "totally different")
        assert result2["correct"] is False
        assert result2["correctness_score"] == 0.0
    print("test_check_correctness_identical_vs_different_vectors: PASS")

    correctness_records = [
        {"correctness_check": {"correct": True}},
        {"correctness_check": {"correct": False}},
    ]
    assert metrics.correctness_rate(correctness_records) == 0.5
    print("test_correctness_rate: PASS")

    print("\nALL METRICS TESTS PASS")


if __name__ == "__main__":
    _run_all()
