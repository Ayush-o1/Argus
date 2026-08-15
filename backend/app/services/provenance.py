"""ARGUS's own sources, and the backfill that gives the existing graph a past.

## Why the generator is a registered source

The audit's sharpest finding was not a bug. It was that the scenario generator
plants storylines and marks their participants high-risk, and the platform then
presents those planted values with the visual authority of analytic conclusions
— so every "discovery" is guaranteed to succeed and proves nothing.

Documenting that in a README does not fix it, because the next surface someone
builds will read `risk_score` and render it like any other number. The fix has
to be structural: the generator is registered as a **source**, flagged
`is_synthetic`, rated F, and every fact it produced hangs off an observation
that names it. A surface can no longer display generator output without also
being able to see where it came from.

## What the backfill claims, and what it refuses to claim

The graph predates this layer, so its provenance is reconstructed rather than
captured. The reconstruction states only what is actually known:

  - **recorded_at** — real. It is when the backfill ran, which genuinely is when
    these facts entered the provenance store.
  - **collected_at** — NULL. The generator never recorded a collection time, and
    defaulting it to the backfill time would fabricate a fact in the one place
    designed to prevent that.
  - **occurred_at** — NULL. The generator writes naive local wall-clock strings
    with no timezone (audit B-17), so no instant can be derived from them. The
    raw string is kept in the payload, where it is evidence of what the source
    said rather than a timestamp ARGUS is asserting. Phase 3 fixes the
    generator; until then this layer shows the gap instead of papering over it.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import asyncpg
from neo4j import AsyncDriver

from app.database.migrations.runner import HUMAN_ID_FIELDS
from app.database.postgres import acquire
from app.models.provenance import (
    Credibility,
    EpistemicKind,
    Reliability,
    Source,
    SourceType,
)
from app.repositories import provenance_repo

logger = logging.getLogger(__name__)

GENERATOR_SOURCE_ID = "argus.scenario-generator"
ANALYST_SOURCE_ID = "argus.analyst"
DERIVED_SOURCE_ID = "argus.derived"

# The method identifier for the generator's risk scorer. Versioned, so when
# Phase 5 replaces it every assertion made by the old one stays identifiable.
GENERATOR_RISK_METHOD = "generator.risk_scorer@v1"


BUILTIN_SOURCES: list[Source] = [
    Source(
        source_id=GENERATOR_SOURCE_ID,
        name="ARGUS Scenario Generator",
        source_type=SourceType.SYNTHETIC,
        description=(
            "Fabricates a synthetic world — people, organisations, accounts, movements and "
            "planted storylines — for demonstration and testing. It is not a report about "
            "anything that happened."
        ),
        reliability=Reliability.F,
        reliability_basis=(
            "Reliability cannot be judged, because there is nothing to judge it against: this "
            "source invents its content rather than reporting on the world. The rating is F and "
            "the synthetic flag is set, so no assessment built on this data can inherit "
            "confidence it has not earned."
        ),
        is_synthetic=True,
        independence_group=GENERATOR_SOURCE_ID,
        staleness_hours=None,
    ),
    Source(
        source_id=ANALYST_SOURCE_ID,
        name="ARGUS Analyst Workbench",
        source_type=SourceType.HUMAN,
        description=(
            "Judgements entered by named analysts through ARGUS. Each assertion is attributed "
            "to the individual who made it."
        ),
        reliability=Reliability.F,
        reliability_basis=(
            "ARGUS does not rate individual analysts, and assigning the workbench a flattering "
            "blanket rating would launder every judgement made through it. Source-level "
            "reliability is therefore left unjudged; what carries weight is the named analyst "
            "on the assertion and the credibility they state for the specific claim."
        ),
        is_synthetic=False,
        independence_group=ANALYST_SOURCE_ID,
        staleness_hours=None,
    ),
    Source(
        source_id=DERIVED_SOURCE_ID,
        name="ARGUS Derived",
        source_type=SourceType.SYSTEM,
        description=(
            "Output of ARGUS's own algorithms — scoring, correlation, anomaly detection. Every "
            "assertion names the method and version that produced it."
        ),
        reliability=Reliability.F,
        reliability_basis=(
            "The reliability of a derivation is a property of the method and its calibration. "
            "ARGUS has no calibration report for any of its algorithms yet (that is Phase 11), "
            "so there is no basis for a rating and F is the honest answer. Individual methods "
            "may be rated higher once measured precision and recall exist to justify it."
        ),
        is_synthetic=False,
        independence_group=DERIVED_SOURCE_ID,
        staleness_hours=None,
    ),
]


async def ensure_builtin_sources() -> None:
    """Register ARGUS's own sources. Idempotent; runs at startup."""
    for source in BUILTIN_SOURCES:
        await provenance_repo.register_source(source)


# ─────────────────────────────────────────────────────────────────────────────
# Backfill
# ─────────────────────────────────────────────────────────────────────────────

_BACKFILL_NOTE = (
    "Reconstructed from the graph by the provenance backfill. The graph predates the "
    "provenance layer, so this record was not captured at ingest: recorded_at is when the "
    "backfill ran, and collection and occurrence times are null because the source never "
    "recorded them. Timestamps the source did write are naive local wall-clock strings with "
    "no timezone, so they are preserved verbatim in the payload rather than converted into "
    "an instant ARGUS cannot actually justify."
)

# Properties excluded from the observation payload because they are ARGUS's
# internal bookkeeping rather than anything the generator "reported" about the
# entity. Keeping them would make the content hash sensitive to storage details.
_INTERNAL_PROPERTIES = frozenset({"id"})

_BATCH_SIZE = 500


class BackfillResult:
    def __init__(self) -> None:
        self.nodes_seen = 0
        self.observations_created = 0
        self.observations_existing = 0
        self.risk_assertions_created = 0
        self.risk_assertions_existing = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "nodes_seen": self.nodes_seen,
            "observations_created": self.observations_created,
            "observations_existing": self.observations_existing,
            "risk_assertions_created": self.risk_assertions_created,
            "risk_assertions_existing": self.risk_assertions_existing,
        }


async def backfill_graph_provenance(
    driver: AsyncDriver, *, labels: list[str] | None = None
) -> BackfillResult:
    """Give every existing graph node an observation attributing it to the generator.

    Idempotent in both directions: observations deduplicate on content hash, and
    risk assertions are skipped for subjects that already have one from the same
    method. Re-running after adding data backfills only the new data, and
    re-running unchanged is a no-op — which matters, because a backfill that
    doubles its output on a second run would double every corroboration count.
    """
    await ensure_builtin_sources()

    wanted = [(label, field) for label, field in HUMAN_ID_FIELDS if labels is None or label in labels]
    result = BackfillResult()

    for label, id_field in wanted:
        skip = 0
        while True:
            batch = await _fetch_node_batch(driver, label, id_field, skip, _BATCH_SIZE)
            if not batch:
                break
            await _write_batch(label, batch, result)
            result.nodes_seen += len(batch)
            skip += _BATCH_SIZE
            logger.info("backfilled provenance for %s: %d nodes", label, skip)

    return result


async def _fetch_node_batch(
    driver: AsyncDriver, label: str, id_field: str, skip: int, limit: int
) -> list[dict[str, Any]]:
    # Ordered by the human id so paging is stable. Ordering by an unindexed or
    # non-unique property would let a node appear in two pages or none.
    query = f"""
    MATCH (n:{label})
    WHERE n.{id_field} IS NOT NULL
    RETURN n.{id_field} AS human_id, properties(n) AS props
    ORDER BY n.{id_field}
    SKIP $skip LIMIT $limit
    """
    async with driver.session() as session:
        cursor = await session.run(query, skip=skip, limit=limit)
        return [
            {"human_id": record["human_id"], "props": dict(record["props"])}
            async for record in cursor
        ]


def _observation_payload(props: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in sorted(props.items())
        if key not in _INTERNAL_PROPERTIES and value is not None
    }


async def _write_batch(label: str, batch: list[dict[str, Any]], result: BackfillResult) -> None:
    prepared = []
    for node in batch:
        payload = _observation_payload(node["props"])
        prepared.append(
            {
                "human_id": node["human_id"],
                "payload": payload,
                "content_hash": provenance_repo.canonical_hash(payload),
                "risk_score": node["props"].get("risk_score"),
                "risk_factors": node["props"].get("risk_factors") or [],
            }
        )

    async with acquire() as conn, conn.transaction():
        await _insert_observations(conn, label, prepared, result)
        await _insert_risk_assertions(conn, label, prepared, result)


async def _insert_observations(
    conn: asyncpg.Connection, label: str, prepared: list[dict[str, Any]], result: BackfillResult
) -> None:
    hashes = [item["content_hash"] for item in prepared]
    before = set(
        await conn.fetch(
            "SELECT content_hash FROM observations WHERE source_id = $1 AND content_hash = ANY($2::text[])",
            GENERATOR_SOURCE_ID,
            hashes,
        )
    )
    existing_hashes = {row["content_hash"] for row in before}

    rows = [
        (
            uuid.uuid4(),
            GENERATOR_SOURCE_ID,
            f"graph.node.{label}",
            json.dumps(item["payload"], default=str),
            item["content_hash"],
            _BACKFILL_NOTE,
        )
        for item in prepared
        if item["content_hash"] not in existing_hashes
    ]
    if rows:
        await conn.executemany(
            """
            INSERT INTO observations (
                observation_id, source_id, content_type, payload, content_hash, provenance_note
            ) VALUES ($1, $2, $3, $4::jsonb, $5, $6)
            ON CONFLICT (source_id, content_hash) DO NOTHING
            """,
            rows,
        )

    # Re-read rather than trusting the generated ids: ON CONFLICT DO NOTHING
    # means a row inserted concurrently keeps the other writer's id, and linking
    # subjects to an id that was never stored would silently orphan them.
    id_rows = await conn.fetch(
        "SELECT observation_id, content_hash FROM observations WHERE source_id = $1 AND content_hash = ANY($2::text[])",
        GENERATOR_SOURCE_ID,
        hashes,
    )
    by_hash = {row["content_hash"]: row["observation_id"] for row in id_rows}

    await conn.executemany(
        """
        INSERT INTO observation_subjects (observation_id, subject_ref, subject_type)
        VALUES ($1, $2, $3)
        ON CONFLICT DO NOTHING
        """,
        [
            (by_hash[item["content_hash"]], item["human_id"], label)
            for item in prepared
            if item["content_hash"] in by_hash
        ],
    )

    for item in prepared:
        if item["content_hash"] in existing_hashes:
            result.observations_existing += 1
        else:
            result.observations_created += 1


async def _insert_risk_assertions(
    conn: asyncpg.Connection, label: str, prepared: list[dict[str, Any]], result: BackfillResult
) -> None:
    """Record the generated risk score as what it is: an inference by a synthetic
    source, not an observation of anything.

    This is the audit's headline finding made structural. `risk_score` is
    displayed on every entity surface with the authority of an assessment, but
    the generator computed it from storyline membership — from its own answer
    key. Writing it as an INFERRED assertion, rated F6, with the method named
    and versioned, means the UI can no longer show the number without also being
    able to show what it actually is. Phase 5 replaces the value; this makes the
    interim honest.
    """
    scored = [item for item in prepared if item["risk_score"] is not None]
    if not scored:
        return

    refs = [item["human_id"] for item in scored]
    already = {
        row["subject_ref"]
        for row in await conn.fetch(
            """
            SELECT DISTINCT subject_ref FROM assertions
             WHERE subject_ref = ANY($1::text[]) AND predicate = 'risk_score' AND method = $2
            """,
            refs,
            GENERATOR_RISK_METHOD,
        )
    }

    pending = [item for item in scored if item["human_id"] not in already]
    result.risk_assertions_existing += len(scored) - len(pending)
    if not pending:
        return

    obs_rows = await conn.fetch(
        """
        SELECT os.subject_ref, os.observation_id
          FROM observation_subjects os
          JOIN observations o ON o.observation_id = os.observation_id
         WHERE os.subject_ref = ANY($1::text[]) AND o.source_id = $2
        """,
        [item["human_id"] for item in pending],
        GENERATOR_SOURCE_ID,
    )
    observation_by_ref: dict[str, Any] = {row["subject_ref"]: row["observation_id"] for row in obs_rows}

    assertion_rows = []
    evidence_rows = []
    for item in pending:
        assertion_id = uuid.uuid4()
        factors = item["risk_factors"]
        note = (
            "Assigned by the scenario generator from storyline membership, not derived from "
            "evidence about the world. "
            + (
                f"Stated contributing factors: {'; '.join(str(f) for f in factors)}."
                if factors
                else "The generator recorded no contributing factors, so this value has no "
                "stated basis at all."
            )
        )
        assertion_rows.append(
            (
                assertion_id,
                item["human_id"],
                label,
                "risk_score",
                json.dumps(item["risk_score"]),
                EpistemicKind.INFERRED.value,
                Reliability.F.value,
                Credibility.CANNOT_BE_JUDGED.value,
                GENERATOR_RISK_METHOD,
                f"source:{GENERATOR_SOURCE_ID}",
                note,
            )
        )
        observation_id = observation_by_ref.get(item["human_id"])
        if observation_id is not None:
            evidence_rows.append((assertion_id, observation_id, "supports"))

    await conn.executemany(
        """
        INSERT INTO assertions (
            assertion_id, subject_ref, subject_type, predicate, object_value,
            epistemic_kind, reliability, credibility, method, asserted_by, note
        ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10, $11)
        """,
        assertion_rows,
    )
    if evidence_rows:
        await conn.executemany(
            """
            INSERT INTO assertion_evidence (assertion_id, observation_id, stance)
            VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
            """,
            evidence_rows,
        )
    result.risk_assertions_created += len(assertion_rows)


# ─────────────────────────────────────────────────────────────────────────────
# Attribute-level provenance
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AttributeProvenanceResult:
    """Per-attribute provenance, with the denominator it was computed against.

    The denominator is not decoration. `attributes` is derived from a bounded
    read of the observation store, so without knowing how many observations
    exist a caller cannot tell "nothing reported this field" from "the
    observation that reported it fell outside the window" — and the first is a
    statement about the world while the second is a statement about a LIMIT
    clause. Rendering one as the other is exactly the class of defect Phase 0
    removed from the timeline and the alert spread.
    """

    attributes: dict[str, dict[str, Any]]
    observations_examined: int
    observations_total: int

    @property
    def complete(self) -> bool:
        return self.observations_examined >= self.observations_total


async def attribute_provenance(
    subject_ref: str, properties: dict[str, Any], *, limit: int = 500
) -> AttributeProvenanceResult:
    """For each displayed property, where it came from.

    This is what makes the phase's first acceptance criterion true rather than
    aspirational: every fact on an entity page resolves to an observation that
    reported it, or is explicitly marked as inferred, or is marked unattributed.
    There is no fourth outcome — a value with no provenance is reported as
    having none rather than quietly rendering like the rest.

    Values are compared against what the source actually said. A property that
    has since been changed in the graph no longer matches its observation, and
    is reported as `modified` rather than as observed — an edit that silently
    inherits the original's provenance is a forgery, however well-intentioned.
    """
    observations = await provenance_repo.observations_for_subject(subject_ref, limit=limit)
    observations_total = await provenance_repo.count_observations_for_subject(subject_ref)
    assertions = await provenance_repo.assertions_for_subject(subject_ref)

    by_predicate: dict[str, list[Any]] = {}
    for assertion in assertions:
        by_predicate.setdefault(assertion.predicate, []).append(assertion)

    out: dict[str, dict[str, Any]] = {}
    for key, value in properties.items():
        entry: dict[str, Any] = {"kind": "unattributed", "observations": [], "assertions": []}

        for observation in observations:
            if key not in observation.payload:
                continue
            matches = observation.payload[key] == value
            entry["observations"].append(
                {
                    "observation_id": observation.observation_id,
                    "source_id": observation.source_id,
                    "source_name": observation.source_name,
                    "source_reliability": observation.source_reliability.value,
                    "source_is_synthetic": observation.source_is_synthetic,
                    "recorded_at": observation.recorded_at,
                    "collected_at": observation.collected_at,
                    "occurred_at": observation.occurred_at,
                    "reported_value": observation.payload[key],
                    "matches_current_value": matches,
                }
            )
            if entry["kind"] == "unattributed":
                entry["kind"] = "reported" if matches else "modified"
            elif entry["kind"] == "modified" and matches:
                entry["kind"] = "reported"

        for assertion in by_predicate.get(key, []):
            entry["assertions"].append(assertion.model_dump(mode="json"))
            # An explicit assertion outranks a raw report for how the value
            # should be labelled: the assertion is the considered claim.
            entry["kind"] = assertion.epistemic_kind.value

        out[key] = entry

    return AttributeProvenanceResult(
        attributes=out,
        observations_examined=len(observations),
        observations_total=observations_total,
    )
