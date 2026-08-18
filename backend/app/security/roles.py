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

    # Operating the ingestion pipeline. Read is telemetry — is a feed healthy,
    # is the dead-letter queue growing — and is deliberately separate from
    # reading what flows through it. Manage configures and controls feeds.
    INGEST_READ = "ingest:read"
    INGEST_MANAGE = "ingest:manage"

    # Entity resolution. Reading the review queue is reading intelligence —
    # a candidate pair displays two records' attributes side by side — so it
    # travels with the rest of the read set rather than with pipeline
    # operation, and an administrator does not get it.
    RESOLUTION_READ = "resolution:read"
    # Deciding that two records are the same person, or that they are not.
    # Held from viewers and auditors, and separate from `assertion:write`
    # because a merge changes what every other surface shows about both
    # records, where an assertion adds a claim beside them.
    RESOLUTION_DECIDE = "resolution:decide"
    # Reversing someone else's merge, pinning a cluster's canonical record, and
    # triggering a matcher sweep. Above analyst for the same reason retraction
    # is: undoing a colleague's decision is a judgement about their work.
    RESOLUTION_MANAGE = "resolution:manage"

    # ARGUS's own risk assessment. Reading one is reading intelligence — it
    # states what ARGUS concluded about a named entity and why — so it travels
    # with the read set and an administrator does not get it.
    ASSESSMENT_READ = "assessment:read"
    # Re-running the assessor over the whole graph, and publishing the
    # evaluation of the model against ground truth. Above analyst: a run
    # rewrites what every risk surface in the product displays, and an
    # evaluation report is a published claim about how good ARGUS is.
    ASSESSMENT_RUN = "assessment:run"

    # Correlation between ARGUS's own findings. Reading one is reading
    # intelligence about two named entities at once — arguably more sensitive
    # than either assessment alone, since the claim is that they are connected —
    # so it travels with the read set and an administrator does not get it.
    CORRELATION_READ = "correlation:read"
    # Re-running the correlator, and publishing the evaluation of the model.
    # Above analyst for the same reasons as ASSESSMENT_RUN: a run rewrites every
    # link the product displays, and an evaluation is a published claim about
    # how good ARGUS is at connecting people to each other.
    CORRELATION_RUN = "correlation:run"

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
        # Whether a source has gone quiet changes how its absence should be
        # read: no reports because nothing happened, or no reports because the
        # feed broke. An analyst who cannot tell those apart is being misled by
        # omission, so pipeline health travels with the intelligence it feeds.
        Permission.INGEST_READ,
        # Whether ARGUS thinks two records are one entity changes how every
        # count, connection and timeline on those records should be read. A
        # reader shown "3 accounts" who cannot see that two of the owners are
        # believed to be the same person has been given a misleading number.
        Permission.RESOLUTION_READ,
        # A risk band with no way to see the signals behind it is the number
        # this phase was built to remove. The assessment and its working are
        # one permission, so no reader can be shown the conclusion without
        # access to the evidence for it.
        Permission.ASSESSMENT_READ,
        # A link with no way to see the dimensions behind it is the same defect
        # as a risk band with no signals. The link and its working are one
        # permission, so no reader can be shown "these two are connected"
        # without access to the evidence that says why.
        Permission.CORRELATION_READ,
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
        Permission.RESOLUTION_DECIDE,
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
        Permission.RESOLUTION_DECIDE,
        Permission.RESOLUTION_MANAGE,
        Permission.ASSESSMENT_RUN,
        Permission.CORRELATION_RUN,
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
        Permission.INGEST_MANAGE,
        Permission.SCENARIO_GENERATE,
        Permission.AUDIT_READ,
        Permission.RESOLUTION_DECIDE,
        Permission.RESOLUTION_MANAGE,
        Permission.ASSESSMENT_RUN,
        Permission.CORRELATION_RUN,
    },
    # No intelligence-read permissions. Deliberate: see the module docstring.
    #
    # Ingestion is the one place this needed a finer line. An administrator
    # operates the pipeline — configures a feed, quarantines a bad one, watches
    # for a source going silent — without being able to read what the feed
    # carries. So they hold INGEST_READ and INGEST_MANAGE, and the endpoints
    # that expose an actual payload additionally require ENTITY_READ, which an
    # administrator does not have. Operating the plumbing is not the same
    # permission as reading the water.
    Role.ADMINISTRATOR: frozenset(
        {
            Permission.USER_MANAGE,
            Permission.AUDIT_READ,
            Permission.INGEST_READ,
            Permission.INGEST_MANAGE,
        }
    ),
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
