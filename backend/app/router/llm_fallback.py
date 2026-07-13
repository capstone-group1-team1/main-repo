"""
llm_fallback.py — one shared LLM gateway classification call, used ONLY when the
rule engine is not confident.  Ambiguous phrasings ("AirMedia acting weird
again?") defeat cue lists; a single JSON-mode call resolves them without
paying LLM latency/cost on every query.
"""

from __future__ import annotations


from tenacity import retry, stop_after_attempt, wait_exponential

from app.synthesis.groq_client import generate_json
from app.synthesis.sanitize import scrub

_PROMPT = """Classify this smart-office question into exactly one route.

Routes:
- GRAPH_ONLY: structural/relational/historical questions about devices,
  rooms, dependencies, installations, replacements, or incident history
  listings. Example: "What devices depend on the CP4?"
- RAG_ONLY: procedural how-to questions answerable from a device manual.
  Example: "How do I factory reset the AirMedia receiver?"
- HYBRID: fault diagnosis needing both the dependency chain and
  troubleshooting text. Example: "The display has no signal."

Question: "{question}"

Return ONLY JSON: {{"route": "GRAPH_ONLY|RAG_ONLY|HYBRID", "confidence": 0.0-1.0}}"""


class FallbackUnavailable(Exception):
    pass


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5),
       reraise=True)
def _call(question: str) -> dict:
    return generate_json(
        system="",
        user=_PROMPT.format(question=scrub(question)),
        temperature=0.0,
    )


def classify(question: str) -> tuple[str, float]:
    """-> (route, confidence).  Raises FallbackUnavailable on any failure —
    the orchestrator converts that into the safe HYBRID default."""
    try:
        data = _call(question)
        route = data.get("route", "")
        conf = float(data.get("confidence", 0.0))
        if route not in ("GRAPH_ONLY", "RAG_ONLY", "HYBRID"):
            raise ValueError(f"bad route {route!r}")
        return route, max(0.0, min(1.0, conf))
    except Exception as exc:
        raise FallbackUnavailable(str(exc)) from exc
