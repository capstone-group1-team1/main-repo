"""
confidence.py — EXACTLY three confidence signals.  Nothing else.

  Retrieval Confidence : shape of the vector-similarity distribution —
                         a strong top hit with a clear gap over the rest is
                         decisive; several close mediocre scores are not.
  Graph Confidence     : did we exactly match the asked-about entity, how
                         short are the paths, did we find facts at all.
  Final Confidence     : the ONE user-facing score, weighted by the route
                         (GRAPH_ONLY -> graph only; RAG_ONLY -> retrieval
                         only; HYBRID -> blend MINUS a disagreement penalty),
                         then post-rules that make honesty structural:
                           * zero citations  -> capped at 0.25
                           * unsourced spans -> deducted proportionally

Router Confidence is NOT here — it is internal-only (core/logging.py).
"""

from __future__ import annotations

from app.models.schemas import Confidence, GraphSignals, RetrievalSignals, Route

# UI thresholds (shared vocabulary with the frontend badge):
LOW_THRESHOLD = 0.40      # below -> red + "needs technician review"
HIGH_THRESHOLD = 0.75     # above -> green

# bge-large cosine similarities in practice live roughly in [0.35, 0.75];
# rescale so the score is discriminative rather than always "medium".
_SIM_FLOOR, _SIM_CEIL = 0.35, 0.75


def _rescale(sim: float) -> float:
    return max(0.0, min(1.0, (sim - _SIM_FLOOR) / (_SIM_CEIL - _SIM_FLOOR)))


def retrieval_confidence(sig: RetrievalSignals) -> float:
    if not sig.scores:
        return 0.0
    top = _rescale(sig.scores[0])
    rest = sig.scores[1:5]
    gap = (sig.scores[0] - (sum(rest) / len(rest))) if rest else 0.15
    gap = max(0.0, min(1.0, gap / 0.15))       # 0.15 raw gap == fully decisive
    return round(min(1.0, 0.65 * top + 0.35 * gap), 3)


def graph_confidence(sig: GraphSignals) -> float:
    if sig.fact_count == 0:
        return 0.0
    conf = 1.0
    if not sig.any_exact_entity_match:
        conf *= 0.35                            # only loosely related context
    conf *= 0.85 ** max(0, sig.min_hop_count - 1)   # path-length decay
    conf *= min(1.0, sig.fact_count / 3)        # 3+ facts = full support
    return round(max(0.05, min(1.0, conf)), 3)


def final_confidence(route: Route, r_conf: float | None, g_conf: float | None,
                     citation_count: int, unsourced_count: int,
                     sentence_count: int) -> Confidence:
    if route == "GRAPH_ONLY":
        base = g_conf or 0.0
        r_out, g_out = None, g_conf
    elif route == "RAG_ONLY":
        base = r_conf or 0.0
        r_out, g_out = r_conf, None
    else:  # HYBRID — blend, then punish sharp disagreement between signals
        r, g = r_conf or 0.0, g_conf or 0.0
        base = 0.5 * r + 0.5 * g - 0.25 * abs(r - g)
        r_out, g_out = r_conf, g_conf

    final = base
    if citation_count == 0:
        final = min(final, 0.25)                # a citation-free answer can
                                                # NEVER present as confident
    if sentence_count > 0:
        final -= 0.30 * (unsourced_count / sentence_count)

    final = round(max(0.0, min(1.0, final)), 3)
    level = "high" if final >= HIGH_THRESHOLD else ("low" if final < LOW_THRESHOLD else "medium")
    return Confidence(retrieval=r_out, graph=g_out, final=final, level=level)
