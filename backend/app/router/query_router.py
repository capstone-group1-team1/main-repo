"""
query_router.py — THE Query Router.  An explicit, testable module (not a
prompt trick):

    question -> entity match -> rules -> (LLM fallback if rules unsure)
             -> RouteDecision  in {GRAPH_ONLY, RAG_ONLY, HYBRID}

Uncertainty defaults to HYBRID: its evidence is a superset of either single
route, so a wrong default costs only latency/tokens — it can never miss the
evidence the answer needs, and any residual mistake is caught by the
confidence safety net (edge case 5).

Every decision (route + the router's OWN confidence + mechanism) goes to the
internal log only.  Router confidence is never exposed to users.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.logging import get_logger, log_router_decision
from app.router import llm_fallback, rules
from app.router.entity_matcher import MatchedEntity, match

log = get_logger(__name__)

# Back-compat defaults (the live values come from Settings; see config.py).
RULE_MARGIN_THRESHOLD = 0.25
FALLBACK_CONF_THRESHOLD = 0.60


@dataclass
class RouteDecision:
    route: str
    router_confidence: float                 # INTERNAL ONLY — never in API
    entities: list[MatchedEntity] = field(default_factory=list)
    mechanism: str = "rules"                 # rules | llm_fallback | default_hybrid


def route(question: str) -> RouteDecision:
    from app.core.config import get_settings
    settings = get_settings()
    entities = match(question)
    result = rules.classify(question)

    if result.score > 0 and result.margin >= settings.router_rule_margin_threshold:
        decision = RouteDecision(result.route, min(1.0, 0.5 + result.margin),
                                 entities, "rules")
    else:
        try:
            fb_route, fb_conf = llm_fallback.classify(question)
            if fb_conf >= settings.router_fallback_conf_threshold:
                decision = RouteDecision(fb_route, fb_conf, entities, "llm_fallback")
            else:
                decision = RouteDecision("HYBRID", fb_conf, entities, "default_hybrid")
        except llm_fallback.FallbackUnavailable as exc:
            log.warning("Router fallback unavailable (%s) — defaulting HYBRID", exc)
            decision = RouteDecision("HYBRID", 0.3, entities, "default_hybrid")

    log_router_decision(question, decision.route, decision.router_confidence,
                        [e.canonical_id for e in decision.entities],
                        decision.mechanism)
    return decision
