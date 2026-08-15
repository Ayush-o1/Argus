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


def test_a_manage_permission_always_comes_with_its_read() -> None:
    """Pins a defect this test was written in response to.

    Ingest routers declare `ingest:read` at the router level and the stricter
    permission per route. A role granted only `ingest:manage` therefore gets a
    403 on *every* route in the group, including the ones it is supposed to be
    able to call — a lockout that looks like a permission bug in the route but
    is really an incomplete role.

    Supervisor was in exactly that state, and no type check or unit test caught
    it; only driving the live API did. The invariant is general, so it is
    asserted generally rather than for the one case that failed.
    """
    read_for_manage = {
        Permission.INGEST_MANAGE: Permission.INGEST_READ,
        Permission.ASSERTION_WRITE: Permission.PROVENANCE_READ,
        Permission.ASSERTION_RETRACT: Permission.PROVENANCE_READ,
    }
    for role in Role:
        granted = permissions_for(role)
        for manage, read in read_for_manage.items():
            if manage in granted:
                assert read in granted, (
                    f"{role.value} holds {manage.value} but not {read.value}; "
                    "the router-level dependency will deny it every route in that group"
                )


def test_administrator_operates_ingestion_without_reading_intelligence() -> None:
    """The separation, at the one place it needed a finer line.

    An administrator must be able to configure a feed, quarantine a bad one and
    see that a source has gone silent — none of which is reading intelligence.
    Reading a dead-lettered *payload* is, so that route additionally requires
    entity:read, which an administrator does not have.
    """
    admin = permissions_for(Role.ADMINISTRATOR)
    assert Permission.INGEST_READ in admin
    assert Permission.INGEST_MANAGE in admin
    assert Permission.ENTITY_READ not in admin
    assert Permission.PROVENANCE_READ not in admin


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
