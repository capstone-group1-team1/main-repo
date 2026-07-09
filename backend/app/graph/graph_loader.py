"""
graph_loader.py — builds the Layer 1 (physical, authoritative) knowledge
graph from the CSV files.  Run with:

    python -m app.graph.graph_loader

Nodes:   (:Room {name})   (:Device {asset_id, ...inventory columns})
         (:Document {document_id, name})   (:Incident {incident_id, ...})
Edges:   CONTAINS, CONNECTED_TO, CONTROLS, USES        (from relationships.csv)
         DESCRIBED_BY (device->document, written at ingestion)
         HAS_INCIDENT (device->incident, from incidents.csv / POST /incidents)
Temporal: installed_on / retired_on are DATE PROPERTIES on Device;
         (:Device)-[:REPLACED_BY {date}]->(:Device) is written only by the
         device-replacement mechanism — devices are NEVER deleted.

Everything uses MERGE keyed on natural ids, so re-running is a no-op.
The LLM never writes to this layer.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.core.config import get_neo4j_driver, get_settings
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)

SCHEMA_STATEMENTS = [
    "CREATE CONSTRAINT device_id  IF NOT EXISTS FOR (d:Device)   REQUIRE d.asset_id    IS UNIQUE",
    "CREATE CONSTRAINT room_name  IF NOT EXISTS FOR (r:Room)     REQUIRE r.name        IS UNIQUE",
    "CREATE CONSTRAINT doc_id     IF NOT EXISTS FOR (m:Document) REQUIRE m.document_id IS UNIQUE",
    "CREATE CONSTRAINT inc_id     IF NOT EXISTS FOR (i:Incident) REQUIRE i.incident_id IS UNIQUE",
]

STRUCTURAL_RELATIONS = {"CONTAINS", "CONNECTED_TO", "CONTROLS", "USES"}


def _data_dir() -> Path:
    return get_settings().project_root / "data"


def apply_schema() -> None:
    with get_neo4j_driver().session() as s:
        for stmt in SCHEMA_STATEMENTS:
            s.run(stmt)
    log.info("Schema constraints applied")


def load_assets() -> int:
    """MERGE one Device node per inventory row (all columns as properties)."""
    rows = list(
        csv.DictReader(
            open(_data_dir() / "asset_inventory.csv", newline="", encoding="utf-8")
        )
    )
    with get_neo4j_driver().session() as s:
        s.run(
            """UNWIND $rows AS r
               MERGE (d:Device {asset_id: r.asset_id})
               SET d.device_name      = r.device_name,
                   d.manufacturer     = r.manufacturer,
                   d.model            = r.model,
                   d.serial_number    = r.serial_number,
                   d.room             = r.room,
                   d.installed_on     = date(r.installation_date),
                   d.warranty_expiry  = date(r.warranty_expiry),
                   d.status           = r.status,
                   d.firmware_version = r.firmware_version
               MERGE (room:Room {name: r.room})
               MERGE (room)-[:CONTAINS]->(d)""",
            rows=rows,
        )
    log.info("Loaded %d devices (+rooms +CONTAINS)", len(rows))
    return len(rows)


def load_relationships() -> int:
    """MERGE the physical edges.  Room CONTAINS rows are already covered by
    load_assets; device-to-device rows are matched by asset_id.  Unknown ids
    are skipped with an ERROR (never abort the whole seed for one bad row)."""
    rows = list(
        csv.DictReader(
            open(_data_dir() / "relationships.csv", newline="", encoding="utf-8")
        )
    )
    count = 0
    with get_neo4j_driver().session() as s:
        # Known devices and rooms both come from the catalog (single source of
        # truth) — no redundant re-read of asset_inventory.csv, no hardcoded
        # room list.
        from app.ingestion.catalog import devices_by_id, load_rooms

        known = set(devices_by_id().keys())
        rooms = set(load_rooms())

        # Bucket rows by (kind, relation) so each group is one UNWIND write
        # instead of a query per edge. kind is "room" or "device".
        room_edges: dict[str, list[dict]] = {}
        device_edges: dict[str, list[dict]] = {}
        for r in rows:
            rel = r["relation"].strip()
            if rel not in STRUCTURAL_RELATIONS:
                log.error("Unknown relation %r — row skipped", rel)
                continue
            src, tgt = r["source_id"].strip(), r["target_id"].strip()
            if src in rooms:  # Room CONTAINS
                room_edges.setdefault(rel, []).append({"s": src, "t": tgt})
            elif src in known and tgt in known:  # Device <-> Device
                device_edges.setdefault(rel, []).append({"s": src, "t": tgt})
            else:
                log.error("Unknown id in row %s — skipped", r)
                continue
            count += 1

        for rel, pairs in room_edges.items():
            s.run(
                f"UNWIND $pairs AS p "
                f"MATCH (a:Room {{name:p.s}}), (b:Device {{asset_id:p.t}}) "
                f"MERGE (a)-[:{rel}]->(b)",
                pairs=pairs,
            )
        for rel, pairs in device_edges.items():
            s.run(
                f"UNWIND $pairs AS p "
                f"MATCH (a:Device {{asset_id:p.s}}), (b:Device {{asset_id:p.t}}) "
                f"MERGE (a)-[:{rel}]->(b)",
                pairs=pairs,
            )
    log.info("Loaded %d relationship edges", count)
    return count


def load_incident_nodes() -> int:
    """Incident nodes + HAS_INCIDENT edges from the seed CSV (idempotent).
    New incidents created at runtime via POST /incidents use the same MERGE."""
    rows = list(
        csv.DictReader(
            open(_data_dir() / "incidents.csv", newline="", encoding="utf-8")
        )
    )
    with get_neo4j_driver().session() as s:
        s.run(
            """UNWIND $rows AS r
               MERGE (i:Incident {incident_id: r.incident_id})
               SET i.date = date(r.date), i.problem = r.problem,
                   i.resolution = r.resolution, i.technician = r.technician,
                   i.status = CASE WHEN r.resolution = '' THEN 'open'
                                   ELSE 'resolved' END
               WITH i, r
               MATCH (d:Device {asset_id: r.device_id})
               MERGE (d)-[:HAS_INCIDENT]->(i)""",
            rows=rows,
        )
    log.info("Loaded %d incidents", len(rows))
    return len(rows)


def link_described_by(device) -> None:
    """Called by the ingestion pipeline after a manual is ingested:
    (:Device)-[:DESCRIBED_BY]->(:Document).  `device` is a catalog
    DeviceRecord (asset_id, document_id, document_name)."""
    with get_neo4j_driver().session() as s:
        s.run(
            """MERGE (m:Document {document_id: $doc_id})
               SET m.name = $doc_name
               WITH m
               MATCH (d:Device {asset_id: $device_id})
               MERGE (d)-[:DESCRIBED_BY]->(m)""",
            doc_id=device.document_id,
            doc_name=device.document_name,
            device_id=device.asset_id,
        )


def run_full() -> None:
    configure_logging(get_settings().log_level)
    log.info("=== Graph loader starting ===")
    apply_schema()
    load_assets()
    load_relationships()
    load_incident_nodes()
    with get_neo4j_driver().session() as s:
        counts = s.run(
            "MATCH (n) RETURN labels(n)[0] AS l, count(*) AS c " "ORDER BY l"
        ).data()
    log.info("Node counts: %s", counts)
    from app.core.config import close_all_clients

    close_all_clients()


if __name__ == "__main__":
    run_full()
