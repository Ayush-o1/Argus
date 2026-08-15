"""Reads and writes for the provenance layer.

The queries here are the ones that answer the questions the audit found ARGUS
could not answer at all: where did this come from, how well is it supported,
what disagrees with it, and what did we believe last Tuesday.

Two rules hold throughout this module:

  1. **Nothing resolves a conflict.** `conflicts_for` returns every side. There
     is no ordering by rating, no "best" assertion, and no tie-break. Choosing
     silently would hide the disagreement from the analyst, who is the only
     party equipped to resolve it.
  2. **Nothing combines the two rating axes.** Reliability and credibility are
     carried separately from the database to the response model.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

import asyncpg

from app.database.postgres import acquire
from app.models.provenance import (
    Assertion,
    Conflict,
    Corroboration,
    Credibility,
    EpistemicKind,
    EvidenceRef,
    Observation,
    Rating,
    Reliability,
    Source,
    SourceType,
)


def canonical_hash(payload: dict[str, Any]) -> str:
    """SHA-256 over a canonical rendering of the payload.

    Sorted keys and fixed separators, so the same content produces the same hash
    regardless of dict ordering at write time — which is what makes ingestion
    idempotent rather than merely usually-idempotent.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Sources
# ─────────────────────────────────────────────────────────────────────────────


def _source_from_row(row: asyncpg.Record) -> Source:
    return Source(
        source_id=row["source_id"],
        name=row["name"],
        source_type=SourceType(row["source_type"]),
        description=row["description"],
        reliability=Reliability(row["reliability"]),
        reliability_basis=row["reliability_basis"],
        is_synthetic=row["is_synthetic"],
        independence_group=row["independence_group"],
        staleness_hours=row["staleness_hours"],
        is_active=row["is_active"],
        registered_at=row["registered_at"],
    )


async def register_source(source: Source, conn: asyncpg.Connection | None = None) -> None:
    """Insert a source if it is not already registered.

    Idempotent so startup registration of ARGUS's own internal sources can run
    on every boot. Existing rows are left untouched: a reliability rating is an
    analytic judgement, and silently overwriting one on deploy would change what
    every downstream assertion means without anybody deciding to.
    """
    sql = """
        INSERT INTO sources (
            source_id, name, source_type, description,
            reliability, reliability_basis, is_synthetic,
            independence_group, staleness_hours, is_active
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ON CONFLICT (source_id) DO NOTHING
    """
    args = (
        source.source_id,
        source.name,
        source.source_type.value,
        source.description,
        source.reliability.value,
        source.reliability_basis,
        source.is_synthetic,
        source.independence_group,
        source.staleness_hours,
        source.is_active,
    )
    if conn is not None:
        await conn.execute(sql, *args)
        return
    async with acquire() as own:
        await own.execute(sql, *args)


async def list_sources() -> list[Source]:
    async with acquire() as conn:
        rows = await conn.fetch("SELECT * FROM sources ORDER BY source_id")
    return [_source_from_row(row) for row in rows]


async def get_source(source_id: str) -> Source | None:
    async with acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM sources WHERE source_id = $1", source_id)
    return _source_from_row(row) if row else None


# ─────────────────────────────────────────────────────────────────────────────
# Observations
# ─────────────────────────────────────────────────────────────────────────────


async def record_observation(
    *,
    source_id: str,
    content_type: str,
    payload: dict[str, Any],
    subjects: list[tuple[str, str]],
    occurred_at: datetime | None = None,
    collected_at: datetime | None = None,
    provenance_note: str | None = None,
    supersedes: str | None = None,
    conn: asyncpg.Connection | None = None,
) -> tuple[str, bool]:
    """Record what a source said. Returns (observation_id, was_created).

    Idempotent on (source_id, content_hash): the same payload from the same
    source twice yields one observation. Re-ingesting a feed must not inflate
    the corroboration count, or replaying a file would look like independent
    confirmation.

    `subjects` is a list of (human_id, graph_label) pairs — what the observation
    is about.
    """
    if conn is not None:
        return await _record_observation_on(
            conn,
            source_id=source_id,
            content_type=content_type,
            payload=payload,
            subjects=subjects,
            occurred_at=occurred_at,
            collected_at=collected_at,
            provenance_note=provenance_note,
            supersedes=supersedes,
        )
    async with acquire() as own:
        return await _record_observation_on(
            own,
            source_id=source_id,
            content_type=content_type,
            payload=payload,
            subjects=subjects,
            occurred_at=occurred_at,
            collected_at=collected_at,
            provenance_note=provenance_note,
            supersedes=supersedes,
        )


async def _record_observation_on(
    conn: asyncpg.Connection,
    *,
    source_id: str,
    content_type: str,
    payload: dict[str, Any],
    subjects: list[tuple[str, str]],
    occurred_at: datetime | None,
    collected_at: datetime | None,
    provenance_note: str | None,
    supersedes: str | None,
) -> tuple[str, bool]:
    content_hash = canonical_hash(payload)
    new_id = uuid.uuid4()

    async with conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO observations (
                observation_id, source_id, content_type, payload, content_hash,
                occurred_at, collected_at, supersedes, provenance_note
            ) VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9)
            ON CONFLICT (source_id, content_hash) DO NOTHING
            RETURNING observation_id
            """,
            new_id,
            source_id,
            content_type,
            json.dumps(payload, default=str),
            content_hash,
            occurred_at,
            collected_at,
            uuid.UUID(supersedes) if supersedes else None,
            provenance_note,
        )

        if row is None:
            existing = await conn.fetchval(
                "SELECT observation_id FROM observations WHERE source_id = $1 AND content_hash = $2",
                source_id,
                content_hash,
            )
            return str(existing), False

        observation_id = row["observation_id"]
        for subject_ref, subject_type in subjects:
            await conn.execute(
                """
                INSERT INTO observation_subjects (observation_id, subject_ref, subject_type)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
                """,
                observation_id,
                subject_ref,
                subject_type,
            )
        return str(observation_id), True


_OBSERVATION_SELECT = """
    SELECT o.observation_id, o.source_id, o.content_type, o.payload, o.content_hash,
           o.occurred_at, o.collected_at, o.recorded_at, o.supersedes, o.provenance_note,
           s.name AS source_name, s.reliability AS source_reliability,
           s.is_synthetic AS source_is_synthetic,
           (SELECT array_agg(os2.subject_ref) FROM observation_subjects os2
             WHERE os2.observation_id = o.observation_id) AS subjects
      FROM observations o
      JOIN sources s ON s.source_id = o.source_id
"""


def _observation_from_row(row: asyncpg.Record) -> Observation:
    return Observation(
        observation_id=str(row["observation_id"]),
        source_id=row["source_id"],
        source_name=row["source_name"],
        source_reliability=Reliability(row["source_reliability"]),
        source_is_synthetic=row["source_is_synthetic"],
        content_type=row["content_type"],
        payload=json.loads(row["payload"]),
        content_hash=row["content_hash"],
        occurred_at=row["occurred_at"],
        collected_at=row["collected_at"],
        recorded_at=row["recorded_at"],
        supersedes=str(row["supersedes"]) if row["supersedes"] else None,
        provenance_note=row["provenance_note"],
        subjects=list(row["subjects"] or []),
    )


async def count_observations_for_subject(
    subject_ref: str, *, as_of: datetime | None = None
) -> int:
    """The denominator. A list that may be truncated must be able to say so —
    the same rule Phase 0 established with `Aggregate`, applied here so a
    provenance view can never present a partial set as the whole."""
    async with acquire() as conn:
        return (
            await conn.fetchval(
                """
                SELECT count(*)
                  FROM observations o
                  JOIN observation_subjects os ON os.observation_id = o.observation_id
                 WHERE os.subject_ref = $1
                   AND ($2::timestamptz IS NULL OR o.recorded_at <= $2)
                """,
                subject_ref,
                as_of,
            )
            or 0
        )


async def observations_for_subject(
    subject_ref: str, *, as_of: datetime | None = None, limit: int = 50
) -> list[Observation]:
    """Observations about one entity, newest first.

    `as_of` filters on `recorded_at` — when ARGUS learned it — which is the
    right axis for "what did we know at the time". Filtering on `occurred_at`
    would answer a different and much less useful question after an incident.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            _OBSERVATION_SELECT
            + """
             JOIN observation_subjects os ON os.observation_id = o.observation_id
            WHERE os.subject_ref = $1
              AND ($2::timestamptz IS NULL OR o.recorded_at <= $2)
            ORDER BY o.recorded_at DESC
            LIMIT $3
            """,
            subject_ref,
            as_of,
            limit,
        )
    return [_observation_from_row(row) for row in rows]


async def existing_observation_ids(observation_ids: list[str]) -> set[str]:
    """Which of these observation ids exist. One query, not one per id.

    `create_assertion` accepts up to 50 supporting and 50 contradicting
    references, and validating them individually meant up to a hundred queries —
    each with a source join — on a single request.
    """
    parsed: list[uuid.UUID] = []
    for candidate in observation_ids:
        try:
            parsed.append(uuid.UUID(candidate))
        except ValueError:
            # Not a uuid, so it cannot exist. Left out rather than raised, so
            # the caller reports every unknown reference at once.
            continue
    if not parsed:
        return set()

    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT observation_id FROM observations WHERE observation_id = ANY($1::uuid[])",
            parsed,
        )
    return {str(row["observation_id"]) for row in rows}


async def get_observation(observation_id: str) -> Observation | None:
    try:
        parsed = uuid.UUID(observation_id)
    except ValueError:
        return None
    async with acquire() as conn:
        row = await conn.fetchrow(
            _OBSERVATION_SELECT + " WHERE o.observation_id = $1", parsed
        )
    return _observation_from_row(row) if row else None


# ─────────────────────────────────────────────────────────────────────────────
# Assertions
# ─────────────────────────────────────────────────────────────────────────────


async def record_assertion(
    *,
    subject_ref: str,
    subject_type: str,
    predicate: str,
    object_value: Any,
    epistemic_kind: EpistemicKind,
    rating: Rating,
    method: str,
    asserted_by: str,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    note: str | None = None,
    evidence: list[tuple[str, str]] | None = None,
    supersedes: str | None = None,
    conn: asyncpg.Connection | None = None,
) -> str:
    """Record a belief. Returns the new assertion's id.

    `evidence` is a list of (observation_id, stance) pairs, stance being
    'supports' or 'contradicts'. Contradicting evidence is recorded against the
    assertion it argues with, not discarded — an assertion whose counter-evidence
    was dropped looks better supported than it is.

    `supersedes` marks a prior assertion as replaced. The prior one is not
    deleted or edited beyond its two supersession columns, so the history of
    what ARGUS believed survives the update.
    """
    if conn is not None:
        return await _record_assertion_on(
            conn,
            subject_ref=subject_ref,
            subject_type=subject_type,
            predicate=predicate,
            object_value=object_value,
            epistemic_kind=epistemic_kind,
            rating=rating,
            method=method,
            asserted_by=asserted_by,
            valid_from=valid_from,
            valid_until=valid_until,
            note=note,
            evidence=evidence,
            supersedes=supersedes,
        )
    async with acquire() as own:
        return await _record_assertion_on(
            own,
            subject_ref=subject_ref,
            subject_type=subject_type,
            predicate=predicate,
            object_value=object_value,
            epistemic_kind=epistemic_kind,
            rating=rating,
            method=method,
            asserted_by=asserted_by,
            valid_from=valid_from,
            valid_until=valid_until,
            note=note,
            evidence=evidence,
            supersedes=supersedes,
        )


async def _record_assertion_on(
    conn: asyncpg.Connection,
    *,
    subject_ref: str,
    subject_type: str,
    predicate: str,
    object_value: Any,
    epistemic_kind: EpistemicKind,
    rating: Rating,
    method: str,
    asserted_by: str,
    valid_from: datetime | None,
    valid_until: datetime | None,
    note: str | None,
    evidence: list[tuple[str, str]] | None,
    supersedes: str | None,
) -> str:
    assertion_id = uuid.uuid4()

    async with conn.transaction():
        await conn.execute(
            """
            INSERT INTO assertions (
                assertion_id, subject_ref, subject_type, predicate, object_value,
                epistemic_kind, reliability, credibility, method, asserted_by,
                valid_from, valid_until, note
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
            assertion_id,
            subject_ref,
            subject_type,
            predicate,
            json.dumps(object_value, default=str),
            epistemic_kind.value,
            rating.reliability.value,
            rating.credibility.value,
            method,
            asserted_by,
            valid_from,
            valid_until,
            note,
        )

        for observation_id, stance in evidence or []:
            await conn.execute(
                """
                INSERT INTO assertion_evidence (assertion_id, observation_id, stance)
                VALUES ($1, $2, $3)
                ON CONFLICT DO NOTHING
                """,
                assertion_id,
                uuid.UUID(observation_id),
                stance,
            )

        if supersedes is not None:
            # Guarded so a second supersession of the same assertion cannot
            # silently overwrite the first. The trigger rejects it too; this
            # turns a database exception into a no-op with a checkable result.
            await conn.execute(
                """
                UPDATE assertions
                   SET superseded_by = $1, superseded_at = now()
                 WHERE assertion_id = $2 AND superseded_at IS NULL
                """,
                assertion_id,
                uuid.UUID(supersedes),
            )

    return str(assertion_id)


class RetractionRefused(RuntimeError):
    """Raised when a retraction cannot be applied as requested."""


async def retract_assertion(
    assertion_id: str, *, retracted_by: str, reason: str, conn: asyncpg.Connection | None = None
) -> bool:
    """Mark an assertion as no longer believed. Returns whether it changed.

    A reason is mandatory, at both this layer and the database's. A belief that
    vanishes without explanation is worse than one that was never recorded: the
    analyst who relied on it has no way to learn why they should not have.
    """
    if not reason.strip():
        raise RetractionRefused("A retraction requires a stated reason")

    sql = """
        UPDATE assertions
           SET retracted_at = now(), retracted_by = $2, retraction_reason = $3
         WHERE assertion_id = $1 AND retracted_at IS NULL
    """
    args = (uuid.UUID(assertion_id), retracted_by, reason)
    if conn is not None:
        status = await conn.execute(sql, *args)
    else:
        async with acquire() as own:
            status = await own.execute(sql, *args)
    return status.endswith(" 1")


# `asserted_by` stays the stable identifier; the display name is resolved
# alongside it rather than stored. An assertion is immutable, so denormalising a
# username would freeze it at write time and a later rename would leave the
# record attributing a judgement to a name that no longer exists. Resolving on
# read tracks the rename, and COALESCE falls back to the raw identifier when the
# user or source has since been removed — the honest answer when the referent is
# gone, rather than an empty byline.
_ASSERTION_SELECT = """
    SELECT a.assertion_id, a.subject_ref, a.subject_type, a.predicate, a.object_value,
           a.epistemic_kind, a.reliability, a.credibility, a.method, a.asserted_by,
           a.asserted_at, a.valid_from, a.valid_until, a.superseded_by, a.superseded_at,
           a.retracted_at, a.retracted_by, a.retraction_reason, a.note,
           COALESCE(u.display_name, s.name, a.asserted_by) AS asserted_by_display,
           COALESCE(ru.display_name, a.retracted_by) AS retracted_by_display
      FROM assertions a
      LEFT JOIN users u
             ON a.asserted_by LIKE 'user:%'
            AND u.id::text = substring(a.asserted_by from 6)
      LEFT JOIN sources s
             ON a.asserted_by LIKE 'source:%'
            AND s.source_id = substring(a.asserted_by from 8)
      LEFT JOIN users ru
             ON a.retracted_by LIKE 'user:%'
            AND ru.id::text = substring(a.retracted_by from 6)
"""


def _assertion_from_row(row: asyncpg.Record) -> Assertion:
    return Assertion(
        assertion_id=str(row["assertion_id"]),
        subject_ref=row["subject_ref"],
        subject_type=row["subject_type"],
        predicate=row["predicate"],
        object_value=json.loads(row["object_value"]),
        epistemic_kind=EpistemicKind(row["epistemic_kind"]),
        rating=Rating(
            reliability=Reliability(row["reliability"]),
            credibility=Credibility(row["credibility"]),
        ),
        method=row["method"],
        asserted_by=row["asserted_by"],
        asserted_by_display=row["asserted_by_display"],
        asserted_at=row["asserted_at"],
        valid_from=row["valid_from"],
        valid_until=row["valid_until"],
        superseded_by=str(row["superseded_by"]) if row["superseded_by"] else None,
        superseded_at=row["superseded_at"],
        retracted_at=row["retracted_at"],
        retracted_by=row["retracted_by"],
        retracted_by_display=row["retracted_by_display"],
        retraction_reason=row["retraction_reason"],
        note=row["note"],
    )


# The bitemporal filter. `as_of` NULL means "as believed now".
#
# An assertion was believed at time D if it had been asserted by then and had
# not yet been retracted or superseded — the retraction has to be compared
# against D rather than merely checked for null, otherwise reconstructing a past
# belief would hide everything ARGUS has since changed its mind about, which is
# precisely what a post-incident review needs to see.
_AS_OF_FILTER = """
      AND ($2::timestamptz IS NULL OR (
              a.asserted_at <= $2
              AND (a.retracted_at IS NULL OR a.retracted_at > $2)
              AND (a.superseded_at IS NULL OR a.superseded_at > $2)
          ))
      AND ($2::timestamptz IS NOT NULL OR $3::boolean OR (
              a.retracted_at IS NULL AND a.superseded_at IS NULL
          ))
"""


async def assertions_for_subject(
    subject_ref: str,
    *,
    as_of: datetime | None = None,
    include_ended: bool = False,
    predicate: str | None = None,
) -> list[Assertion]:
    """Assertions about one entity.

    With `as_of` set, returns what ARGUS believed at that instant. Without it,
    returns current belief — plus retracted and superseded assertions when
    `include_ended` is true, which is how the UI shows an analyst that a belief
    was withdrawn rather than simply making it disappear.
    """
    async with acquire() as conn:
        rows = await conn.fetch(
            _ASSERTION_SELECT
            + """
            WHERE a.subject_ref = $1
            """
            + _AS_OF_FILTER
            + """
              AND ($4::text IS NULL OR a.predicate = $4)
            ORDER BY a.predicate ASC, a.asserted_at DESC
            """,
            subject_ref,
            as_of,
            include_ended,
            predicate,
        )
    assertions = [_assertion_from_row(row) for row in rows]
    await _attach_evidence(assertions)
    return assertions


async def get_assertion(assertion_id: str) -> Assertion | None:
    try:
        parsed = uuid.UUID(assertion_id)
    except ValueError:
        return None
    async with acquire() as conn:
        row = await conn.fetchrow(_ASSERTION_SELECT + " WHERE a.assertion_id = $1", parsed)
    if row is None:
        return None
    assertion = _assertion_from_row(row)
    await _attach_evidence([assertion])
    return assertion


async def _attach_evidence(assertions: list[Assertion]) -> None:
    """Load evidence and corroboration for a batch of assertions.

    One query for the batch rather than one per assertion: an entity page can
    carry dozens, and a per-row query here would make provenance the slowest
    thing on the screen — which is how provenance ends up being switched off.
    """
    if not assertions:
        return
    ids = [uuid.UUID(a.assertion_id) for a in assertions]

    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ae.assertion_id, ae.stance,
                   o.observation_id, o.recorded_at, o.occurred_at, o.collected_at,
                   s.source_id, s.name AS source_name, s.reliability,
                   s.is_synthetic, s.independence_group
              FROM assertion_evidence ae
              JOIN observations o ON o.observation_id = ae.observation_id
              JOIN sources s ON s.source_id = o.source_id
             WHERE ae.assertion_id = ANY($1::uuid[])
             ORDER BY o.recorded_at DESC
            """,
            ids,
        )

    by_assertion: dict[str, list[asyncpg.Record]] = defaultdict(list)
    for row in rows:
        by_assertion[str(row["assertion_id"])].append(row)

    for assertion in assertions:
        evidence_rows = by_assertion.get(assertion.assertion_id, [])
        assertion.evidence = [
            EvidenceRef(
                observation_id=str(row["observation_id"]),
                stance=row["stance"],
                source_id=row["source_id"],
                source_name=row["source_name"],
                source_reliability=Reliability(row["reliability"]),
                source_is_synthetic=row["is_synthetic"],
                recorded_at=row["recorded_at"],
                occurred_at=row["occurred_at"],
                collected_at=row["collected_at"],
            )
            for row in evidence_rows
        ]

        # Independence groups, not source ids and certainly not observation
        # counts. Two feeds reprinting one wire service share a group and count
        # once; counting them twice is how one rumour comes to look like a
        # corroborated pattern.
        supporting = {r["independence_group"] for r in evidence_rows if r["stance"] == "supports"}
        contradicting = {
            r["independence_group"] for r in evidence_rows if r["stance"] == "contradicts"
        }
        assertion.corroboration = Corroboration(
            independent_sources=len(supporting),
            supporting_observations=sum(1 for r in evidence_rows if r["stance"] == "supports"),
            contradicting_observations=sum(
                1 for r in evidence_rows if r["stance"] == "contradicts"
            ),
            source_groups=sorted(supporting),
            contradicting_groups=sorted(contradicting),
        )


async def conflicts_for_subject(
    subject_ref: str, *, as_of: datetime | None = None
) -> list[Conflict]:
    """Predicates on which current assertions disagree."""
    return find_conflicts(subject_ref, await assertions_for_subject(subject_ref, as_of=as_of))


def find_conflicts(subject_ref: str, assertions: list[Assertion]) -> list[Conflict]:
    """Group already-loaded assertions into conflicts.

    Returns every side, in the order they were asserted, with no winner. This is
    the single most important behaviour in the phase: a system that silently
    picks one of two contradictory claims is more dangerous than one that shows
    the conflict, because it removes the disagreement from the view of the only
    person who can resolve it.

    Pure, and takes the assertions rather than fetching them, so a caller that
    already has the list does not run the query and its evidence join a second
    time — which `get_subject_provenance` was doing on every entity page.
    """
    grouped: dict[str, list[Assertion]] = defaultdict(list)
    for assertion in assertions:
        grouped[assertion.predicate].append(assertion)

    conflicts: list[Conflict] = []
    for predicate, group in sorted(grouped.items()):
        distinct = {json.dumps(a.object_value, sort_keys=True, default=str) for a in group}
        if len(distinct) > 1:
            conflicts.append(
                Conflict(
                    subject_ref=subject_ref,
                    predicate=predicate,
                    assertions=sorted(group, key=lambda a: a.asserted_at),
                )
            )
    return conflicts


async def sources_for_subject(subject_ref: str) -> list[Source]:
    """Every source that has said anything about this entity."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT s.*
              FROM sources s
              JOIN observations o ON o.source_id = s.source_id
              JOIN observation_subjects os ON os.observation_id = o.observation_id
             WHERE os.subject_ref = $1
             ORDER BY s.source_id
            """,
            subject_ref,
        )
    return [_source_from_row(row) for row in rows]


async def counts() -> dict[str, int]:
    """Row counts, for the health surface and for verifying a backfill."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT (SELECT count(*) FROM sources) AS sources,
                   (SELECT count(*) FROM observations) AS observations,
                   (SELECT count(*) FROM observation_subjects) AS observation_subjects,
                   (SELECT count(*) FROM assertions) AS assertions,
                   (SELECT count(*) FROM assertion_evidence) AS assertion_evidence
            """
        )
    assert row is not None
    return dict(row)
