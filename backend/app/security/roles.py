"""Roles and permissions.

Two separations are deliberate and worth stating, because they are what stops a
single compromised account from being catastrophic (the audit's Scenario 10):

  - **Administrator cannot read intelligence.** They manage users and system
    configuration. An attacker who takes an admin account gets the ability to
    disrupt the system, but not to exfiltrate what it knows.
  - **Auditor cannot mutate anything.** They read the audit log and the records
    it refers to. An attacker cannot both act and erase the evidence of acting
    from a single account.

Permissions are enumerated rather than inferred from role names, so adding a
route forces an explicit decision about who may call it.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    INVESTIGATOR = "investigator"
    SUPERVISOR = "supervisor"
    ADMINISTRATOR = "administrator"
    AUDITOR = "auditor"


class Permission(StrEnum):
    # Reading intelligence
    ENTITY_READ = "entity:read"
    GRAPH_READ = "graph:read"
    ALERT_READ = "alert:read"
    CASE_READ = "case:read"
    ANALYTICS_READ = "analytics:read"
    PROVENANCE_READ = "provenance:read"

    # Acting on intelligence
    ALERT_TRIAGE = "alert:triage"
    CASE_CREATE = "case:create"
    CASE_UPDATE = "case:update"
    CASE_UPDATE_ANY = "case:update:any"  # beyond one's own assignments
    EVIDENCE_LINK = "evidence:link"
    # Recording a judgement under one's own name. Separate from case work
    # because an assertion is an intelligence claim that outlives the case it
    # was made in, and other analysts will rely on it.
    ASSERTION_WRITE = "assertion:write"
    # Withdrawing a belief. Held above analyst deliberately: an analyst who
    # changes their mind supersedes their assertion, which preserves both
    # versions, whereas retraction says the claim should never have been relied
    # on — a judgement about someone's work as much as about the fact.
    ASSERTION_RETRACT = "assertion:retract"

    # Expensive or graph-mutating operations
    ANALYTICS_RUN = "analytics:run"
    SCENARIO_GENERATE = "scenario:generate"

    # Administration and oversight
    USER_MANAGE = "user:manage"
    AUDIT_READ = "audit:read"


_READ_INTELLIGENCE = frozenset(
    {
        Permission.ENTITY_READ,
        Permission.GRAPH_READ,
        Permission.ALERT_READ,
        Permission.CASE_READ,
        Permission.ANALYTICS_READ,
        # Provenance travels with the fact it explains. Anyone permitted to see
        # a value must be permitted to see where it came from — a reader who can
        # see "risk 87.3" but not "assigned by a synthetic source, unrated" has
        # been handed the misleading half.
        Permission.PROVENANCE_READ,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: _READ_INTELLIGENCE,
    Role.ANALYST: _READ_INTELLIGENCE
    | {
        Permission.ALERT_TRIAGE,
        Permission.CASE_CREATE,
        Permission.CASE_UPDATE,
        Permission.EVIDENCE_LINK,
        Permission.ANALYTICS_RUN,
        Permission.ASSERTION_WRITE,
    },
    Role.INVESTIGATOR: _READ_INTELLIGENCE
    | {
        Permission.ALERT_TRIAGE,
        Permission.CASE_CREATE,
        Permission.CASE_UPDATE,
        Permission.CASE_UPDATE_ANY,
        Permission.EVIDENCE_LINK,
        Permission.ANALYTICS_RUN,
        Permission.ASSERTION_WRITE,
        Permission.ASSERTION_RETRACT,
    },
    Role.SUPERVISOR: _READ_INTELLIGENCE
    | {
        Permission.ALERT_TRIAGE,
        Permission.CASE_CREATE,
        Permission.CASE_UPDATE,
        Permission.CASE_UPDATE_ANY,
        Permission.EVIDENCE_LINK,
        Permission.ANALYTICS_RUN,
        Permission.ASSERTION_WRITE,
        Permission.ASSERTION_RETRACT,
        Permission.SCENARIO_GENERATE,
        Permission.AUDIT_READ,
    },
    # No intelligence-read permissions. Deliberate: see the module docstring.
    Role.ADMINISTRATOR: frozenset({Permission.USER_MANAGE, Permission.AUDIT_READ}),
    # Read-only, including the audit log. Deliberately holds no write permission
    # of any kind.
    Role.AUDITOR: _READ_INTELLIGENCE | {Permission.AUDIT_READ},
}


def permissions_for(role: Role | str) -> frozenset[Permission]:
    try:
        return ROLE_PERMISSIONS[Role(role)]
    except ValueError:
        # An unrecognised role grants nothing. Failing closed matters more here
        # than a helpful error: a typo in a role name must not widen access.
        return frozenset()


def has_permission(role: Role | str, permission: Permission) -> bool:
    return permission in permissions_for(role)
