"""
citation_assembler.py — turns the LLM's [n]-marked answer into the API's
structured citations array, and detects UNSOURCED claims.

Steps:
  1. Parse [n] markers and resolve each against the evidence list the LLM saw.
  2. Dangling markers (pointing at nothing) are stripped and logged.
  3. Markers are renumbered compactly in answer order ([3],[1] -> [1],[2])
     and the answer text is rewritten to match, so the UI list aligns.
  4. Any factual-looking sentence WITHOUT a marker is collected into
     unsourced_spans — the model filled a gap from its own knowledge, which
     must lower confidence (see confidence.py) and be visibly flagged in the
     UI ("no source found for this part of the answer").

GRAPH facts cite differently by design: their snippet is the graph path
string itself (e.g. "CP4-001 —CONTROLS→ DSP-001"), so graph-derived claims
are equally traceable, never just asserted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.models.schemas import Citation, GraphFact, RetrievedChunk

log = get_logger(__name__)

_MARKER = re.compile(r"\[(\d+)\]")
# Sentences that are hedges/meta rather than factual claims:
_NON_FACTUAL = re.compile(
    r"(available sources do not|i (do not|don't) have|no information|"
    r"in summary|hope this helps)", re.I)


@dataclass
class AssembledAnswer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    unsourced_spans: list[str] = field(default_factory=list)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def assemble(answer_text: str,
             evidence: list[GraphFact | RetrievedChunk]) -> AssembledAnswer:
    # ---- 1+2: resolve markers, drop dangling ones ---------------------------
    used_order: list[int] = []           # original evidence numbers, in order
    for m in _MARKER.finditer(answer_text):
        n = int(m.group(1))
        if 1 <= n <= len(evidence):
            if n not in used_order:
                used_order.append(n)
        else:
            log.warning("Dangling citation marker [%d] stripped", n)

    renumber = {old: new for new, old in enumerate(used_order, start=1)}

    def _rewrite(match: re.Match) -> str:
        old = int(match.group(1))
        return f"[{renumber[old]}]" if old in renumber else ""

    new_text = _MARKER.sub(_rewrite, answer_text).strip()
    new_text = re.sub(r"  +", " ", new_text)

    # ---- 3: build the citations array ---------------------------------------
    sentences = _split_sentences(new_text)

    def _sentence_for(marker: int) -> str:
        tag = f"[{marker}]"
        for s in sentences:
            if tag in s:
                return _MARKER.sub("", s).strip()
        return ""

    citations: list[Citation] = []
    for old_n in used_order:
        item = evidence[old_n - 1]
        marker = renumber[old_n]
        if isinstance(item, RetrievedChunk):
            citations.append(Citation(
                marker=marker, source_type=item.source_type,
                source_id=item.source_id,
                snippet=item.text[:220] + ("…" if len(item.text) > 220 else ""),
                page_number=item.page_number or None,
                supports=_sentence_for(marker)))
        else:
            citations.append(Citation(
                marker=marker, source_type="graph",
                source_id=item.path_str, snippet=item.path_str,
                supports=_sentence_for(marker)))

    # ---- 4: unsourced-claim detection ----------------------------------------
    unsourced: list[str] = []
    for s in sentences:
        if _MARKER.search(s):
            continue
        if _NON_FACTUAL.search(s):
            continue
        if len(s.split()) < 4:            # fragments / headers
            continue
        unsourced.append(s)

    return AssembledAnswer(text=new_text, citations=citations,
                           unsourced_spans=unsourced)
