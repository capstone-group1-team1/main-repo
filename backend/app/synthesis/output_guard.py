"""Utilities that protect users and JSON parsers from exposed reasoning."""

from __future__ import annotations

import json
import re
from typing import Any


_THINK_BLOCK_RE = re.compile(
    r"<think\b[^>]*>.*?</think>\s*",
    flags=re.IGNORECASE | re.DOTALL,
)

_THINK_TAG_RE = re.compile(
    r"</?think\b",
    flags=re.IGNORECASE,
)


def final_content(content: str | None) -> str:
    """Return final user-visible content without reasoning blocks.

    Groq is explicitly requested to use reasoning_format="hidden". This
    function is a defensive boundary in case a provider regression or an
    unexpected model response still includes <think> tags.

    Complete reasoning blocks are removed. Malformed or unclosed reasoning
    tags are rejected rather than exposed to users or passed to JSON parsers.
    """
    text = content or ""
    cleaned = _THINK_BLOCK_RE.sub("", text).strip()

    if _THINK_TAG_RE.search(cleaned):
        raise ValueError("model output contains malformed reasoning tags")

    return cleaned


def load_json_content(content: str | None) -> dict[str, Any]:
    """Clean model output and decode exactly one JSON object."""
    cleaned = final_content(content)

    if not cleaned:
        raise ValueError("model returned empty JSON content")

    data = json.loads(cleaned)

    if not isinstance(data, dict):
        raise ValueError("model JSON output must be an object")

    return data
