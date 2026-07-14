"""
Tests for app.retrieval.hybrid_merger.merge() -- composing HYBRID evidence.

All assertions verified by actually running merge() against these inputs.
"""
from __future__ import annotations

from app.models.schemas import GraphFact, RetrievedChunk


def _chunk(chunk_id, text):
    return RetrievedChunk(
        chunk_id=chunk_id, text=text, score=0.9, source_type="manual",
        source_id=chunk_id, document_id="d1", document_name="Doc",
        device_id="dev1", device_name="Dev", section_title="S",
    )


def _fact(fact_id, source_chunk_id=None):
    return GraphFact(fact_id=fact_id, path_str="A->B", text="fact text",
                     source_chunk_id=source_chunk_id)


def test_graph_facts_come_before_chunks():
    from app.retrieval.hybrid_merger import merge

    c1 = _chunk("c1", "chunk text one")
    f1 = _fact("f1")
    result = merge([c1], [f1])

    assert isinstance(result[0], GraphFact)
    assert isinstance(result[1], RetrievedChunk)


def test_enrichment_fact_dropped_when_its_source_chunk_is_already_retrieved():
    from app.retrieval.hybrid_merger import merge

    c1 = _chunk("c1", "chunk text one")
    f1 = _fact("f1", source_chunk_id="c1")  # already covered by chunk c1
    result = merge([c1], [f1])

    assert len(result) == 1
    assert isinstance(result[0], RetrievedChunk)


def test_enrichment_fact_kept_when_its_source_chunk_was_not_retrieved():
    from app.retrieval.hybrid_merger import merge

    c1 = _chunk("c1", "chunk text one")
    f1 = _fact("f1", source_chunk_id="c99")  # not among retrieved chunks
    result = merge([c1], [f1])

    assert len(result) == 2


def test_near_identical_chunk_text_is_deduplicated():
    from app.retrieval.hybrid_merger import merge

    c1 = _chunk("c1", "chunk text one")
    c2 = _chunk("c2", "CHUNK TEXT ONE")  # same normalized text, different case
    result = merge([c1, c2], [])

    assert len(result) == 1
    assert result[0].chunk_id == "c1"  # first occurrence wins


def test_genuinely_different_chunks_are_both_kept():
    from app.retrieval.hybrid_merger import merge

    c1 = _chunk("c1", "chunk text one")
    c2 = _chunk("c2", "a totally different chunk")
    result = merge([c1, c2], [])

    assert len(result) == 2


def test_merge_trims_to_rerank_candidate_pool_size(monkeypatch):
    import app.retrieval.hybrid_merger as hm

    monkeypatch.setattr(hm, "get_settings", lambda: type(
        "S", (), {"rerank_candidate_pool": 20})())

    many_chunks = [_chunk(f"c{i}", f"unique text {i}") for i in range(30)]
    result = hm.merge(many_chunks, [])

    assert len(result) == 20


def test_merge_with_no_evidence_returns_empty_list():
    from app.retrieval.hybrid_merger import merge

    assert merge([], []) == []
