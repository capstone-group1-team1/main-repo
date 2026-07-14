"""
Tests for app.synthesis.citation_assembler.assemble().

Every expected value in this file was verified by actually executing the
real assemble() function against these exact inputs (not just reasoned
about), including the sentence-splitting edge case documented at the bottom.
"""
from __future__ import annotations

from app.models.schemas import GraphFact, RetrievedChunk


def _chunk(chunk_id, text, source_id="man-1", page_number=None):
    return RetrievedChunk(
        chunk_id=chunk_id, text=text, score=0.9, source_type="manual",
        source_id=source_id, document_id="d1", document_name="Doc1",
        device_id="dev1", device_name="AMR-001", section_title="Reset",
        page_number=page_number,
    )


def test_markers_resolve_to_correct_evidence_in_order():
    from app.synthesis.citation_assembler import assemble

    chunk1 = _chunk("c1", "Factory reset restores defaults.", source_id="man-1")
    chunk2 = _chunk("c2", "Press and hold the button.", source_id="man-2")

    # Marker placement follows the system prompt's own convention: BEFORE
    # the sentence-ending period, e.g. "...adapter [3]." — not after it.
    answer = "Factory reset restores defaults [1]. Press and hold the button [2]."
    result = assemble(answer, [chunk1, chunk2])

    assert len(result.citations) == 2
    assert result.citations[0].source_id == "man-1"
    assert result.citations[1].source_id == "man-2"
    assert result.unsourced_spans == []


def test_markers_are_renumbered_compactly_in_answer_order():
    from app.synthesis.citation_assembler import assemble

    chunk1 = _chunk("c1", "First fact.", source_id="man-1")
    chunk2 = _chunk("c2", "Second fact.", source_id="man-2")

    # Evidence [2] is cited before evidence [1] in the answer text.
    answer = "Second point [2]. First point [1]."
    result = assemble(answer, [chunk1, chunk2])

    # Renumbered to [1],[2] in the order they actually appear in the text.
    assert "[1]" in result.text
    assert "[2]" in result.text
    assert result.text.index("[1]") < result.text.index("[2]")
    # The renumbered [1] must still point at the evidence it originally cited
    # (original marker 2 -> chunk2 / "man-2"), not at evidence index 1.
    assert result.citations[0].source_id == "man-2"
    assert result.citations[1].source_id == "man-1"


def test_dangling_marker_is_stripped_not_left_in_text():
    from app.synthesis.citation_assembler import assemble

    chunk1 = _chunk("c1", "Some fact.")
    # Only one evidence item exists, but the answer cites marker [5].
    answer = "This claims something [5]."
    result = assemble(answer, [chunk1])

    assert "[5]" not in result.text
    assert len(result.citations) == 0


def test_factual_sentence_without_marker_is_flagged_unsourced():
    from app.synthesis.citation_assembler import assemble

    chunk1 = _chunk("c1", "Some fact.")
    answer = "The AirMedia receiver was manufactured in a factory overseas."
    result = assemble(answer, [chunk1])

    assert result.unsourced_spans == [
        "The AirMedia receiver was manufactured in a factory overseas."
    ]


def test_decline_hedge_sentence_is_not_flagged_unsourced():
    from app.synthesis.citation_assembler import assemble

    chunk1 = _chunk("c1", "Some fact.")
    answer = "The available sources do not cover this question."
    result = assemble(answer, [chunk1])

    assert result.unsourced_spans == []


def test_short_fragment_is_not_flagged_unsourced():
    from app.synthesis.citation_assembler import assemble

    # Fewer than 4 words -- treated as a fragment/header, not a claim.
    answer = "See below."
    result = assemble(answer, [])

    assert result.unsourced_spans == []


def test_graph_fact_citation_uses_path_string_as_snippet():
    from app.synthesis.citation_assembler import assemble

    fact = GraphFact(fact_id="f1", path_str="CP4-001 -CONTROLS-> DSP-001",
                     text="CP4 controls the display.")
    answer = "CP4 controls the display [1]."
    result = assemble(answer, [fact])

    assert result.citations[0].source_type == "graph"
    assert result.citations[0].source_id == "CP4-001 -CONTROLS-> DSP-001"
    assert result.citations[0].snippet == "CP4-001 -CONTROLS-> DSP-001"


def test_known_limitation_marker_placed_after_sentence_period_orphans_citation():
    """Documents a real, verified edge case: if a marker follows a period AND
    a space (e.g. "Sentence. [1] Next sentence."), the sentence splitter's
    regex attaches the marker to the FOLLOWING sentence, not the one it was
    meant to cite -- so the preceding sentence gets flagged as unsourced even
    though a marker was written for it. This should never happen in practice
    because the system prompt's own example (prompts.py) places markers
    BEFORE the period, e.g. "...adapter [3]." -- but if a model ever
    violates that convention, this is the resulting (degraded, not crashed)
    behavior: the sentence with the "orphaned" marker still gets a citation
    entry, it just isn't the sentence a human would expect it to attach to.
    """
    from app.synthesis.citation_assembler import assemble

    chunk1 = _chunk("c1", "Factory reset restores defaults.", source_id="man-1")
    chunk2 = _chunk("c2", "Press and hold the button.", source_id="man-2")

    # Marker placed AFTER the period + space (violates the prompt's own
    # documented convention).
    answer = "Factory reset restores defaults. [1] Press and hold the button. [2]"
    result = assemble(answer, [chunk1, chunk2])

    # The first sentence ends up in unsourced_spans despite a marker being
    # written for it -- because that marker got attached to the next
    # sentence by the splitter, not this one.
    assert "Factory reset restores defaults." in result.unsourced_spans
