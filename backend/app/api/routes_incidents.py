"""
routes_incidents.py — GET /incidents (any role), POST /incidents
(technician/admin only).

POST is the ONLY runtime write path for incidents: it allocates the next
incident id in the graph, writes the Incident node + HAS_INCIDENT edge, and
ingests the row into Weaviate through the standard pipeline (so the new
incident is immediately retrievable AND citable by its incident id).
The seed CSV is seed data only — never appended to at runtime.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.permissions import require
from app.core.config import get_neo4j_driver
from app.core.logging import get_logger
from app.models.schemas import IncidentIn, IncidentOut, MockUser

log = get_logger(__name__)
router = APIRouter()


@router.get("/incidents", response_model=list[IncidentOut])
def list_incidents(
    device_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    user: MockUser = Depends(require("view_incidents")),
) -> list[IncidentOut]:
    where, params = ["1=1"], {}
    if device_id:
        where.append("d.asset_id = $device_id"); params["device_id"] = device_id
    if date_from:
        where.append("i.date >= date($date_from)"); params["date_from"] = date_from
    if date_to:
        where.append("i.date <= date($date_to)"); params["date_to"] = date_to
    with get_neo4j_driver().session() as s:
        rows = s.run(
            f"""MATCH (d:Device)-[:HAS_INCIDENT]->(i:Incident)
                WHERE {' AND '.join(where)}
                RETURN i.incident_id AS incident_id, d.asset_id AS device_id,
                       toString(i.date) AS date, i.problem AS problem,
                       i.resolution AS resolution, i.technician AS technician,
                       i.status AS status
                ORDER BY i.date DESC""", **params).data()
    return [IncidentOut(**r) for r in rows]


@router.post("/incidents", response_model=IncidentOut, status_code=201)
def create_incident(body: IncidentIn,
                    user: MockUser = Depends(require("create_incident"))
                    ) -> IncidentOut:
    with get_neo4j_driver().session() as s:
        exists = s.run("MATCH (d:Device {asset_id:$id}) RETURN d",
                       id=body.device_id).single()
        if exists is None:
            raise HTTPException(404, detail=f"Unknown device '{body.device_id}'.")

        # Allocate next id (I001, I002, ...) and write node+edge in one tx.
        def _tx(tx):
            row = tx.run("MATCH (i:Incident) RETURN count(i) AS c").single()
            new_id = f"I{row['c'] + 1:03d}"
            status = "resolved" if body.resolution.strip() else "open"
            tx.run(
                """MATCH (d:Device {asset_id:$device_id})
                   CREATE (i:Incident {incident_id:$id, date:date($date),
                                       problem:$problem, resolution:$resolution,
                                       technician:$technician, status:$status})
                   CREATE (d)-[:HAS_INCIDENT]->(i)""",
                device_id=body.device_id, id=new_id, date=date.today().isoformat(),
                problem=body.problem, resolution=body.resolution,
                technician=body.technician, status=status)
            return new_id, status

        new_id, status = s.execute_write(_tx)

    # Ingest into the vector store (best-effort: a vector failure never loses
    # the incident — the graph already has it, and re-running the pipeline heals).
    try:
        from app.ingestion.hash_store import HashStore
        from app.ingestion.pipeline import ingest_incident_row
        store = HashStore()
        ingest_incident_row({
            "incident_id": new_id, "device_id": body.device_id,
            "date": date.today().isoformat(), "problem": body.problem,
            "resolution": body.resolution, "technician": body.technician,
        }, store)
        store.close()
    except Exception as exc:
        log.warning("Incident %s created but vector indexing pending: %s",
                    new_id, exc)

    return IncidentOut(incident_id=new_id, device_id=body.device_id,
                       date=date.today().isoformat(), problem=body.problem,
                       resolution=body.resolution, technician=body.technician,
                       status=status)
