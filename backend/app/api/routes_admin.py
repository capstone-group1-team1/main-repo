"""
routes_admin.py — POST /devices/replace (admin only) and GET /users.
Validation + delegation only; the replacement logic lives in
graph/device_replacement.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth.mock_users import MOCK_USERS
from app.auth.permissions import require
from app.graph.device_replacement import ReplacementFailed, replace_device
from app.models.schemas import (MockUser, ReplaceDeviceRequest,
                                ReplacementSummary)

router = APIRouter()


@router.get("/users", response_model=list[MockUser])
def list_users() -> list[MockUser]:
    """Public: the frontend user picker needs this before a user is chosen."""
    return list(MOCK_USERS.values())


@router.post("/devices/replace", response_model=ReplacementSummary)
def devices_replace(body: ReplaceDeviceRequest,
                    user: MockUser = Depends(require("replace_device"))
                    ) -> ReplacementSummary:
    try:
        return replace_device(body)
    except ReplacementFailed as exc:
        raise HTTPException(
            status_code=409,
            detail={"failed_step": exc.step, "reason": exc.cause,
                    "note": "The graph transaction was rolled back; "
                            "no partial replacement was applied."})
