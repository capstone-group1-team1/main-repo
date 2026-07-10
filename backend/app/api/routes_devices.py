"""
routes_devices.py — GET /devices, GET /device/{id}, GET /graph/device/{id}.
Read-only device information; any role.
"""

from __future__ import annotations

import csv

from fastapi import APIRouter, Depends, HTTPException

from app.auth.permissions import require
from app.core.config import get_settings
from app.models.schemas import DeviceInfo, GraphNeighborhood, MockUser
from app.retrieval.graph_retriever import get_device_info, get_neighborhood

router = APIRouter()


def _known_ids() -> list[str]:
    path = get_settings().project_root / "data" / "asset_inventory.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return [r["asset_id"] for r in csv.DictReader(f)]


@router.get("/devices")
def list_devices(user: MockUser = Depends(require("view_devices"))) -> list[dict]:
    path = get_settings().project_root / "data" / "asset_inventory.csv"
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


@router.get("/device/{asset_id}", response_model=DeviceInfo)
def device(asset_id: str,
           user: MockUser = Depends(require("view_devices"))) -> DeviceInfo:
    info = get_device_info(asset_id)
    if info is None:
        raise HTTPException(404, detail=f"Unknown device '{asset_id}'. "
                                        f"Known ids: {_known_ids()}")
    d = info["device"]
    return DeviceInfo(
        asset_id=d["asset_id"], device_name=d.get("device_name", ""),
        manufacturer=d.get("manufacturer", ""), model=d.get("model", ""),
        serial_number=d.get("serial_number", ""), room=d.get("room", ""),
        installation_date=d.get("installed_on") or "",
        warranty_expiry=d.get("warranty_expiry") or "",
        status=d.get("status", ""), firmware_version=d.get("firmware_version", ""),
        relationships=info["relationships"],
    )


@router.get("/graph/device/{asset_id}", response_model=GraphNeighborhood)
def device_graph(asset_id: str,
                 user: MockUser = Depends(require("view_devices"))
                 ) -> GraphNeighborhood:
    nb = get_neighborhood(asset_id)
    if len(nb.nodes) <= 1 and not nb.edges:
        raise HTTPException(404, detail=f"Unknown device '{asset_id}'.")
    return nb
