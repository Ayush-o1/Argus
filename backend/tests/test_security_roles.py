"""The role/permission model, as pure assertions.

These are unit tests over the permission table rather than HTTP tests, so a
widening of access shows up here as a failing assertion naming the role and the
permission — before anything reaches a route.
"""

from __future__ import annotations

import pytest

from app.security.roles import Permission, Role, has_permission, permissions_for

INTELLIGENCE_READS = [
    Permission.ENTITY_READ,
    Permission.GRAPH_READ,
    Permission.ALERT_READ,
    Permission.CASE_READ,
    Permission.ANALYTICS_READ,
]

WRITES = [
    Permission.ALERT_TRIAGE,
    Permission.CASE_CREATE,
    Permission.CASE_UPDATE,
    Permission.CASE_UPDATE_ANY,
    Permission.EVIDENCE_LINK,
    Permission.ANALYTICS_RUN,
    Permission.SCENARIO_GENERATE,
    Permission.USER_MANAGE,
]


@pytest.mark.parametrize("permission", INTELLIGENCE_READS)
def test_administrator_cannot_read_intelligence(permission: Permission) -> None:
    """Separation of duties: an administrator manages the system, not the data.

    Compromising an admin account must grant disruption, not exfiltration. If
    this test is ever "fixed" by granting the permission, that decision needs to
    be deliberate and argued, not incidental.
    """
    assert not has_permission(Role.ADMINISTRATOR, permission), (
        f"administrator must not hold {permission.value}"
    )


@pytest.mark.parametrize("permission", WRITES)
def test_auditor_cannot_write_anything(permission: Permission) -> None:
    """The account that can see what happened must not be able to change it."""
    assert not has_permission(Role.AUDITOR, permission), f"auditor must not hold {permission.value}"


@pytest.mark.parametrize("permission", WRITES)
def test_viewer_cannot_write_anything(permission: Permission) -> None:
    assert not has_permission(Role.VIEWER, permission), f"viewer must not hold {permission.value}"


def test_viewer_cannot_run_analytics() -> None:
    """Reading results and starting jobs are different privileges.

    The authorization matrix caught this as a live hole: the analytics POST
    routes inherited only the router's read permission, so a read-only role
    could start unbounded GDS work.
    """
    assert has_permission(Role.VIEWER, Permission.ANALYTICS_READ)
    assert not has_permission(Role.VIEWER, Permission.ANALYTICS_RUN)


def test_only_supervisor_and_above_generate_scenarios() -> None:
    """Scenario generation writes to the live graph."""
    allowed = {r for r in Role if has_permission(r, Permission.SCENARIO_GENERATE)}
    assert allowed == {Role.SUPERVISOR}


def test_audit_read_is_limited_to_oversight_roles() -> None:
    allowed = {r for r in Role if has_permission(r, Permission.AUDIT_READ)}
    assert allowed == {Role.SUPERVISOR, Role.ADMINISTRATOR, Role.AUDITOR}


def test_user_management_is_administrator_only() -> None:
    allowed = {r for r in Role if has_permission(r, Permission.USER_MANAGE)}
    assert allowed == {Role.ADMINISTRATOR}


def test_unknown_role_grants_nothing() -> None:
    """Failing closed matters more than a helpful error: a typo in a role name
    must never widen access."""
    assert permissions_for("not-a-real-role") == frozenset()
    assert not has_permission("not-a-real-role", Permission.ENTITY_READ)


def test_every_role_is_in_the_permission_table() -> None:
    """A role with no entry silently grants nothing, which would look like a
    permissions bug rather than a missing table entry."""
    for role in Role:
        assert permissions_for(role), f"{role.value} has no permissions defined"
