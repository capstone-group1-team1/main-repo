"""
permissions.py — THE single centralized permission table.

Every mutating (and readable) action is checked against this one table via
the require() dependency.  No route performs its own role logic.
Rejections return a clear, human-readable reason (shown verbatim in the UI).
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.auth.mock_users import get_current_user
from app.models.schemas import MockUser, Role

# action -> roles allowed to perform it
PERMISSIONS: dict[str, set[Role]] = {
    "ask":              {"operator", "technician", "admin"},
    "view_devices":     {"operator", "technician", "admin"},
    "view_incidents":   {"operator", "technician", "admin"},
    "create_incident":  {"technician", "admin"},
    "replace_device":   {"admin"},
}


def is_allowed(role: Role, action: str) -> bool:
    return role in PERMISSIONS.get(action, set())


def require(action: str):
    """Usage:  user: MockUser = Depends(require("create_incident"))"""

    def dependency(user: MockUser = Depends(get_current_user)) -> MockUser:
        if not is_allowed(user.role, action):
            allowed = ", ".join(sorted(PERMISSIONS[action]))
            raise HTTPException(
                status_code=403,
                detail={
                    "allowed": False,
                    "reason": (
                        f"Role '{user.role}' is not permitted to perform "
                        f"'{action}'. This action requires one of: {allowed}."
                    ),
                },
            )
        return user

    return dependency
