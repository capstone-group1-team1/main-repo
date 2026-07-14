"""
run_eval.py — the evaluation harness (Module 12).

PRIMARY METRIC: grounded rate. Declared here, in one sentence:
    "The fraction of answered questions whose answer is semantically similar
    enough to the retrieved evidence it cites (embedding comparison, no LLM
    judge call)."

BASELINE (R2): the plain BM25-only retrieval stage from the ladder below,
paired with a router-less, rerank-less answer (no graph, no hybrid merge,
no cross-encoder) — the literature-standard "keyword retrieval + direct
answer" baseline the Module 12 guide names explicitly, compared against the
full system's grounded rate.

RETRIEVAL LADDER (supporting analysis, not the primary metric): BM25 ->
dense -> hybrid -> hybrid+reranker, each scored by Recall@k against a gold
manual/incident document per held-out item, showing what each stage in the
production retrieval pipeline actually buys.

ROUTE ABLATION (R5 error analysis): every GRAPH_ONLY-tagged question is ALSO
force-run through RAG_ONLY and HYBRID (bypassing the router), so the report
shows whether those questions genuinely need the graph or would have been
answered fine by RAG alone.

STOCHASTIC HANDLING (R4): the LLM generation step is stochastic, so the
end-to-end grounded-rate run executes 3 seeded times and reports mean ±
stddev. Retrieval (the baseline ladder, Recall@k) is deterministic and runs
once.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import metrics
import retrieval_baselines

HERE = Path(__file__).resolve().parent
REPORTS = HERE / "reports"
REPORTS.mkdir(exist_ok=True)

PRIMARY_METRIC = (
    "grounded rate — the fraction of answered questions whose answer is "
    "semantically similar enough to the retrieved evidence it cites "
    "(embedding comparison, no LLM judge call)"
)


def set_all_seeds(seed: int) -> None:
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except Exception:
        pass


def load_heldout(subset: str | None) -> list[dict]:
    items = [
        json.loads(l)
        for l in (HERE / "heldout.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    if subset != "smoke":
        return items
    # A naive items[:8] would grab only the file's first 8 rows — which,
    # given heldout.jsonl is grouped by route, means all-GRAPH_ONLY. That's
    # both unrepresentative AND accidentally the most expensive subset to run
    # (every GRAPH_ONLY item triggers 3x more LLM calls via route ablation).
    # Sample 2 items per route instead, so "smoke" is actually representative
    # and actually cheap.
    by_route: dict[str, list[dict]] = {}
    for it in items:
        by_route.setdefault(it["metadata"]["route"], []).append(it)
    smoke = []
    for route_items in by_route.values():
        smoke.extend(route_items[:2])
    return smoke


# ---------------------------------------------------------------------------
# End-to-end system run (one held-out item -> one scored record)
# ---------------------------------------------------------------------------


def _evidence_texts(evidence: list) -> list[str]:
    from app.models.schemas import GraphFact, RetrievedChunk

    out = []
    for item in evidence:
        if isinstance(item, RetrievedChunk):
            out.append(item.text)
        elif isinstance(item, GraphFact):
            out.append(item.text)
    return out


def run_system(item: dict) -> dict:
    """Natural routing — exactly what /chat does, called in-process (no HTTP
    hop) via the same helpers routes_chat.py uses."""
    import time

    from app.api.routes_chat import _finalize, _get_evidence
    from app.core.config import get_settings
    from app.retrieval import reranker
    from app.router.query_router import route as route_question
    from app.synthesis.groq_client import LLMUnavailable, generate
    from app.synthesis.prompts import SYSTEM_PROMPT, build_user_prompt

    settings = get_settings()
    decision = route_question(item["input"])
    evidence, r_sig, g_sig = _get_evidence(item["input"], decision)
    evidence = reranker.rerank(item["input"], evidence, top_n=settings.max_evidence)

    if evidence:
        try:
            raw_answer = generate(
                SYSTEM_PROMPT, build_user_prompt(item["input"], evidence)
            )
        except LLMUnavailable as exc:
            raw_answer = f"[LLM unavailable: {exc}]"
    else:
        raw_answer = (
            "The available sources do not cover this question. "
            "Please check the device manuals or contact a technician."
        )
    time.sleep(settings.extraction_call_delay_seconds)  # pace between LLM-calling steps

    response = _finalize(raw_answer, evidence, decision, r_sig, g_sig)
    ev_texts = _evidence_texts(evidence)
    grounded_check = metrics.check_grounded(response.answer, ev_texts)
    correctness_check = metrics.check_correctness(response.answer, item["expected"])
    return {
        "id": item["id"],
        "input": item["input"],
        "expected": item["expected"],
        "metadata": item["metadata"],
        "actual_route": response.route,
        "answer": response.answer,
        "final_confidence": response.confidence.final,
        "grounded_check": grounded_check,
        "correctness_check": correctness_check,
    }


# ---------------------------------------------------------------------------
# Route ablation: force GRAPH_ONLY-tagged questions through every route
# ---------------------------------------------------------------------------


def run_route_ablation(graph_only_items: list[dict]) -> list[dict]:
    import time

    from app.api.routes_chat import _finalize, _get_evidence
    from app.core.config import get_settings
    from app.retrieval import reranker
    from app.router.entity_matcher import match as match_entities
    from app.router.query_router import RouteDecision
    from app.synthesis.groq_client import LLMUnavailable, generate
    from app.synthesis.prompts import SYSTEM_PROMPT, build_user_prompt

    delay = get_settings().extraction_call_delay_seconds  # reuse the same
    # provider-pacing knob as ingestion — same reasoning: one request per
    # forced route with no gap trips the per-minute rate limit fast.
    rows = []
    for item in graph_only_items:
        entities = match_entities(item["input"])
        for forced_route in ("GRAPH_ONLY", "RAG_ONLY", "HYBRID"):
            decision = RouteDecision(
                route=forced_route,
                router_confidence=1.0,
                entities=entities,
                mechanism="eval_forced",
            )
            evidence, r_sig, g_sig = _get_evidence(item["input"], decision)
            evidence = reranker.rerank(
                item["input"], evidence, top_n=get_settings().max_evidence
            )
            if evidence:
                try:
                    raw_answer = generate(
                        SYSTEM_PROMPT, build_user_prompt(item["input"], evidence)
                    )
                except LLMUnavailable as exc:
                    raw_answer = f"[LLM unavailable: {exc}]"
            else:
                raw_answer = (
                    "The available sources do not cover this question. "
                    "Please check the device manuals or contact a technician."
                )
            response = _finalize(raw_answer, evidence, decision, r_sig, g_sig)
            ev_texts = _evidence_texts(evidence)
            grounded_check = metrics.check_grounded(response.answer, ev_texts)
            correctness_check = metrics.check_correctness(
                response.answer, item["expected"]
            )
            time.sleep(delay)  # pace before the next forced-route iteration
            rows.append(
                {
                    "id": item["id"],
                    "forced_route": forced_route,
                    "answer": response.answer,
                    "grounded_check": grounded_check,
                    "correctness_check": correctness_check,
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Baseline (R2): BM25-only retrieval + a router-less, rerank-less answer
# ---------------------------------------------------------------------------


def measure_service_health(base_url: str, items: list[dict], n: int = 5) -> dict:
    """The 'fast' and 'reliable' axes (Module 11 §15): fire a SMALL number of
    REAL HTTP requests at the running API's /chat endpoint — the main eval
    above calls the pipeline in-process for speed/determinism, which never
    touches the API's middleware, so /metrics would otherwise show zero
    traffic. This step exists specifically to exercise the live service and
    then read its own instrumentation back, proving the deployed service is
    actually observable (not just that the eval script can time Python
    calls itself)."""
    sample = items[:n]
    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            for item in sample:
                try:
                    client.post(
                        f"{base_url}/chat",
                        json={"question": item["input"]},
                        headers={"X-Mock-User-Id": "u-ali"},
                    )
                except Exception as exc:
                    print(
                        f"  health-check request failed (counted toward "
                        f"error rate): {exc}"
                    )
            resp = client.get(f"{base_url}/metrics", timeout=10.0)
            resp.raise_for_status()
            families = metrics.parse_metrics(resp.text)
    except Exception as exc:
        print(
            f"Could not reach {base_url} for the fast/reliable axes ({exc}) "
            f"— is the API running? Skipping. Use --skip-health to silence this."
        )
        return {
            "p95_latency_chat_s": None,
            "error_rate_chat": None,
            "note": f"unreachable: {exc}",
        }

    return {
        "p95_latency_chat_s": metrics.p95_latency(families, "/chat"),
        "error_rate_chat": metrics.error_rate(families, "/chat"),
        "sampled_requests": len(sample),
    }


def _run_retrieval_baseline(rag_items: list[dict], search_fn) -> float:
    """Shared runner for any single-stage retrieval baseline: retrieve with
    `search_fn`, synthesize a direct answer (no router, no graph, no
    reranker — a naive baseline is naive on every axis, not just retrieval),
    score it against the same check_grounded metric as the full system.

    Scoring uses the same convention as grounded_rate(): a decline
    (grounded=None) is EXCLUDED from the denominator, not counted as a
    failure. This matters — without it, a baseline that correctly declines
    an unanswerable question would be punished as "wrong" while the full
    system's identical correct decline is excluded from its own grounded_rate
    denominator, silently inflating the full system's apparent advantage
    over the baselines beyond what the underlying behavior actually earns."""
    import time

    from app.core.config import get_settings
    from app.models.schemas import RetrievedChunk
    from app.synthesis.groq_client import LLMUnavailable, generate
    from app.synthesis.prompts import SYSTEM_PROMPT, build_user_prompt

    delay = get_settings().extraction_call_delay_seconds
    checks = []
    for item in rag_items:
        raw = search_fn(item["input"], k=5)
        evidence = [
            RetrievedChunk(
                chunk_id=c["chunk_id"],
                text=c["text"],
                score=c.get("score", 0.0),
                source_type=c["source_type"],
                source_id=c["source_id"],
                document_id=c["document_id"],
                document_name=c["document_name"],
                device_id=c["device_id"],
                device_name=c["device_name"],
                section_title=c["section_title"],
                page_number=c.get("page_number"),
            )
            for c in raw
        ]
        if evidence:
            try:
                answer = generate(
                    SYSTEM_PROMPT, build_user_prompt(item["input"], evidence)
                )
            except LLMUnavailable as exc:
                answer = f"[LLM unavailable: {exc}]"
        else:
            answer = "The available sources do not cover this question."
        time.sleep(delay)
        ev_texts = [c.text for c in evidence]
        check = metrics.check_grounded(answer, ev_texts)
        time.sleep(delay)
        checks.append(check)
    return metrics.grounded_rate([{"grounded_check": c} for c in checks])


def run_bm25_baseline(rag_items: list[dict]) -> float:
    """R2 baseline 1: literature-standard keyword retrieval + a direct,
    router-less, graph-less, reranker-less answer — the Module 12 guide's
    own worked example for a RAG baseline."""
    return _run_retrieval_baseline(rag_items, retrieval_baselines.bm25_search)


def run_dense_baseline(rag_items: list[dict]) -> float:
    """R2 baseline 2 (the guide explicitly permits a second baseline "if it
    clarifies the story"): plain dense/semantic-only retrieval — no BM25, no
    graph, no reranker. This is what most "vanilla RAG" implementations
    actually do, so it's a fair, common second comparison point — distinct
    from the retrieval LADDER's dense stage, which measures Recall@k in
    isolation; this measures end-to-end grounded rate with the same naive
    single-stage-retrieval, direct-answer pipeline as the BM25 baseline."""
    return _run_retrieval_baseline(rag_items, retrieval_baselines.dense_search)


# ---------------------------------------------------------------------------
# Aggregation + reporting
# ---------------------------------------------------------------------------


def aggregate(all_seeds: list[list[dict]]) -> dict:
    def ms(xs):
        return {
            "mean": round(statistics.mean(xs), 3),
            "stddev": round(statistics.pstdev(xs), 3) if len(xs) > 1 else 0.0,
        }

    grounded = [metrics.grounded_rate(s) for s in all_seeds]
    correctness = [metrics.correctness_rate(s) for s in all_seeds]
    routing = [metrics.routing_accuracy(s) for s in all_seeds]
    seed0 = all_seeds[0]
    buckets = metrics.calibration_buckets(seed0)
    return {
        "primary_metric": PRIMARY_METRIC,
        "grounded_rate": ms(grounded),
        "correctness_rate": ms(correctness),
        "routing_accuracy": ms(routing),
        "calibration": buckets,
        "calibration_monotonic": metrics.is_monotonic(buckets),
        "error_grid_route_x_device": metrics.error_grid(seed0, "route", "device"),
        "error_grid_kind_x_scope": metrics.error_grid(seed0, "kind", "scope"),
    }


def write_failure_cases(records: list[dict]) -> None:
    cases = metrics.failure_cases(records, limit=5)
    lines = ["# Failure cases (Module 12 R5)", ""]
    if not cases:
        lines.append(
            "No failures in this run — every scored held-out item matched "
            "the gold reference answer closely enough."
        )
    for i, c in enumerate(cases, 1):
        lines += [
            f"## {i}. `{c['id']}` — {c['input']}",
            "",
            f"- **Predicted:** {c['predicted']}",
            f"- **Expected:** {c['expected']}",
            f"- **Route:** expected `{c['route_expected']}`, got `{c['route_actual']}`",
            f"- **Grounded:** {c['grounded']} (semantic score vs. evidence: {c['semantic_score']})",
            f"- **Correctness score (vs. gold answer):** {c['correctness_score']}",
            f"- **Why:** {c['why']}",
            "",
        ]
    lines += [
        "## Next-iteration hypothesis",
        "_If we had another week, we would try <specific intervention> because "
        "<specific reason from the error grid / route ablation above>._  "
        "(Fill in from this run's numbers before submitting.)",
    ]
    (HERE / "failure_cases.md").write_text("\n".join(lines), encoding="utf-8")


def write_reports(
    summary: dict,
    ladder: dict,
    ablation_table: dict,
    bm25_baseline: float,
    dense_baseline: float,
    health: dict,
    seed0: list[dict],
    tag: str,
    rag_item_ids: set,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    # The baselines only ever run on rag_items (items with a gold_document_id
    # -- RAG_ONLY and HYBRID), since a retrieval-only baseline has no graph
    # access and can't attempt GRAPH_ONLY or out_of_scope items at all. The
    # full system's grounded_rate/correctness_rate above cover all 50 items,
    # which is NOT the same population the baselines were scored against --
    # comparing them directly overstates the full system's apparent edge,
    # since it gets credit for easy out_of_scope declines and GRAPH_ONLY
    # answers the baselines were never able to attempt in the first place.
    # This is the full system's score restricted to that SAME subset, for a
    # genuine apples-to-apples comparison alongside the full-population one.
    matched_records = [r for r in seed0 if r["id"] in rag_item_ids]
    matched_grounded = metrics.grounded_rate(matched_records)
    matched_correctness = metrics.correctness_rate(matched_records)

    (REPORTS / f"eval-{tag}-{stamp}.json").write_text(
        json.dumps(
            {
                "summary": summary,
                "retrieval_ladder": ladder,
                "route_ablation": ablation_table,
                "baselines": {"bm25": bm25_baseline, "dense": dense_baseline},
                "full_system_on_baseline_population": {
                    "n": len(matched_records),
                    "grounded_rate": matched_grounded,
                    "correctness_rate": matched_correctness,
                },
                "service_health": health,
                "records": seed0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    m = summary
    md = [
        f"# Evaluation report ({tag}) — {stamp}",
        "",
        f"**Primary metric:** {m['primary_metric']}",
        "",
    ]

    md += [
        "## Three axes of service health (Module 11 §15)",
        "",
        "| Axis | Metric | Value |",
        "|---|---|---|",
        f"| Correct | grounded rate | {m['grounded_rate']['mean']} ± {m['grounded_rate']['stddev']} |",
        f"| Correct | correctness rate (vs. gold answer) | {m['correctness_rate']['mean']} ± {m['correctness_rate']['stddev']} |",
        f"| Fast | p95 latency /chat | {health.get('p95_latency_chat_s', 'n/a')} s |",
        f"| Reliable | error rate /chat | {health.get('error_rate_chat', 'n/a')} |",
        "",
    ]
    if health.get("note"):
        md.append(f"_Fast/reliable axes unavailable this run: {health['note']}_\n")

    md += [
        "## Baseline comparison (Module 12 R2 — two baselines, as permitted)",
        "",
        f"_Scored on the same {len(matched_records)}-item population as the "
        f"baselines (RAG_ONLY + HYBRID items only) — NOT the full 50-item "
        f"set, so this is a genuine apples-to-apples comparison. The full "
        f"system's true full-population numbers are in the axes table above._",
        "",
        "| System | Grounded rate | Correctness rate |",
        "|---|---|---|",
        f"| Baseline 1: BM25-only retrieval + direct answer | {bm25_baseline} | n/a |",
        f"| Baseline 2: dense-only retrieval + direct answer | {dense_baseline} | n/a |",
        f"| **Full system**, same population (router + hybrid + graph) | "
        f"**{matched_grounded}** | **{matched_correctness}** |",
        "",
    ]

    md += [
        "## Retrieval baseline ladder — Recall@{}".format(ladder.get("k", 5)),
        "",
        "| Stage | Recall@k | MRR | n |",
        "|---|---|---|---|",
    ]
    for stage in retrieval_baselines.STAGES:
        s = ladder["summary"].get(stage, {"recall_at_k": None, "mrr": None, "n": 0})
        md.append(f"| {stage} | {s['recall_at_k']} | {s['mrr']} | {s['n']} |")
    md.append("")

    md += [
        "## Route ablation — GRAPH_ONLY questions forced through every route",
        "",
        "| Forced route | n | Grounded rate | Correctness rate (vs. gold answer) |",
        "|---|---|---|---|",
    ]
    for r in ("GRAPH_ONLY", "RAG_ONLY", "HYBRID"):
        row = ablation_table.get(
            r, {"n": 0, "grounded_rate": None, "correctness_rate": None}
        )
        md.append(
            f"| {r} | {row['n']} | {row['grounded_rate']} | {row['correctness_rate']} |"
        )
    md.append("")

    md += [
        "## Routing accuracy",
        "",
        f"{m['routing_accuracy']['mean']} ± {m['routing_accuracy']['stddev']}",
        "",
    ]

    md += [
        "## Calibration (grounded rate should rise with confidence)",
        "",
        "| band | range | n | mean grounded |",
        "|---|---|---|---|",
    ]
    for b in m["calibration"]:
        md.append(f"| {b['band']} | {b['range']} | {b['n']} | {b['mean_grounded']} |")
    md.append(f"\nMonotonic: **{m['calibration_monotonic']}**\n")

    md += [
        "## Error grid — route × device",
        "",
        "| cell | correct | wrong | declined | error rate |",
        "|---|---|---|---|---|",
    ]
    for cell, c in sorted(m["error_grid_route_x_device"].items()):
        md.append(
            f"| {cell} | {c['correct']} | {c['wrong']} | {c['declined']} | {c['error_rate']} |"
        )

    md += [
        "",
        "## Error grid — kind × scope",
        "",
        "| cell | correct | wrong | declined | error rate |",
        "|---|---|---|---|---|",
    ]
    for cell, c in sorted(m["error_grid_kind_x_scope"].items()):
        md.append(
            f"| {cell} | {c['correct']} | {c['wrong']} | {c['declined']} | {c['error_rate']} |"
        )

    md += [
        "",
        "See `eval/failure_cases.md` for 5 documented failures + the "
        "next-iteration hypothesis.",
    ]
    path = REPORTS / f"eval-{tag}-{stamp}.md"
    path.write_text("\n".join(md), encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", choices=["smoke"], default=None)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument(
        "--skip-ladder",
        action="store_true",
        help="skip the retrieval baseline ladder (still runs the main eval)",
    )
    ap.add_argument(
        "--skip-ablation",
        action="store_true",
        help="skip the GRAPH_ONLY route-ablation comparison",
    )
    ap.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="running API base URL, used only to measure the "
        "fast/reliable axes (a handful of real HTTP calls "
        "to populate /metrics, then read it back)",
    )
    ap.add_argument(
        "--skip-health",
        action="store_true",
        help="skip the fast/reliable axes (no HTTP calls to the "
        "running API at all — pure in-process eval)",
    )
    args = ap.parse_args()

    items = load_heldout(args.subset)
    tag = "smoke" if args.subset else "full"
    seeds = [42, 1337, 2024][: args.seeds]
    print(f"Primary metric: {PRIMARY_METRIC}")
    print(f"Running {len(items)} items x {len(seeds)} seed(s)")

    import time
    from app.core.config import get_settings as _get_settings

    pacing_delay = _get_settings().extraction_call_delay_seconds
    print(
        f"Pacing {pacing_delay}s between LLM-calling steps to respect provider rate limits."
    )

    all_seeds = []
    for seed in seeds:
        set_all_seeds(seed)
        print(f"  seed {seed}...")
        seed_records = []
        for it in items:
            seed_records.append(run_system(it))
            time.sleep(pacing_delay)  # pace the generate() call per item
        all_seeds.append(seed_records)

    rag_items = [it for it in items if it["metadata"].get("gold_document_id")]
    graph_items = [it for it in items if it["metadata"]["route"] == "GRAPH_ONLY"]

    ladder = {"k": 5, "summary": {}, "per_item": {}}
    if not args.skip_ladder:
        print(
            "Running retrieval baseline ladder (BM25 -> dense -> hybrid -> hybrid+rerank)..."
        )
        ladder = retrieval_baselines.run_ladder(rag_items, k=5)

    ablation_table = {}
    if not args.skip_ablation and graph_items:
        print(f"Running route ablation on {len(graph_items)} GRAPH_ONLY items...")
        ablation_records = run_route_ablation(graph_items)
        ablation_table = metrics.route_ablation_table(ablation_records)

    bm25_baseline = 0.0
    dense_baseline = 0.0
    if not args.skip_ladder and rag_items:
        print("Running Baseline 1: BM25-only (R2)...")
        bm25_baseline = run_bm25_baseline(rag_items)
        print("Running Baseline 2: dense-only (R2)...")
        dense_baseline = run_dense_baseline(rag_items)

    health = {"p95_latency_chat_s": None, "error_rate_chat": None}
    if not args.skip_health:
        print(
            f"Measuring fast/reliable axes against {args.base_url} "
            f"({min(5, len(items))} real HTTP calls to populate /metrics)..."
        )
        health = measure_service_health(args.base_url, items, n=5)

    summary = aggregate(all_seeds)
    write_failure_cases(all_seeds[0])
    rag_item_ids = {it["id"] for it in rag_items}
    md_path = write_reports(
        summary,
        ladder,
        ablation_table,
        bm25_baseline,
        dense_baseline,
        health,
        all_seeds[0],
        tag,
        rag_item_ids,
    )

    print(
        f"\nGrounded rate: {summary['grounded_rate']['mean']} ± {summary['grounded_rate']['stddev']}"
    )
    print(
        f"Correctness rate (vs. gold answer): {summary['correctness_rate']['mean']} "
        f"± {summary['correctness_rate']['stddev']}"
    )
    print(f"Routing accuracy: {summary['routing_accuracy']['mean']}")
    print(f"Fast (p95 /chat): {health.get('p95_latency_chat_s', 'n/a')} s")
    print(f"Reliable (error rate /chat): {health.get('error_rate_chat', 'n/a')}")
    print(f"Baseline 1 (BM25-only): {bm25_baseline}")
    print(f"Baseline 2 (dense-only): {dense_baseline}")
    print(f"Retrieval ladder: {ladder['summary']}")
    print(f"Route ablation: {ablation_table}")
    print(f"Report: {md_path}")
    print(f"Failures: {HERE / 'failure_cases.md'}")


if __name__ == "__main__":
    main()
