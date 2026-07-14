"""
Tests for app.router.entity_matcher.match() -- query-time gazetteer lookup.

Every assertion here was verified by actually running match() against
realistic device/room fixtures.
"""
from __future__ import annotations

import pytest

from app.ingestion.catalog import DeviceRecord


@pytest.fixture
def matcher(monkeypatch):
    import app.router.entity_matcher as em

    devices = [
        DeviceRecord(asset_id="CP4-001", device_name="Crestron CP4 Control Processor",
                     manufacturer="Crestron", model="CP4", room="Meeting Room",
                     aliases=("cp4", "control processor")),
        DeviceRecord(asset_id="AMR-001", device_name="Crestron AirMedia Receiver",
                     manufacturer="Crestron", model="AM-3200", room="Meeting Room",
                     aliases=("airmedia", "air media")),
    ]
    monkeypatch.setattr(em, "load_devices", lambda: devices)
    monkeypatch.setattr(em, "load_rooms", lambda: ("Meeting Room", "Server Room"))
    em._gazetteer.cache_clear()
    yield em
    em._gazetteer.cache_clear()


def test_matches_device_by_alias(matcher):
    result = matcher.match("What devices depend on the CP4?")
    assert [(e.canonical_id, e.kind) for e in result] == [("CP4-001", "device")]


def test_matches_room_by_name(matcher):
    result = matcher.match("What is in the Meeting Room?")
    assert [(e.canonical_id, e.kind) for e in result] == [("Meeting Room", "room")]


def test_does_not_false_positive_on_partial_word(matcher):
    # "cp4x" contains "cp4" as a substring, but the word-boundary regex
    # must NOT treat that as a match for the "cp4" alias.
    result = matcher.match("The cp4x device is broken")
    assert result == []


def test_matches_multiple_distinct_entities_in_one_question(matcher):
    result = matcher.match("Does the AirMedia receiver connect to the CP4?")
    assert sorted(e.canonical_id for e in result) == ["AMR-001", "CP4-001"]


def test_no_entities_returns_empty_list(matcher):
    assert matcher.match("What is the capital of France?") == []


def test_longest_overlapping_alias_of_same_device_is_recorded_as_surface(monkeypatch):
    """A device with two overlapping aliases ("cp4" and "cp4 control
    processor") must resolve to exactly ONE MatchedEntity (not two), and
    the longest-alias-first sort means the recorded `surface` text is the
    longer alias, since matching it first marks the canonical id as found
    and the shorter alias is never reached for that same device."""
    import app.router.entity_matcher as em

    devices = [
        DeviceRecord(asset_id="CP4-001", device_name="Crestron CP4 Control Processor",
                     manufacturer="Crestron", model="CP4", room="Meeting Room",
                     aliases=("cp4", "cp4 control processor")),
    ]
    monkeypatch.setattr(em, "load_devices", lambda: devices)
    monkeypatch.setattr(em, "load_rooms", lambda: ())
    em._gazetteer.cache_clear()

    result = em.match("the cp4 control processor is offline")
    assert len(result) == 1
    assert result[0].canonical_id == "CP4-001"
    assert result[0].surface == "cp4 control processor"
