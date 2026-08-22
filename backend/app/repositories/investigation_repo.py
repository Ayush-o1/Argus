"""Reads and writes for investigations, findings, evidence links and dissent.

Every mutation here writes the row and its history event **in one transaction**.
That is the whole discipline of this module: if the two could be written
separately, a failure between them would leave an investigation whose current
state no event explains, and `history.verify()` would report a break that was
ARGUS's own fault rather than evidence of interference. A history that cries
wolf is one nobody checks.

All SQL is static. None of it is assembled from a caller-supplied string, which
is what keeps bandit's B608 quiet honestly rather than by annotation — the same
rewrite `alert_repo` went through in Phase 7. Where a field is optionally
updated, the statement carries a `CASE WHEN $flag` rather than a built-up SET
clause.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from app.database.postgres import acquire, transaction
from app.evidence.classification import CLASSIFICATIONS, rank

__all__ = [
    "attach_alert",
    "complete_action",
    "count_investigations",
    "create_investigation",
    "detach_alert",
    "fetch_events",
    "get_investigation",
    "link_entity",
    "list_investigations",
    "outcomes_by_rule",
    "queue_counts",
    "record_action",
    "record_analyst_assessment",
    "record_finding",
    "record_review",
    "standing_analyst_assessments",
    "transition",
    "unlink_entity",
    "update_fields",
    "withdraw_finding",
]


def _jsonable(value: Any) -> Any:
    """Values as they go into a JSONB event column.

    Datetimes become ISO strings. They come back as strings too, which means a
    replayed `closed_at` is a string where the live row holds a datetime — the
    history test compares them after normalising both through here, rather than
    pretending the round trip is lossless.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _decoded(value: Any) -> Any:
    """asyncpg returns JSONB as text unless a codec is registered.

    Decoded at the repository boundary, the convention every other repository
    here follows. Phase 7 learned this the expensive way: the raw text reaches
    the browser as a JSON *string*, and membership tests against it silently
    search a substring instead of throwing.
    """
    return json.loads(value) if isinstance(value, str) else value


async def _write_events(
    conn: Any,
    investigation_id: str,
    event_type: str,
    actor_username: str,
    actor_role: str,
    changes: list[tuple[str, Any, Any]] | None = None,
    note: str | None = None,
    snapshot: dict[str, Any] | None = None,
) -> None:
    """Append history for one action, on an open transaction.

    Takes `conn` rather than acquiring its own, so it cannot be called outside
    the transaction that made the change it describes.
    """
    if snapshot is not None:
        await conn.execute(
            _INSERT_EVENT,
            investigation_id,
            event_type,
            None,
            None,
            json.dumps({k: _jsonable(v) for k, v in snapshot.items()}),
            note,
            actor_username,
            actor_role,
        )
        return

    if not changes:
        await conn.execute(
            _INSERT_EVENT,
            investigation_id,
            event_type,
            None,
            None,
            None,
            note,
            actor_username,
            actor_role,
        )
        return

    for field, old, new in changes:
        await conn.execute(
            _INSERT_EVENT,
            investigation_id,
            event_type,
            field,
            json.dumps(_jsonable(old)),
            json.dumps(_jsonable(new)),
            note,
            actor_username,
            actor_role,
        )


_INSERT_EVENT = """
    INSERT INTO investigation_events
        (investigation_id, event_type, field, old_value, new_value, note,
         actor_username, actor_role)
    VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8)
"""


# ─────────────────────────────────────────────────────────────────────────────
# Creating and reading
# ─────────────────────────────────────────────────────────────────────────────

_INSERT_INVESTIGATION = """
    INSERT INTO investigations
        (investigation_id, inv_ref, title, hypothesis, confidence, confidence_basis,
         opened_by, assigned_to, classification)
    VALUES ($1, 'INV-' || lpad(nextval('investigation_ref_seq')::text, 7, '0'),
            $2, $3, $4, $5, $6, $7, $8)
    RETURNING *
"""


async def create_investigation(
    *,
    title: str,
    hypothesis: str,
    confidence: str,
    confidence_basis: str,
    opened_by: str,
    actor_role: str,
    assigned_to: str | None = None,
    alert_keys: tuple[str, ...] = (),
    classification: str = "internal",
) -> dict[str, Any]:
    """Open an investigation, optionally escalating alerts into it.

    The reference is allocated by the database from a sequence inside the same
    statement that inserts the row. The Neo4j case id this replaces needed a
    lock on a counter node plus a reconciliation against the highest existing id
    to survive concurrent creates (audit B-02, B-22); a sequence needs neither
    and cannot produce a duplicate.
    """
    investigation_id = str(uuid.uuid4())
    async with transaction() as conn:
        row = await conn.fetchrow(
            _INSERT_INVESTIGATION,
            investigation_id,
            title,
            hypothesis,
            confidence,
            confidence_basis,
            opened_by,
            assigned_to,
            classification,
        )
        created = dict(row)

        await _write_events(
            conn,
            investigation_id,
            "opened",
            opened_by,
            actor_role,
            snapshot={
                "title": title,
                "hypothesis": hypothesis,
                "confidence": confidence,
                "confidence_basis": confidence_basis,
                "state": created["state"],
                "assigned_to": assigned_to,
                "outcome": None,
                "outcome_rationale": None,
                "closed_by": None,
                "closed_at": None,
            },
        )

        for key in alert_keys:
            await conn.execute(_ATTACH_ALERT, investigation_id, key, opened_by, "opened with this alert")
            await _write_events(
                conn,
                investigation_id,
                "alert_attached",
                opened_by,
                actor_role,
                note=key,
            )

    return created


_SELECT_INVESTIGATION = "SELECT * FROM investigations WHERE investigation_id = $1"
_SELECT_BY_REF = "SELECT * FROM investigations WHERE inv_ref = $1"


async def get_investigation(ref_or_id: str | uuid.UUID) -> dict[str, Any] | None:
    """One investigation with everything hanging off it.

    Looked up by human reference or uuid, because both appear in URLs and an
    analyst pasting `INV-0000012` should not get a 404 for using the identifier
    the product shows them.

    `uuid.UUID` is accepted as well as `str` because that is what asyncpg hands
    back for the id column, so every caller holding a row from this module has
    one. Coerced rather than rejected: the alternative is each caller
    remembering to stringify, and the one that forgets gets a TypeError from
    deep inside the driver rather than a useful error.
    """
    ref = str(ref_or_id)
    async with acquire() as conn:
        row = await conn.fetchrow(_SELECT_BY_REF, ref)
        if row is None:
            try:
                uuid.UUID(ref)
            except ValueError:
                return None
            row = await conn.fetchrow(_SELECT_INVESTIGATION, ref)
        if row is None:
            return None

        investigation = dict(row)
        iid = investigation["investigation_id"]

        alerts = await conn.fetch(_SELECT_ALERTS, iid)
        entities = await conn.fetch(_SELECT_ENTITIES, iid)
        findings = await conn.fetch(_SELECT_FINDINGS, iid)
        actions = await conn.fetch(_SELECT_ACTIONS, iid)
        assessments = await conn.fetch(_SELECT_INVESTIGATION_ASSESSMENTS, iid)
        reviews = await conn.fetch(_SELECT_REVIEWS, iid)

    investigation["alerts"] = [dict(r) for r in alerts]
    investigation["entities"] = [dict(r) for r in entities]
    investigation["findings"] = [dict(r) for r in findings]
    investigation["actions"] = [dict(r) for r in actions]
    investigation["analyst_assessments"] = [dict(r) for r in assessments]
    investigation["reviews"] = [dict(r) for r in reviews]
    return investigation


# Attached alerts, with enough of each alert to be readable without a second
# call, and detached ones alongside — the detach is part of the reasoning, so
# hiding it would misrepresent how the investigation reached its conclusion.
_SELECT_ALERTS = """
    SELECT ia.alert_key,
           ia.attached_by, ia.attached_at, ia.attach_reason,
           ia.detached_at, ia.detached_by, ia.detach_reason,
           a.rule_id, a.rule_version, a.title, a.priority_band, a.state AS alert_state,
           a.scope
    FROM investigation_alerts ia
    JOIN alerts a ON a.alert_key = ia.alert_key
    WHERE ia.investigation_id = $1
    ORDER BY ia.attached_at
"""

_SELECT_ENTITIES = """
    SELECT link_id, entity_ref, entity_type, reason, linked_by, linked_at,
           removed_at, removed_by, removal_reason
    FROM investigation_entities
    WHERE investigation_id = $1
    ORDER BY linked_at
"""

_SELECT_FINDINGS = """
    SELECT finding_id, statement, confidence, cites,
           author_username, author_role, recorded_at,
           superseded_by, superseded_at,
           withdrawn_at, withdrawn_by, withdrawal_reason
    FROM investigation_findings
    WHERE investigation_id = $1
    ORDER BY recorded_at
"""

_SELECT_ACTIONS = """
    SELECT action_id, description, assigned_to, due_at,
           recorded_by, recorded_at, completed_at, completed_by, completion_note
    FROM investigation_actions
    WHERE investigation_id = $1
    ORDER BY recorded_at
"""

_SELECT_INVESTIGATION_ASSESSMENTS = """
    SELECT analyst_assessment_id, subject_ref, subject_type, analyst_band, rationale,
           confidence, machine_assessment_id, machine_band, machine_fingerprint,
           machine_computed_at, dissents, author_username, author_role, recorded_at,
           superseded_by, superseded_at, withdrawn_at, withdrawn_by, withdrawal_reason
    FROM analyst_assessments
    WHERE investigation_id = $1
    ORDER BY recorded_at
"""


# ─────────────────────────────────────────────────────────────────────────────
# The queue
# ─────────────────────────────────────────────────────────────────────────────

# Classification is filtered by passing the set of codes the reader may see,
# never by comparing the strings — `confidential` sorts before `internal`
# alphabetically, which is the wrong answer and precisely the sort of thing that
# works in testing and fails on the one level that mattered. The ranks live in
# `app/evidence/classification.py` and are turned into a set once, above.
_LIST_ALL = """
    SELECT * FROM investigation_queue
    WHERE classification = ANY($3::text[])
    ORDER BY (state = 'closed'), opened_at DESC
    LIMIT $1 OFFSET $2
"""

_LIST_BY_STATE = """
    SELECT * FROM investigation_queue
    WHERE state = $4 AND classification = ANY($3::text[])
    ORDER BY opened_at DESC
    LIMIT $1 OFFSET $2
"""

_COUNT_ALL = """
    SELECT count(*) AS total FROM investigations WHERE classification = ANY($1::text[])
"""
_COUNT_BY_STATE = """
    SELECT count(*) AS total FROM investigations
     WHERE state = $1 AND classification = ANY($2::text[])
"""


def visible_classifications(clearance: str) -> list[str]:
    """Every classification a holder of `clearance` may see.

    Raises on an unrecognised clearance rather than returning an empty list. A
    typo that silently shows nothing reads as "there are no investigations",
    which is a lie the reader has no way to detect.
    """
    ceiling = rank(clearance)
    return [c.code for c in CLASSIFICATIONS if c.rank <= ceiling]


async def list_investigations(
    *, state: str | None, limit: int, offset: int, max_classification: str
) -> list[dict[str, Any]]:
    allowed = visible_classifications(max_classification)
    async with acquire() as conn:
        if state is None:
            rows = await conn.fetch(_LIST_ALL, limit, offset, allowed)
        else:
            rows = await conn.fetch(_LIST_BY_STATE, limit, offset, allowed, state)
    return [dict(r) for r in rows]


async def count_investigations(state: str | None, max_classification: str) -> int:
    """The true total within the reader's clearance.

    A separate count rather than `len()` of the page — the defect the audit found
    on four surfaces (B-04, B-05) and Phase 7 found once more in its own code.
    Bounded by clearance for a second reason: a total that included investigations
    the reader cannot open would tell them exactly how much is being withheld.
    """
    allowed = visible_classifications(max_classification)
    async with acquire() as conn:
        if state is None:
            row = await conn.fetchrow(_COUNT_ALL, allowed)
        else:
            row = await conn.fetchrow(_COUNT_BY_STATE, state, allowed)
    return int(row["total"]) if row else 0


_QUEUE_COUNTS = "SELECT state, count(*) AS n FROM investigations GROUP BY state"
_OUTCOME_COUNTS = """
    SELECT outcome, count(*) AS n FROM investigations
    WHERE outcome IS NOT NULL GROUP BY outcome
"""


async def queue_counts() -> dict[str, dict[str, int]]:
    """Counts by state and by outcome, for the dashboard.

    Grouped queries rather than one count per bucket, so the numbers sum to the
    population by construction — the same correction migration 006's band
    distribution needed.
    """
    async with acquire() as conn:
        states = await conn.fetch(_QUEUE_COUNTS)
        outcomes = await conn.fetch(_OUTCOME_COUNTS)
    return {
        "by_state": {r["state"]: int(r["n"]) for r in states},
        "by_outcome": {r["outcome"]: int(r["n"]) for r in outcomes},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Changing an investigation
# ─────────────────────────────────────────────────────────────────────────────

# One static statement covering every editable field, each behind its own flag.
# `confidence` and `confidence_basis` share a flag deliberately: a confidence
# level whose stated basis belongs to the previous level is worse than either
# alone, so the pair moves together or not at all.
_UPDATE_FIELDS = """
    UPDATE investigations
       SET title            = CASE WHEN $2 THEN $3 ELSE title END,
           hypothesis       = CASE WHEN $4 THEN $5 ELSE hypothesis END,
           confidence       = CASE WHEN $6 THEN $7 ELSE confidence END,
           confidence_basis = CASE WHEN $6 THEN $8 ELSE confidence_basis END,
           assigned_to      = CASE WHEN $9 THEN $10 ELSE assigned_to END
     WHERE investigation_id = $1
    RETURNING *
"""


async def update_fields(
    *,
    investigation_id: str,
    actor_username: str,
    actor_role: str,
    title: str | None = None,
    hypothesis: str | None = None,
    confidence: str | None = None,
    confidence_basis: str | None = None,
    assigned_to: str | None = None,
    set_assigned: bool = False,
    note: str | None = None,
) -> dict[str, Any] | None:
    """Apply an edit and record exactly what changed.

    `set_assigned` exists because null is a meaningful value for `assigned_to`:
    unassigning is an action someone takes, and it has to be distinguishable
    from "this request did not mention assignment".
    """
    async with transaction() as conn:
        before = await conn.fetchrow(_SELECT_INVESTIGATION, investigation_id)
        if before is None:
            return None

        row = await conn.fetchrow(
            _UPDATE_FIELDS,
            investigation_id,
            title is not None,
            title,
            hypothesis is not None,
            hypothesis,
            confidence is not None,
            confidence,
            confidence_basis,
            set_assigned,
            assigned_to,
        )
        after = dict(row)

        changes = [
            (field, before[field], after[field])
            for field in ("title", "hypothesis", "confidence", "confidence_basis", "assigned_to")
            if before[field] != after[field]
        ]
        if changes:
            await _write_events(
                conn,
                investigation_id,
                "field_changed",
                actor_username,
                actor_role,
                changes=changes,
                note=note,
            )
    return after


# State changes. Closure and reopening are separate statements rather than one
# with more flags, because they set disjoint columns and a single statement
# would have to express "clear the outcome unless closing" — a rule easy to
# state and easy to get backwards.
_CLOSE = """
    UPDATE investigations
       SET state = 'closed', outcome = $2, outcome_rationale = $3,
           closed_by = $4, closed_at = now()
     WHERE investigation_id = $1 AND state = $5
    RETURNING *
"""

_REOPEN = """
    UPDATE investigations
       SET state = 'active', outcome = NULL, outcome_rationale = NULL,
           closed_by = NULL, closed_at = NULL
     WHERE investigation_id = $1 AND state = 'closed'
    RETURNING *
"""

_SET_STATE = """
    UPDATE investigations SET state = $2
     WHERE investigation_id = $1 AND state = $3
    RETURNING *
"""


async def transition(
    *,
    investigation_id: str,
    to_state: str,
    actor_username: str,
    actor_role: str,
    outcome: str | None = None,
    outcome_rationale: str | None = None,
    note: str | None = None,
) -> dict[str, Any] | None:
    """Move an investigation between states, recording who and why.

    Guarded on the state read a moment earlier (`AND state = $current`), so two
    analysts closing the same investigation at once produce one closure and one
    "it moved under you" rather than two closures with one silently overwriting
    the other's outcome. The same guard `alert_repo.apply_transition` uses.

    Reopening clears the outcome. That is a real loss of the current row's
    content and it is deliberate: an investigation that is open again does not
    have a conclusion, and leaving a stale one would let the queue show `active`
    beside `confirmed`. Nothing is lost — the closure, its outcome and its
    rationale are all in the event log, and `history.reconstruct()` shows them
    at the time they were true. Reviews are untouched: each one records the
    outcome it was commenting on, so an old review does not silently reattach
    itself to a new verdict.
    """
    async with transaction() as conn:
        before = await conn.fetchrow(_SELECT_INVESTIGATION, investigation_id)
        if before is None:
            return None
        current = before["state"]

        if to_state == "closed":
            row = await conn.fetchrow(_CLOSE, investigation_id, outcome, outcome_rationale, actor_username, current)
        elif current == "closed":
            row = await conn.fetchrow(_REOPEN, investigation_id)
        else:
            row = await conn.fetchrow(_SET_STATE, investigation_id, to_state, current)

        if row is None:
            # The guard did not match: someone else moved it between the read
            # and the write.
            return None
        after = dict(row)

        changes = [
            (field, before[field], after[field])
            for field in (
                "state",
                "outcome",
                "outcome_rationale",
                "closed_by",
                "closed_at",
            )
            if before[field] != after[field]
        ]
        event_type = "closed" if to_state == "closed" else ("reopened" if current == "closed" else "field_changed")
        await _write_events(
            conn,
            investigation_id,
            event_type,
            actor_username,
            actor_role,
            changes=changes,
            note=note,
        )
    return after


# A review is inserted only if the investigation is closed AND the reviewer is
# not the person who closed it. Both conditions live in the statement rather
# than in a Python guard, so neither can be skipped by a future caller — and the
# self-review rule in particular is the kind of thing an "internal" helper
# quietly bypasses.
#
# The self-review check was added after a live walkthrough in which the analyst
# who closed an investigation reviewed their own conclusion and the API accepted
# it. An investigator holds both INVESTIGATION_UPDATE and INVESTIGATION_REVIEW,
# so permissions alone were never going to stop that.
_INSERT_REVIEW = """
    INSERT INTO investigation_reviews
        (investigation_id, reviewer, reviewer_role, concurs, note, outcome_reviewed)
    SELECT i.investigation_id, $2, $3, $4, $5, i.outcome
      FROM investigations i
     WHERE i.investigation_id = $1
       AND i.state = 'closed'
       AND i.closed_by IS DISTINCT FROM $2
    RETURNING review_id, reviewed_at, outcome_reviewed
"""


async def record_review(
    *,
    investigation_id: str,
    reviewer: str,
    actor_role: str,
    concurs: bool,
    note: str | None,
) -> dict[str, Any] | None:
    """Record an independent judgement about a closed investigation.

    Appends. It does not, and cannot, modify an earlier review — the table has
    no UPDATE grant and a trigger behind that. The first version of this stored
    the review in four columns on the investigation, and a second reviewer
    silently erased the first one's recorded dissent, which is precisely the
    failure `analyst_assessments` was designed to prevent one level down.

    The outcome is never changed by a review. A supervisor who thinks the
    verdict is wrong records that they think it is wrong; if they want a
    different verdict on the record, the route is to reopen the investigation
    and close it again, and the log then holds both closures and the review
    between them.

    Returns None when the investigation is not closed, does not exist, or the
    reviewer is the person who closed it.
    """
    async with transaction() as conn:
        row = await conn.fetchrow(
            _INSERT_REVIEW, investigation_id, reviewer, actor_role, concurs, note
        )
        if row is None:
            return None
        await _write_events(
            conn,
            investigation_id,
            "reviewed",
            reviewer,
            actor_role,
            note=(
                f"{'concurs' if concurs else 'does not concur'} with "
                f"{row['outcome_reviewed']}" + (f": {note}" if note else "")
            ),
        )
        return {
            "review_id": row["review_id"],
            "reviewer": reviewer,
            "reviewer_role": actor_role,
            "concurs": concurs,
            "note": note,
            "reviewed_at": row["reviewed_at"],
            "outcome_reviewed": row["outcome_reviewed"],
        }


_SELECT_REVIEWS = """
    SELECT review_id, reviewer, reviewer_role, concurs, note, reviewed_at, outcome_reviewed
    FROM investigation_reviews
    WHERE investigation_id = $1
    ORDER BY reviewed_at
"""


# ─────────────────────────────────────────────────────────────────────────────
# Evidence
# ─────────────────────────────────────────────────────────────────────────────

_ATTACH_ALERT = """
    INSERT INTO investigation_alerts (investigation_id, alert_key, attached_by, attach_reason)
    VALUES ($1, $2, $3, $4)
"""

_DETACH_ALERT = """
    UPDATE investigation_alerts
       SET detached_at = now(), detached_by = $3, detach_reason = $4
     WHERE investigation_id = $1 AND alert_key = $2 AND detached_at IS NULL
    RETURNING link_id
"""


async def attach_alert(
    *,
    investigation_id: str,
    alert_key: str,
    actor_username: str,
    actor_role: str,
    reason: str = "",
) -> bool:
    async with transaction() as conn:
        await conn.execute(_ATTACH_ALERT, investigation_id, alert_key, actor_username, reason)
        await _write_events(
            conn,
            investigation_id,
            "alert_attached",
            actor_username,
            actor_role,
            note=f"{alert_key}: {reason}" if reason else alert_key,
        )
    return True


async def detach_alert(
    *,
    investigation_id: str,
    alert_key: str,
    actor_username: str,
    actor_role: str,
    reason: str,
) -> bool:
    async with transaction() as conn:
        row = await conn.fetchrow(_DETACH_ALERT, investigation_id, alert_key, actor_username, reason)
        if row is None:
            return False
        await _write_events(
            conn,
            investigation_id,
            "alert_detached",
            actor_username,
            actor_role,
            note=f"{alert_key}: {reason}",
        )
    return True


_LINK_ENTITY = """
    INSERT INTO investigation_entities
        (investigation_id, entity_ref, entity_type, reason, linked_by)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING link_id
"""

_UNLINK_ENTITY = """
    UPDATE investigation_entities
       SET removed_at = now(), removed_by = $3, removal_reason = $4
     WHERE investigation_id = $1 AND entity_ref = $2 AND removed_at IS NULL
    RETURNING link_id
"""


async def link_entity(
    *,
    investigation_id: str,
    entity_ref: str,
    entity_type: str,
    reason: str,
    actor_username: str,
    actor_role: str,
) -> bool:
    async with transaction() as conn:
        await conn.fetchrow(_LINK_ENTITY, investigation_id, entity_ref, entity_type, reason, actor_username)
        await _write_events(
            conn,
            investigation_id,
            "entity_linked",
            actor_username,
            actor_role,
            note=f"{entity_ref}: {reason}",
        )
    return True


async def unlink_entity(
    *,
    investigation_id: str,
    entity_ref: str,
    actor_username: str,
    actor_role: str,
    reason: str,
) -> bool:
    """Tombstone an evidence link (audit G-11).

    Unlike the Neo4j implementation this replaces, re-linking later does **not**
    reuse this row and clear the tombstone — it inserts a new one. So the record
    of the removal, and of who made it, survives being reversed.
    """
    async with transaction() as conn:
        row = await conn.fetchrow(_UNLINK_ENTITY, investigation_id, entity_ref, actor_username, reason)
        if row is None:
            return False
        await _write_events(
            conn,
            investigation_id,
            "entity_unlinked",
            actor_username,
            actor_role,
            note=f"{entity_ref}: {reason}",
        )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Findings and actions
# ─────────────────────────────────────────────────────────────────────────────

_INSERT_FINDING = """
    INSERT INTO investigation_findings
        (finding_id, investigation_id, statement, confidence, cites,
         author_username, author_role)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    RETURNING *
"""

_SUPERSEDE_FINDING = """
    UPDATE investigation_findings
       SET superseded_by = $2, superseded_at = now()
     WHERE finding_id = $1 AND superseded_at IS NULL AND withdrawn_at IS NULL
    RETURNING finding_id
"""

_WITHDRAW_FINDING = """
    UPDATE investigation_findings
       SET withdrawn_at = now(), withdrawn_by = $2, withdrawal_reason = $3
     WHERE finding_id = $1 AND investigation_id = $4 AND withdrawn_at IS NULL
    RETURNING finding_id
"""


async def record_finding(
    *,
    investigation_id: str,
    statement: str,
    confidence: str,
    cites: list[str],
    author_username: str,
    author_role: str,
    supersedes: str | None = None,
) -> dict[str, Any]:
    """Record a finding, optionally replacing an earlier one.

    Supersession is an insert plus a pointer, never an edit. How an analyst's
    understanding changed over the course of an investigation is part of the
    record, and rewriting the earlier statement would delete it.
    """
    finding_id = str(uuid.uuid4())
    async with transaction() as conn:
        row = await conn.fetchrow(
            _INSERT_FINDING,
            finding_id,
            investigation_id,
            statement,
            confidence,
            cites,
            author_username,
            author_role,
        )
        if supersedes is not None:
            await conn.fetchrow(_SUPERSEDE_FINDING, supersedes, finding_id)
        await _write_events(
            conn,
            investigation_id,
            "finding_recorded",
            author_username,
            author_role,
            note=statement,
        )
    return dict(row)


async def withdraw_finding(
    *,
    investigation_id: str,
    finding_id: str,
    actor_username: str,
    actor_role: str,
    reason: str,
) -> bool:
    async with transaction() as conn:
        row = await conn.fetchrow(_WITHDRAW_FINDING, finding_id, actor_username, reason, investigation_id)
        if row is None:
            return False
        await _write_events(conn, investigation_id, "finding_withdrawn", actor_username, actor_role, note=reason)
    return True


_INSERT_ACTION = """
    INSERT INTO investigation_actions
        (action_id, investigation_id, description, assigned_to, due_at, recorded_by)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING *
"""

_COMPLETE_ACTION = """
    UPDATE investigation_actions
       SET completed_at = now(), completed_by = $2, completion_note = $3
     WHERE action_id = $1 AND investigation_id = $4 AND completed_at IS NULL
    RETURNING action_id
"""


async def record_action(
    *,
    investigation_id: str,
    description: str,
    assigned_to: str | None,
    due_at: datetime | None,
    actor_username: str,
    actor_role: str,
) -> dict[str, Any]:
    """Record a next action.

    `due_at` is a date somebody wrote down. Nothing in ARGUS watches it — there
    is no scheduler, no reminder and no escalation behind this column, and the
    API says so in the response rather than letting a date in a UI imply a
    mechanism that does not exist.
    """
    action_id = str(uuid.uuid4())
    async with transaction() as conn:
        row = await conn.fetchrow(
            _INSERT_ACTION,
            action_id,
            investigation_id,
            description,
            assigned_to,
            due_at,
            actor_username,
        )
        await _write_events(
            conn,
            investigation_id,
            "action_recorded",
            actor_username,
            actor_role,
            note=description,
        )
    return dict(row)


async def complete_action(
    *,
    investigation_id: str,
    action_id: str,
    actor_username: str,
    actor_role: str,
    note: str | None,
) -> bool:
    async with transaction() as conn:
        row = await conn.fetchrow(_COMPLETE_ACTION, action_id, actor_username, note, investigation_id)
        if row is None:
            return False
        await _write_events(conn, investigation_id, "action_completed", actor_username, actor_role, note=note)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Analyst assessments — the dissent record (audit G-15)
# ─────────────────────────────────────────────────────────────────────────────

# The machine's current answer for a subject, read so it can be frozen into the
# dissent. Selected inside the same transaction as the insert, so the snapshot
# is of the assessment that was current at the moment the judgement was made
# rather than one an assessment run replaced in between.
_CURRENT_MACHINE_ASSESSMENT = """
    SELECT assessment_id, band, model_fingerprint, computed_at
    FROM assessment_current
    WHERE subject_ref = $1
"""

_INSERT_ANALYST_ASSESSMENT = """
    INSERT INTO analyst_assessments
        (analyst_assessment_id, subject_ref, subject_type, analyst_band, rationale,
         confidence, machine_assessment_id, machine_band, machine_fingerprint,
         machine_computed_at, investigation_id, author_username, author_role)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
    RETURNING *
"""

# Supersede whatever this author previously said about the same subject. An
# analyst who records a second judgement is changing their mind, not holding two
# beliefs at once — but the earlier one stays on the record, superseded rather
# than edited, because when they changed their mind is itself informative.
_SUPERSEDE_PRIOR = """
    UPDATE analyst_assessments
       SET superseded_by = $1, superseded_at = now()
     WHERE subject_ref = $2 AND author_username = $3
       AND analyst_assessment_id <> $1
       AND superseded_at IS NULL AND withdrawn_at IS NULL
"""


async def record_analyst_assessment(
    *,
    subject_ref: str,
    subject_type: str,
    analyst_band: str,
    rationale: str,
    confidence: str,
    author_username: str,
    author_role: str,
    investigation_id: str | None = None,
) -> dict[str, Any]:
    """Record what an analyst concluded about a subject, beside what ARGUS did.

    **Nothing here writes to `assessments` or `assessment_current`.** That is the
    property this function exists to provide: an analyst who disagrees with the
    model gets their judgement recorded next to it, attributed, and the model's
    output is left exactly as it was. Both are then visible, and a reader can
    see that there is a disagreement at all — which is impossible in a system
    where the human simply overwrites the machine.
    """
    analyst_assessment_id = str(uuid.uuid4())
    async with transaction() as conn:
        machine = await conn.fetchrow(_CURRENT_MACHINE_ASSESSMENT, subject_ref)

        row = await conn.fetchrow(
            _INSERT_ANALYST_ASSESSMENT,
            analyst_assessment_id,
            subject_ref,
            subject_type,
            analyst_band,
            rationale,
            confidence,
            machine["assessment_id"] if machine else None,
            machine["band"] if machine else None,
            machine["model_fingerprint"] if machine else None,
            machine["computed_at"] if machine else None,
            investigation_id,
            author_username,
            author_role,
        )
        await conn.execute(_SUPERSEDE_PRIOR, analyst_assessment_id, subject_ref, author_username)
        if investigation_id is not None:
            await _write_events(
                conn,
                investigation_id,
                "assessment_recorded",
                author_username,
                author_role,
                note=f"{subject_ref}: {analyst_band}",
            )
    return dict(row)


_STANDING_FOR_SUBJECT = """
    SELECT analyst_assessment_id, subject_ref, subject_type, analyst_band, rationale,
           confidence, machine_assessment_id, machine_band, machine_fingerprint,
           machine_computed_at, dissents, investigation_id,
           author_username, author_role, recorded_at
    FROM analyst_assessments_standing
    WHERE subject_ref = ANY($1::text[])
    ORDER BY subject_ref, recorded_at DESC
"""


async def standing_analyst_assessments(refs: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Standing analyst judgements for a set of subjects, keyed by subject.

    Returns every standing judgement rather than "the latest", because two
    analysts may hold different views of the same subject and collapsing them to
    one would be the system choosing a winner. The assessment surface shows all
    of them.
    """
    if not refs:
        return {}
    async with acquire() as conn:
        rows = await conn.fetch(_STANDING_FOR_SUBJECT, refs)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["subject_ref"], []).append(dict(row))
    return grouped


# ─────────────────────────────────────────────────────────────────────────────
# History and outcomes
# ─────────────────────────────────────────────────────────────────────────────

_SELECT_EVENTS = """
    SELECT event_id, event_type, field, old_value, new_value, note,
           actor_username, actor_role, occurred_at
    FROM investigation_events
    WHERE investigation_id = $1
    ORDER BY occurred_at, event_id
"""


async def fetch_events(investigation_id: str) -> list[dict[str, Any]]:
    async with acquire() as conn:
        rows = await conn.fetch(_SELECT_EVENTS, investigation_id)
    events = []
    for row in rows:
        event = dict(row)
        event["old_value"] = _decoded(event["old_value"])
        event["new_value"] = _decoded(event["new_value"])
        events.append(event)
    return events


_OUTCOMES_BY_RULE = """
    SELECT rule_id, rule_version, outcome, investigations, alerts
    FROM investigation_outcomes_by_rule
    ORDER BY rule_id, rule_version, outcome
"""


async def outcomes_by_rule() -> list[dict[str, Any]]:
    """Closed-investigation outcomes joined back to the rules that raised them.

    Counts only. No rate is computed here and none should be: a precision over
    three closed investigations has the same number of digits as one over three
    thousand, and the pair (numerator, denominator) is the only honest form
    until there are enough outcomes for a rate to mean anything. That judgement
    belongs to the calibration phase, with the denominators in front of it.
    """
    async with acquire() as conn:
        rows = await conn.fetch(_OUTCOMES_BY_RULE)
    return [dict(r) for r in rows]
