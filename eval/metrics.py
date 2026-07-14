"""
metrics.py — scoring functions for the evaluation harness.

PRIMARY METRIC: grounded rate — the fraction of answered questions judged
grounded, where "grounded" means the answer's embedding is similar enough to
at least one retrieved evidence chunk's embedding (semantic check only, no
LLM judge call — see the note below on why the judge was removed).

Also here: routing accuracy, calibration, the route-ablation comparison (does
a GRAPH_ONLY question actually need the graph?), the error grid, and the
/metrics parsing (p95 latency + error rate) for the fast/reliable axes.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

import numpy as np

from app.ingestion.embedder import embed_query

_MARKER = re.compile(r"\[(\d+)\]")
DECLINE_PREFIXES = (
    "the available sources do not cover",
    "i cannot answer this from the available sources",
)

SEMANTIC_GROUNDING_THRESHOLD = 0.50  # cosine similarity floor; tunable


def is_decline(answer: str) -> bool:
    a = answer.strip().lower()
    return any(a.startswith(p) for p in DECLINE_PREFIXES)


# ---------------------------------------------------------------------------
# Semantic grounding check — no LLM judge call.
#
# An earlier version of this harness combined an LLM-as-judge score with this
# semantic check. The LLM judge was removed deliberately: it doubled the LLM
# calls per held-out item (judge + generate), which was the single biggest
# contributor to eval runtime and to burning through Groq's daily quota. The
# semantic check alone answers the primary question this harness cares
# about — "is the answer actually grounded in the retrieved evidence?" — via
# a local embedding comparison (no network/LLM round-trip, no extra quota
# cost). What it does NOT verify is factual correctness against the
# `expected` reference answer beyond that grounding; the LLM judge used to
# catch a plausible-but-wrong answer that still cited real evidence text.
# That is the explicit, accepted trade-off for the large speed/cost win.
# ---------------------------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    a, b = np.array(a), np.array(b)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-9
    return float(np.dot(a, b) / denom)


def semantic_grounding_score(answer: str, evidence_texts: list[str]) -> float:
    """Max cosine similarity between the answer's embedding and any single
    evidence chunk's embedding, using the SAME bge-large model production
    uses for retrieval."""
    if not evidence_texts or not answer.strip():
        return 0.0
    answer_vec = embed_query(answer)
    # evidence chunks are documents, not queries — embed_query() applies the
    # query-only instruction prefix, which would bias this comparison, so we
    # embed evidence with the plain (no-prefix) path via embed_texts.
    from app.ingestion.embedder import embed_texts

    evidence_vecs = embed_texts(evidence_texts)
    return max(_cosine(answer_vec, v) for v in evidence_vecs)


def check_grounded(
    actual: str,
    evidence_texts: list[str],
    semantic_threshold: float = SEMANTIC_GROUNDING_THRESHOLD,
) -> dict:
    """The primary metric's per-example building block, semantic-only (no
    LLM call). grounded=True iff the answer's embedding clears the
    similarity threshold against at least one evidence chunk."""
    if is_decline(actual):
        return {
            "grounded": None,
            "semantic_score": None,
            "reason": "declined — excluded from the grounded-rate denominator",
        }
    sem_score = semantic_grounding_score(actual, evidence_texts)
    grounded = sem_score >= semantic_threshold
    return {
        "grounded": grounded,
        "semantic_score": round(sem_score, 3),
        "reason": f"semantic similarity {sem_score:.3f} vs threshold {semantic_threshold}",
    }


# grounded_rate only checks the answer against whatever EVIDENCE it was
# given -- it can't tell "cited real evidence but drew the wrong
# conclusion" from "cited real evidence and answered correctly". It also
# can't catch a decline that should have been a real answer, since declines
# are excluded from grounded_rate's denominator entirely. check_correctness()
# closes that gap cheaply: it compares the answer directly against
# `expected` (the reference answer), which every heldout.jsonl item already
# carries but which nothing previously scored against. Still no LLM call --
# just a second embedding comparison, this time against the gold answer
# instead of the retrieved evidence.
CORRECTNESS_THRESHOLD = 0.60  # cosine similarity floor; tunable, same idea as grounding


def semantic_correctness_score(answer: str, expected: str) -> float:
    """Cosine similarity between the answer's embedding and the expected
    (gold reference) answer's embedding. Deliberately does NOT special-case
    declines: if both answer and expected are declines, their embeddings
    are naturally close (shared boilerplate phrasing) and correctly score
    as matching; if the model declines but expected was a real answer (or
    vice versa), the embeddings are naturally far apart and correctly score
    as not matching -- no extra branching needed to get that right."""
    if not expected or not expected.strip():
        return 0.0
    from app.ingestion.embedder import embed_query

    answer_vec = embed_query(answer)
    expected_vec = embed_query(expected)
    return round(_cosine(answer_vec, expected_vec), 3)


def check_correctness(
    actual: str, expected: str, threshold: float = CORRECTNESS_THRESHOLD
) -> dict:
    """Per-example correctness check against the gold reference answer.
    Unlike check_grounded(), this is never excluded for declines -- a
    decline that SHOULD have answered is exactly the failure mode this is
    meant to catch, so it must still be scored, not skipped."""
    score = semantic_correctness_score(actual, expected)
    correct = score >= threshold
    return {
        "correct": correct,
        "correctness_score": score,
        "reason": f"answer-vs-expected similarity {score:.3f} vs threshold {threshold}",
    }


def correctness_rate(records: list[dict]) -> float:
    """fraction of ALL records (declines included -- see check_correctness's
    docstring) whose answer semantically matches the expected reference."""
    if not records:
        return 0.0
    correct = sum(1 for r in records if r["correctness_check"]["correct"])
    return round(correct / len(records), 3)


def grounded_rate(records: list[dict]) -> float:
    """grounded / answered. Declines (grounded is None) are excluded from
    the denominator — a correct 'I don't know' should neither help nor hurt."""
    scored = [r for r in records if r["grounded_check"]["grounded"] is not None]
    if not scored:
        return 0.0
    grounded = sum(1 for r in scored if r["grounded_check"]["grounded"])
    return round(grounded / len(scored), 3)


# ---------------------------------------------------------------------------
# Secondary metrics
# ---------------------------------------------------------------------------


def routing_accuracy(records: list[dict]) -> float:
    if not records:
        return 0.0
    correct = sum(1 for r in records if r["metadata"]["route"] == r["actual_route"])
    return round(correct / len(records), 3)


def calibration_buckets(records: list[dict]) -> list[dict]:
    bands = [(0.0, 0.4, "low"), (0.4, 0.75, "medium"), (0.75, 1.01, "high")]
    out = []
    for lo, hi, name in bands:
        subset = [r for r in records if lo <= r["final_confidence"] < hi]
        if subset:
            mean = sum(
                1.0 if r["grounded_check"]["grounded"] else 0.0
                for r in subset
                if r["grounded_check"]["grounded"] is not None
            ) / max(
                1, sum(1 for r in subset if r["grounded_check"]["grounded"] is not None)
            )
            out.append(
                {
                    "band": name,
                    "range": f"[{lo},{hi})",
                    "n": len(subset),
                    "mean_grounded": round(mean, 3),
                }
            )
        else:
            out.append(
                {"band": name, "range": f"[{lo},{hi})", "n": 0, "mean_grounded": None}
            )
    return out


def is_monotonic(buckets: list[dict]) -> bool:
    means = [b["mean_grounded"] for b in buckets if b["mean_grounded"] is not None]
    return all(a <= b for a, b in zip(means, means[1:]))


# ---------------------------------------------------------------------------
# Route ablation — "does this GRAPH_ONLY question actually need the graph?"
# ---------------------------------------------------------------------------


def route_ablation_table(ablation_records: list[dict]) -> dict:
    """ablation_records: one row per (question, forced_route) pair, each with
    a grounded_check AND a correctness_check. Groups by forced_route and
    reports BOTH rates, so GRAPH_ONLY questions' natural route can be
    compared against what RAG-only and HYBRID would have produced for the
    SAME questions.

    Reporting grounded_rate alone here is actively misleading: a route that
    retrieves the wrong evidence can still cite it fluently and score as
    "grounded" while answering a completely different question than the one
    asked. correctness_rate (semantic match against the gold `expected`
    answer) is what actually tells you whether forcing a route through the
    wrong evidence source produced a right or wrong answer."""
    by_route: dict[str, list[dict]] = defaultdict(list)
    for r in ablation_records:
        by_route[r["forced_route"]].append(r)
    table = {}
    for forced_route, rows in by_route.items():
        table[forced_route] = {
            "n": len(rows),
            "grounded_rate": grounded_rate(
                [{"grounded_check": r["grounded_check"]} for r in rows]
            ),
            "correctness_rate": correctness_rate(
                [{"correctness_check": r["correctness_check"]} for r in rows]
            ),
        }
    return table


# ---------------------------------------------------------------------------
# Error analysis — grid across >=2 metadata dimensions (Module 12 R5)
# ---------------------------------------------------------------------------


def error_grid(records: list[dict], dim1: str, dim2: str) -> dict:
    grid: dict = defaultdict(lambda: {"correct": 0, "wrong": 0, "declined": 0})
    for r in records:
        key = (r["metadata"].get(dim1, "unknown"), r["metadata"].get(dim2, "unknown"))
        g = r["grounded_check"]["grounded"]
        if g is None:
            grid[key]["declined"] += 1
        elif g:
            grid[key]["correct"] += 1
        else:
            grid[key]["wrong"] += 1
    out = {}
    for key, c in grid.items():
        scored = c["correct"] + c["wrong"]
        out[f"{key[0]} × {key[1]}"] = {
            **c,
            "error_rate": round(c["wrong"] / scored, 3) if scored else 0.0,
        }
    return out


def failure_cases(records: list[dict], limit: int = 5) -> list[dict]:
    """Surfaces the worst-scoring failures by correctness (not grounding
    alone). This matters specifically for declines: a wrongly-declined
    answer has grounded=None (excluded from grounded_check entirely, since
    grounded_rate treats declines as neither help nor hurt) -- so sorting by
    grounded_check alone, as this function used to, silently missed every
    case of "the system should have answered but gave up instead". Sorting
    by correctness_check catches that failure mode too, since
    check_correctness() never excludes declines."""
    fails = [r for r in records if not r["correctness_check"]["correct"]]
    fails.sort(key=lambda r: r["correctness_check"]["correctness_score"])
    return [
        {
            "id": r["id"],
            "input": r["input"],
            "predicted": r["answer"][:200],
            "expected": r["expected"][:200],
            "route_expected": r["metadata"]["route"],
            "route_actual": r["actual_route"],
            "grounded": r["grounded_check"]["grounded"],
            "semantic_score": r["grounded_check"]["semantic_score"],
            "correctness_score": r["correctness_check"]["correctness_score"],
            "why": r["correctness_check"]["reason"],
        }
        for r in fails[:limit]
    ]


# ---------------------------------------------------------------------------
# /metrics parsing — the "fast" and "reliable" axes (Module 11 §10)
# ---------------------------------------------------------------------------


def parse_metrics(metrics_text: str) -> list:
    from prometheus_client.parser import text_string_to_metric_families

    return list(text_string_to_metric_families(metrics_text))


def error_rate(families: list, path: str) -> float:
    errors = total = 0.0
    for fam in families:
        if fam.name != "requests":
            continue
        for s in fam.samples:
            if s.name == "requests_total" and s.labels.get("path") == path:
                total += s.value
                if s.labels.get("status", "").startswith("5"):
                    errors += s.value
    return round(errors / total, 3) if total else 0.0


def p95_latency(families: list, path: str) -> float:
    buckets, total = [], 0.0
    for fam in families:
        if fam.name != "request_latency_seconds":
            continue
        for s in fam.samples:
            if s.labels.get("path") != path:
                continue
            if s.name.endswith("_bucket"):
                le = s.labels["le"]
                le = float("inf") if le == "+Inf" else float(le)
                buckets.append((le, s.value))
            elif s.name.endswith("_count"):
                total = s.value
    if not total:
        return 0.0
    buckets.sort()
    target = 0.95 * total
    prev_le = prev_count = 0.0
    for le, count in buckets:
        if count >= target:
            if le == float("inf") or count == prev_count:
                return le
            frac = (target - prev_count) / (count - prev_count)
            return round(prev_le + frac * (le - prev_le), 3)
        prev_le, prev_count = le, count
    return 0.0
