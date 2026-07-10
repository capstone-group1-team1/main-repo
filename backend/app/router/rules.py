"""
rules.py — the deterministic first-stage route classifier.

Three cue groups score the question; the route with the top score wins and
`margin` (top - runner-up) tells the orchestrator whether the rules were
confident.  ~0 ms, free, and every decision is explainable via fired_cues —
which is exactly why rules run BEFORE any LLM on this per-query hot path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

GRAPH_CUES = [
    "depend", "depends on", "connected", "connect to", "controls",
    "controlled by", "which devices", "what devices", "installed",
    "replaced", "replacement", "history", "incident history", "incidents for",
    "in the meeting room", "in the office", "in the server room",
    "in reception", "last year", "this year", "when was", "list all",
    "relationship", "topology", "uses", "warranty", "serial",
]
RAG_CUES = [
    "how do i", "how to", "how can i", "steps", "step by step", "procedure",
    "configure", "configuration", "set up", "setup", "install ", "update",
    "upgrade", "firmware", "factory reset", "reset", "pair", "pairing",
    "calibrate", "adjust", "enable", "disable", "change the", "guide",
    "instructions", "manual say",
]
HYBRID_CUES = [
    "no signal", "offline", "not working", "doesn't work", "does not work",
    "won't", "wont", "not responding", "no audio", "no video", "no sound",
    "why is", "why does", "keeps", "drops", "dropping", "lagging", "lag",
    "slow", "fail", "failing", "fails", "broken", "problem with", "issue",
    "error", "cannot", "can't", "diagnos", "troubleshoot", "flickering",
    "black screen", "blank screen", "disconnect",
]
_ERROR_CODE = re.compile(r"\b[A-Z]?\d{2,4}\b.*error|\berror\b.*\b\d+", re.I)


@dataclass
class RuleResult:
    route: str
    score: float
    margin: float
    fired_cues: list[str] = field(default_factory=list)


def classify(question: str) -> RuleResult:
    q = question.lower()
    fired: dict[str, list[str]] = {"GRAPH_ONLY": [], "RAG_ONLY": [], "HYBRID": []}
    for cue in GRAPH_CUES:
        if cue in q:
            fired["GRAPH_ONLY"].append(cue)
    for cue in RAG_CUES:
        if cue in q:
            fired["RAG_ONLY"].append(cue)
    for cue in HYBRID_CUES:
        if cue in q:
            fired["HYBRID"].append(cue)
    if _ERROR_CODE.search(question):
        fired["HYBRID"].append("error-code-pattern")

    # Symptom cues dominate: a fault question mentioning a room is still HYBRID.
    scores = {
        "HYBRID": 1.0 * len(fired["HYBRID"]),
        "RAG_ONLY": 0.9 * len(fired["RAG_ONLY"]),
        "GRAPH_ONLY": 0.8 * len(fired["GRAPH_ONLY"]),
    }
    if fired["HYBRID"]:
        scores["GRAPH_ONLY"] *= 0.3     # relational words inside a fault report
        scores["RAG_ONLY"] *= 0.3

    ordered = sorted(scores.items(), key=lambda kv: -kv[1])
    (top_route, top), (_, second) = ordered[0], ordered[1]
    total = sum(scores.values()) or 1.0
    return RuleResult(route=top_route, score=top / total,
                      margin=(top - second) / total,
                      fired_cues=fired[top_route])
