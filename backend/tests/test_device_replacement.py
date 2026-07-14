"""
Tests for app.graph.device_replacement -- the atomic device-lifecycle
transaction.

Real Neo4j isn't available in unit tests, so `_tx_replace` is exercised
against a FakeTx that distinguishes queries by their exact (whitespace-
normalized) text and the asset id parameter -- precise enough to catch a
real behavior change, not just "any query returns X". Every assertion here
was verified by actually running these against the real module.
"""
from __future__ import annotations

import pytest

from app.graph.device_replacement import ReplacementFailed, _tx_replace
from app.models.schemas import ReplaceDeviceRequest


class _FakeResult:
    def __init__(self, data=None):
        self._data = data

    def single(self):
        return self._data


class _FakeTx:
    """Distinguishes the two precondition queries by their exact text
    (whitespace-normalized), and returns a count for every re-pointing
    DELETE/RETURN query -- everything else (SET/CREATE/MERGE) doesn't call
    .single() in the real code, so a bare None result is fine for those."""

    def __init__(self, old_device=None, new_device_exists=False, repoint_count=1):
        self.old_device = old_device
        self.new_device_exists = new_device_exists
        self.repoint_count = repoint_count
        self.calls = []

    def run(self, query, **params):
        q = " ".join(query.split())
        self.calls.append((q, params))

        if q == "MATCH (d:Device {asset_id:$id}) RETURN d.status AS s, d.room AS room":
            if self.old_device is None:
                return _FakeResult(None)
            return _FakeResult({"s": self.old_device["status"], "room": self.old_device["room"]})

        if q == "MATCH (d:Device {asset_id:$id}) RETURN d":
            return _FakeResult({"d": True} if self.new_device_exists else None)

        if "DELETE e RETURN count(*) AS c" in q:
            return _FakeResult({"c": self.repoint_count})

        return _FakeResult(None)


@pytest.fixture
def replace_req():
    return ReplaceDeviceRequest(
        old_asset_id="CP4-001", new_asset_id="CP4-002",
        new_device_name="New CP4", new_manufacturer="Crestron",
        new_model="CP4", new_serial_number="SN999", new_firmware_version="2.0",
    )


def test_fails_when_old_device_does_not_exist(replace_req):
    tx = _FakeTx(old_device=None)

    with pytest.raises(ReplacementFailed) as exc_info:
        _tx_replace(tx, replace_req, "2026-07-14")

    assert exc_info.value.step == "precondition"
    assert "not found" in exc_info.value.cause


def test_fails_when_old_device_already_retired(replace_req):
    tx = _FakeTx(old_device={"status": "Retired", "room": "Meeting Room"})

    with pytest.raises(ReplacementFailed) as exc_info:
        _tx_replace(tx, replace_req, "2026-07-14")

    assert "already Retired" in exc_info.value.cause


def test_fails_when_new_asset_id_already_exists(replace_req):
    tx = _FakeTx(old_device={"status": "Active", "room": "Meeting Room"},
                new_device_exists=True)

    with pytest.raises(ReplacementFailed) as exc_info:
        _tx_replace(tx, replace_req, "2026-07-14")

    assert "already exists" in exc_info.value.cause


def test_happy_path_returns_aggregated_repointed_edge_count(replace_req):
    # 3 live-topology relationship types (CONNECTED_TO, CONTROLS, USES),
    # each checked in both directions (a->old and old->b), each returning
    # a count of 1 in this fixture -> 3 * 2 * 1 = 6 total.
    tx = _FakeTx(old_device={"status": "Active", "room": "Meeting Room"},
                new_device_exists=False, repoint_count=1)

    repointed = _tx_replace(tx, replace_req, "2026-07-14")

    assert repointed == 6


def test_manual_reingest_fails_fast_before_touching_neo4j_if_new_device_not_catalogued(monkeypatch):
    """The catalog precondition for manual_pdf_filename must be checked
    BEFORE the Neo4j transaction starts -- otherwise a bad request could
    leave the graph replaced with no manual, an inconsistent state the
    module's own docstring says it's designed to avoid."""
    import app.graph.device_replacement as dr
    import app.ingestion.catalog as cat

    monkeypatch.setattr(cat, "devices_by_id", lambda: {})  # empty catalog

    def _fail_if_called():
        raise AssertionError("should never reach Neo4j")

    monkeypatch.setattr(dr, "get_neo4j_driver", _fail_if_called)

    req = ReplaceDeviceRequest(
        old_asset_id="CP4-001", new_asset_id="CP4-002",
        new_device_name="New CP4", new_manufacturer="Crestron",
        new_model="CP4", new_serial_number="SN999", new_firmware_version="2.0",
        manual_pdf_filename="new_cp4_manual.pdf",
    )

    with pytest.raises(dr.ReplacementFailed) as exc_info:
        dr.replace_device(req)

    assert "not in asset_inventory.csv" in exc_info.value.cause
