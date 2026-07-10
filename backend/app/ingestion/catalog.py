"""
catalog.py — the device catalog, derived entirely from asset_inventory.csv.

This REPLACES the old hardcoded registry. There is now ONE source of truth:
the inventory CSV. Nothing about devices or manuals is hardcoded here.

Two things it provides:
  1. load_devices()        — every device row as a DeviceRecord (name, model,
                             manufacturer, room, dates, and routing aliases).
  2. match_manuals_to_devices() — scans data/manuals_pdf/ and links each PDF
                             to a device by NORMALIZED NAME CONTAINMENT:
                             a file whose name contains the device name (in any
                             reasonable spelling) is that device's manual.

Add a device = add a CSV row + drop a PDF whose filename contains the device
name. No code changes. Ambiguous or unmatched files are logged and skipped,
never guessed.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class DeviceRecord:
    asset_id: str
    device_name: str
    manufacturer: str
    model: str
    room: str
    aliases: tuple[str, ...] = field(default_factory=tuple)

    # Derived identifiers used everywhere else (graph doc node, vector filter).
    @property
    def document_id(self) -> str:
        return f"man-{self.asset_id.lower()}"

    @property
    def document_name(self) -> str:
        return f"{self.device_name} Manual"


@dataclass(frozen=True)
class ManualMatch:
    filename: str
    device: DeviceRecord


def _normalize(text: str) -> str:
    """Lowercase and strip everything except letters/digits, so
    'Cisco ISR 1111 Router', 'cisco_isr_1111_router.pdf', and
    'Cisco-ISR-1111-Router' all reduce to the same token string."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _derive_aliases(device: dict) -> tuple[str, ...]:
    """If the CSV row has no explicit aliases, derive reasonable ones from the
    device name and model (individual words + the model string)."""
    raw = (device.get("aliases") or "").strip()
    if raw:
        return tuple(a.strip().lower() for a in raw.split(";") if a.strip())
    words = re.findall(r"[a-z0-9]+", device["device_name"].lower())
    model = device["model"].lower()
    # keep multi-char tokens; add the model as a phrase
    derived = {w for w in words if len(w) > 2} | {model}
    return tuple(sorted(derived))


def _data_dir() -> Path:
    return get_settings().project_root / "data"


@lru_cache
def load_devices() -> list[DeviceRecord]:
    """Every device from the inventory CSV. Cached for the process."""
    path = _data_dir() / "asset_inventory.csv"
    devices: list[DeviceRecord] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            devices.append(
                DeviceRecord(
                    asset_id=row["asset_id"].strip(),
                    device_name=row["device_name"].strip(),
                    manufacturer=row["manufacturer"].strip(),
                    model=row["model"].strip(),
                    room=row["room"].strip(),
                    aliases=_derive_aliases(row),
                )
            )
    return devices


def devices_by_id() -> dict[str, DeviceRecord]:
    return {d.asset_id: d for d in load_devices()}


@lru_cache
def load_rooms() -> tuple[str, ...]:
    """Distinct room names from the inventory CSV, in first-seen order. Single
    source of truth — adding a room in the CSV needs no code change."""
    rooms: list[str] = []
    for d in load_devices():
        if d.room and d.room not in rooms:
            rooms.append(d.room)
    return tuple(rooms)


def match_manuals_to_devices() -> list[ManualMatch]:
    """Scan data/manuals_pdf/*.pdf and match each to a device.

    Matching tries three keys, most specific first, so real-world filenames
    that abbreviate the full device name still match safely:
      1. full device name contained in the filename   (strongest)
      2. model string contained in the filename
      3. a distinctive alias contained in the filename
    The device with the longest matched key wins; genuine ties are skipped
    with a warning rather than guessed."""
    manuals_dir = _data_dir() / "manuals_pdf"
    if not manuals_dir.exists():
        return []

    devices = load_devices()

    def match_keys(d: DeviceRecord) -> list[str]:
        # normalized candidate keys for this device, longest first
        keys = {_normalize(d.device_name), _normalize(d.model)}
        keys |= {_normalize(a) for a in d.aliases if len(_normalize(a)) >= 4}
        return [k for k in keys if k]

    indexed = [(d, match_keys(d)) for d in devices]

    matches: list[ManualMatch] = []
    for pdf in sorted(manuals_dir.glob("*.pdf")):
        norm_file = _normalize(pdf.stem)

        # Best (device, matched-key-length) where a key is contained in the file.
        scored: list[tuple[DeviceRecord, int]] = []
        for d, keys in indexed:
            hit = max((len(k) for k in keys if k in norm_file), default=0)
            if hit:
                scored.append((d, hit))

        if not scored:
            log.warning(
                "Manual %s matches no device (by name, model, or alias) "
                "— skipped. Include the device name in the filename, "
                "e.g. 'Cisco ISR 1111 Router.pdf'.",
                pdf.name,
            )
            continue

        scored.sort(key=lambda c: -c[1])
        best = scored[0][1]
        top = [d for d, s in scored if s == best]
        if len(top) > 1:
            names = ", ".join(d.device_name for d in top)
            log.warning(
                "Manual %s matches multiple devices equally (%s) — "
                "skipped. Make the filename more specific.",
                pdf.name,
                names,
            )
            continue

        matches.append(ManualMatch(filename=pdf.name, device=top[0]))
        log.info("Manual %s -> %s (%s)", pdf.name, top[0].asset_id, top[0].device_name)

    return matches
