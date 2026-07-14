"""
Tests for app.ingestion.catalog -- the device catalog derived from
asset_inventory.csv, and manual-to-device filename matching.

Uses a temporary data/ directory with a small realistic CSV (same columns
as the real asset_inventory.csv) so tests never touch real project data.
Every assertion here was verified by actually running the real module
against these fixtures.
"""
from __future__ import annotations

import pytest

CSV_HEADER = ("asset_id,device_name,manufacturer,model,serial_number,room,"
             "installation_date,warranty_expiry,status,firmware_version,aliases")
CSV_ROWS = [
    "RTR-001,Cisco ISR 1111 Router,Cisco,ISR 1111,FGL2534L0QA,Server Room,"
    "2024-03-10,2027-03-10,Active,17.9.4a,router;isr1111;isr 1111",
    "AMR-001,Crestron AirMedia Receiver,Crestron,AM-3200,AM3200XY,Meeting Room,"
    "2024-01-15,2027-01-15,Active,2.5.1,airmedia;air media",
    "CP4-001,Crestron CP4 Control Processor,Crestron,CP4,CP4ZZ99,Meeting Room,"
    "2024-01-15,2027-01-15,Active,10.2,cp4;control processor",
]


@pytest.fixture
def catalog_module(tmp_path, monkeypatch):
    """Fresh catalog module state pointed at a temp data/ dir per test --
    load_devices()/load_rooms() are @lru_cache'd at module level, so the
    cache must be cleared between tests or they'd leak fixture state."""
    import app.ingestion.catalog as cat

    data_dir = tmp_path / "data"
    (data_dir / "manuals_pdf").mkdir(parents=True)
    (data_dir / "asset_inventory.csv").write_text(
        CSV_HEADER + "\n" + "\n".join(CSV_ROWS) + "\n", encoding="utf-8")

    class _Settings:
        project_root = tmp_path

    monkeypatch.setattr(cat, "get_settings", lambda: _Settings())
    cat.load_devices.cache_clear()
    cat.load_rooms.cache_clear()
    yield cat, data_dir
    cat.load_devices.cache_clear()
    cat.load_rooms.cache_clear()


def test_load_devices_returns_every_csv_row(catalog_module):
    cat, _ = catalog_module
    devices = cat.load_devices()
    assert len(devices) == 3
    assert devices[0].asset_id == "RTR-001"


def test_document_id_and_name_are_derived_from_asset_id(catalog_module):
    cat, _ = catalog_module
    devices = cat.load_devices()
    assert devices[0].document_id == "man-rtr-001"
    assert devices[0].document_name == "Cisco ISR 1111 Router Manual"


def test_explicit_aliases_from_csv_are_used_verbatim(catalog_module):
    cat, _ = catalog_module
    devices = cat.load_devices()
    assert devices[0].aliases == ("router", "isr1111", "isr 1111")


def test_devices_by_id_provides_dict_lookup(catalog_module):
    cat, _ = catalog_module
    by_id = cat.devices_by_id()
    assert by_id["AMR-001"].device_name == "Crestron AirMedia Receiver"


def test_load_rooms_returns_distinct_rooms_in_first_seen_order(catalog_module):
    cat, _ = catalog_module
    rooms = cat.load_rooms()
    assert rooms == ("Server Room", "Meeting Room")


def test_manual_matches_by_full_device_name_in_filename(catalog_module):
    cat, data_dir = catalog_module
    (data_dir / "manuals_pdf" / "Cisco ISR 1111 Router.pdf").touch()

    matches = cat.match_manuals_to_devices()
    assert len(matches) == 1
    assert matches[0].device.asset_id == "RTR-001"


def test_manual_matches_by_short_alias(catalog_module):
    cat, data_dir = catalog_module
    (data_dir / "manuals_pdf" / "cp4.pdf").touch()

    matches = cat.match_manuals_to_devices()
    assert len(matches) == 1
    assert matches[0].device.asset_id == "CP4-001"


def test_manual_matching_multiple_devices_all_named_correctly(catalog_module):
    cat, data_dir = catalog_module
    (data_dir / "manuals_pdf" / "Cisco ISR 1111 Router.pdf").touch()
    (data_dir / "manuals_pdf" / "airmedia_receiver_manual.pdf").touch()

    matches = cat.match_manuals_to_devices()
    matched_ids = {m.device.asset_id for m in matches}
    assert matched_ids == {"RTR-001", "AMR-001"}


def test_unmatched_manual_is_skipped_not_guessed(catalog_module):
    cat, data_dir = catalog_module
    (data_dir / "manuals_pdf" / "unrelated_document.pdf").touch()

    matches = cat.match_manuals_to_devices()
    assert matches == []


def test_no_manuals_directory_returns_empty_list(tmp_path, monkeypatch):
    import app.ingestion.catalog as cat

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "asset_inventory.csv").write_text(
        CSV_HEADER + "\n" + CSV_ROWS[0] + "\n", encoding="utf-8")
    # deliberately do NOT create manuals_pdf/

    class _Settings:
        project_root = tmp_path

    monkeypatch.setattr(cat, "get_settings", lambda: _Settings())
    cat.load_devices.cache_clear()
    cat.load_rooms.cache_clear()

    assert cat.match_manuals_to_devices() == []
