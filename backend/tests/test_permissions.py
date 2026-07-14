"""
Tests for app.auth.permissions -- the centralized permission table.

Every assertion here was verified by actually running is_allowed()/require()
against the real module.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth.permissions import is_allowed, require
from app.models.schemas import MockUser


@pytest.mark.parametrize("role,action,expected", [
    ("operator", "ask", True),
    ("technician", "ask", True),
    ("admin", "ask", True),
    ("operator", "view_devices", True),
    ("operator", "view_incidents", True),
    ("operator", "create_incident", False),
    ("technician", "create_incident", True),
    ("admin", "create_incident", True),
    ("operator", "replace_device", False),
    ("technician", "replace_device", False),
    ("admin", "replace_device", True),
])
def test_is_allowed_matches_the_permission_table(role, action, expected):
    assert is_allowed(role, action) is expected


def test_is_allowed_unknown_action_denies_everyone():
    assert is_allowed("admin", "nonexistent_action") is False


def test_require_dependency_allows_permitted_role():
    dependency = require("replace_device")
    admin = MockUser(id="u-amer", name="Amer", role="admin")

    result = dependency(user=admin)

    assert result is admin


def test_require_dependency_denies_disallowed_role_with_403():
    dependency = require("replace_device")
    operator = MockUser(id="u-omar", name="Omar", role="operator")

    with pytest.raises(HTTPException) as exc_info:
        dependency(user=operator)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["allowed"] is False


def test_require_denial_reason_names_the_action_and_allowed_roles():
    dependency = require("replace_device")
    operator = MockUser(id="u-omar", name="Omar", role="operator")

    with pytest.raises(HTTPException) as exc_info:
        dependency(user=operator)

    reason = exc_info.value.detail["reason"]
    assert "replace_device" in reason
    assert "admin" in reason
    assert "operator" in reason  # names the role that was denied
