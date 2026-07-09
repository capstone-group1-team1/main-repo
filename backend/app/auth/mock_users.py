"""
mock_users.py — the seeded mock-user list.  NO real authentication by design:
the frontend picks a user, and every request carries the `X-Mock-User-Id`
header.  This deliberately replaces OAuth/JWT for this project's scope.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.models.schemas import MockUser

MOCK_USERS: dict[str, MockUser] = {
    u.id: u
    for u in [
        MockUser(id="u-omar",  name="Omar (Operator)",     role="operator"),
        MockUser(id="u-lina",  name="Lina (Operator)",     role="operator"),
        MockUser(id="u-ali",   name="Ali (Technician)",    role="technician"),
        MockUser(id="u-sara",  name="Sara (Technician)",   role="technician"),
        MockUser(id="u-amer",  name="Amer (Admin)",        role="admin"),
    ]
}


def get_current_user(x_mock_user_id: str = Header(...)) -> MockUser:
    """FastAPI dependency: resolves the mock-user header to a user object."""
    user = MOCK_USERS.get(x_mock_user_id)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail=f"Unknown mock user id '{x_mock_user_id}'. "
                   f"Pick a user in the UI. Known ids: {sorted(MOCK_USERS)}",
        )
    return user
