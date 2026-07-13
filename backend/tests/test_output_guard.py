from __future__ import annotations

import pytest

from app.synthesis.output_guard import final_content, load_json_content


def test_final_content_preserves_normal_answer():
    assert final_content("Final answer") == "Final answer"


def test_final_content_removes_complete_think_block():
    raw = "<think>private reasoning</think>\nFinal answer"

    assert final_content(raw) == "Final answer"


def test_final_content_rejects_malformed_think_tag():
    raw = "<think>private reasoning without closing tag"

    with pytest.raises(ValueError, match="malformed reasoning tags"):
        final_content(raw)


def test_load_json_content_handles_defensive_think_block():
    raw = (
        '<think>private reasoning</think>'
        '{"route": "HYBRID", "confidence": 0.9}'
    )

    assert load_json_content(raw) == {
        "route": "HYBRID",
        "confidence": 0.9,
    }


def test_load_json_content_requires_object():
    with pytest.raises(ValueError, match="must be an object"):
        load_json_content('["not", "an", "object"]')
