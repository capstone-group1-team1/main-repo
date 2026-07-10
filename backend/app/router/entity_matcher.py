"""
entity_matcher.py — query-time gazetteer lookup.

Matches device names / models / aliases and room names in the question, using
the device catalog (derived from asset_inventory.csv — the single source of
truth).  Deterministic and explainable — no LLM.  Its output feeds BOTH the
routing decision and the Graph Confidence signal (exact match found or not).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from app.ingestion.catalog import load_devices, load_rooms


@dataclass(frozen=True)
class MatchedEntity:
    surface: str          # text as matched in the question
    canonical_id: str     # asset_id or room name
    kind: str             # "device" | "room"


@lru_cache
def _gazetteer() -> list[tuple[str, str, str]]:
    """[(alias_lowercase, canonical_id, kind)], longest aliases first so
    'meeting room' wins over 'room'.  Everything comes from the catalog."""
    entries: list[tuple[str, str, str]] = []
    for d in load_devices():
        entries.append((d.device_name.lower(), d.asset_id, "device"))
        entries.append((d.model.lower(), d.asset_id, "device"))
        entries.append((d.asset_id.lower(), d.asset_id, "device"))
        for alias in d.aliases:
            entries.append((alias.lower(), d.asset_id, "device"))
    for room in load_rooms():
        entries.append((room.lower(), room, "room"))
    # de-duplicate, then longest-first
    entries = list(dict.fromkeys(entries))
    entries.sort(key=lambda e: -len(e[0]))
    return entries


def match(question: str) -> list[MatchedEntity]:
    q = " " + question.lower() + " "
    found: dict[str, MatchedEntity] = {}
    for alias, canonical, kind in _gazetteer():
        if canonical in found:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", q):
            found[canonical] = MatchedEntity(alias, canonical, kind)
    return list(found.values())
