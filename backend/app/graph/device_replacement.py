"""
device_replacement.py — the admin-only, transactional device lifecycle
mechanism (invoked only via POST /devices/replace).

In ONE Neo4j transaction it:
  (a) marks the old device Retired and writes retired_on   (never deletes it)
  (b) creates the new Device node with installed_on = today
  (c) copies CONTAINS (room placement) to the new node while KEEPING it on the
      old node (historical room placement is preserved), and re-points the live
      topology edges (CONNECTED_TO/CONTROLS/USES) from the old node to the new
  (d) writes (old)-[:REPLACED_BY {date}]->(new)

If any of (a)-(d) fails, the Neo4j transaction rolls back automatically —
the graph is never left half-replaced.  Afterwards (outside the graph
transaction) it:
  (e) re-ingests the new device's manual IF a filename was provided — the
      hash store makes this a no-op when the manual is already ingested
  (f) the ingestion step itself writes the DESCRIBED_BY link.

History is preserved: the retired node keeps its incidents and its
installed_on/retired_on window, so "what was installed in the Meeting Room
last year?" traverses CONTAINS over ALL devices ever in the room and filters
by that window — and REPLACED_BY chains stay walkable across generations.
"""

from __future__ import annotations

from datetime import date

from app.core.config import get_neo4j_driver, get_settings
from app.core.logging import get_logger
from app.models.schemas import ReplaceDeviceRequest, ReplacementSummary

log = get_logger(__name__)


class ReplacementFailed(Exception):
    def __init__(self, step: str, cause: str):
        self.step, self.cause = step, cause
        super().__init__(f"Replacement failed at step '{step}': {cause}")


def _tx_replace(tx, req: ReplaceDeviceRequest, today: str) -> int:
    # Preconditions -----------------------------------------------------------
    old = tx.run(
        "MATCH (d:Device {asset_id:$id}) RETURN d.status AS s, d.room AS room",
        id=req.old_asset_id,
    ).single()
    if old is None:
        raise ReplacementFailed(
            "precondition", f"old device {req.old_asset_id} not found"
        )
    if old["s"] == "Retired":
        raise ReplacementFailed(
            "precondition", f"{req.old_asset_id} is already Retired"
        )
    if tx.run("MATCH (d:Device {asset_id:$id}) RETURN d", id=req.new_asset_id).single():
        raise ReplacementFailed(
            "precondition", f"new asset id {req.new_asset_id} already exists"
        )

    # (a) retire old ----------------------------------------------------------
    tx.run(
        "MATCH (d:Device {asset_id:$id}) "
        "SET d.status='Retired', d.retired_on=date($today)",
        id=req.old_asset_id,
        today=today,
    )

    # (b) create new ----------------------------------------------------------
    tx.run(
        """CREATE (n:Device {asset_id:$id, device_name:$name,
                             manufacturer:$manu, model:$model,
                             serial_number:$serial, room:$room,
                             installed_on:date($today), status:'Active',
                             firmware_version:$fw})""",
        id=req.new_asset_id,
        name=req.new_device_name,
        manu=req.new_manufacturer,
        model=req.new_model,
        serial=req.new_serial_number,
        room=old["room"],
        today=today,
        fw=req.new_firmware_version,
    )

    # (c) structural edges -----------------------------------------------------
    # CONTAINS is HISTORICAL room placement: keep it on the old (retired) device
    # so "what was in the Meeting Room last year?" still traverses it, and ALSO
    # add it to the new device. All other structural edges (CONNECTED_TO /
    # CONTROLS / USES) represent the live topology and are re-pointed off the
    # retired device onto the new one. MERGE everywhere prevents duplicate
    # edges on repeated runs.
    repointed = 0

    # CONTAINS: copy to new device (both directions), do NOT delete from old.
    tx.run(
        """MATCH (a)-[:CONTAINS]->(old:Device {asset_id:$old})
           MATCH (new:Device {asset_id:$new})
           MERGE (a)-[:CONTAINS]->(new)""",
        old=req.old_asset_id,
        new=req.new_asset_id,
    )
    tx.run(
        """MATCH (old:Device {asset_id:$old})-[:CONTAINS]->(b)
           MATCH (new:Device {asset_id:$new})
           MERGE (new)-[:CONTAINS]->(b)""",
        old=req.old_asset_id,
        new=req.new_asset_id,
    )

    # Live topology: re-point (copy to new, delete from old).
    for rel in ("CONNECTED_TO", "CONTROLS", "USES"):
        r = tx.run(
            f"""MATCH (a)-[e:{rel}]->(old:Device {{asset_id:$old}})
                MATCH (new:Device {{asset_id:$new}})
                MERGE (a)-[:{rel}]->(new)
                DELETE e RETURN count(*) AS c""",
            old=req.old_asset_id,
            new=req.new_asset_id,
        ).single()
        repointed += r["c"]
        r = tx.run(
            f"""MATCH (old:Device {{asset_id:$old}})-[e:{rel}]->(b)
                MATCH (new:Device {{asset_id:$new}})
                MERGE (new)-[:{rel}]->(b)
                DELETE e RETURN count(*) AS c""",
            old=req.old_asset_id,
            new=req.new_asset_id,
        ).single()
        repointed += r["c"]

    # (d) REPLACED_BY chain link ----------------------------------------------
    tx.run(
        """MATCH (old:Device {asset_id:$old}), (new:Device {asset_id:$new})
              MERGE (old)-[:REPLACED_BY {date: date($today)}]->(new)""",
        old=req.old_asset_id,
        new=req.new_asset_id,
        today=today,
    )
    return repointed


def replace_device(req: ReplaceDeviceRequest) -> ReplacementSummary:
    today = date.today().isoformat()

    # Early precondition: if a manual re-ingest is requested, the new device
    # must already be a row in asset_inventory.csv (the catalog needs it to
    # match the PDF). Check this BEFORE mutating the graph so we fail fast with
    # a clear message instead of leaving a replaced graph + un-ingested manual.
    if req.manual_pdf_filename:
        from app.ingestion.catalog import devices_by_id

        if req.new_asset_id not in devices_by_id():
            raise ReplacementFailed(
                "precondition",
                f"new device {req.new_asset_id} is not in asset_inventory.csv "
                f"— add its row before requesting manual ingestion",
            )

    # Steps (a)-(d): atomic — execute_write rolls back on any exception.
    with get_neo4j_driver().session() as s:
        repointed = s.execute_write(_tx_replace, req, today)
    log.info(
        "Replaced %s -> %s (%d edges re-pointed)",
        req.old_asset_id,
        req.new_asset_id,
        repointed,
    )

    # Steps (e)+(f): manual ingestion, hash-gated and idempotent.
    manual_ingested = False
    if req.manual_pdf_filename:
        from app.ingestion.catalog import ManualMatch, devices_by_id
        from app.ingestion.hash_store import HashStore
        from app.ingestion.pipeline import ingest_manual

        device = devices_by_id().get(req.new_asset_id)
        pdf_path = (
            get_settings().project_root
            / "data"
            / "manuals_pdf"
            / req.manual_pdf_filename
        )
        if device is None:
            log.warning(
                "New device %s is not in asset_inventory.csv yet — add "
                "its row, then re-run seeding to ingest its manual.",
                req.new_asset_id,
            )
        elif not pdf_path.exists():
            log.warning(
                "Manual %s not found in data/manuals_pdf/ — drop it in, "
                "then re-run seeding.",
                req.manual_pdf_filename,
            )
        else:
            store = HashStore()
            action = ingest_manual(
                ManualMatch(filename=req.manual_pdf_filename, device=device),
                store,
                enrich=False,
            )
            store.close()
            manual_ingested = action in ("new", "changed", "skipped")

    return ReplacementSummary(
        old_asset_id=req.old_asset_id,
        new_asset_id=req.new_asset_id,
        edges_repointed=repointed,
        retired_on=today,
        installed_on=today,
        manual_ingested=manual_ingested,
    )
