"""Named graph projections, so an algorithm result can say what it ran on.

Every graph algorithm in ARGUS used to run against one projection — `Account`
nodes joined by `TRANSACTED_WITH` — and none of them said so. A PageRank score
appeared on the analytics page as "influence", with no indication that the graph
in question contained no people, no organisations, no devices and no events, and
that "influence" therefore meant "receives money from accounts that receive
money". An analyst comparing a PageRank rank against a Louvain community was
comparing two answers to two different questions and had no way to know it.

A `ProjectionSpec` fixes that by making the graph an explicit, named,
fingerprinted argument. Every result carries the spec that produced it, and the
UI renders the spec beside the number.

## Weights are a claim, and are stated as one

Once a projection contains more than one relationship type, their relative
weight decides the outcome — an entity graph where a directorship counts the
same as a single phone call produces a different ranking from one where it
counts for ten times as much, and neither is "the" answer. The weights below are
a stated editorial position with a reason attached, exposed through the API so
they can be argued with. They are not tuned against the storylines: doing so
would be fitting the projection to the answer key, which is the failure this
whole part of the system exists to avoid.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from neo4j import AsyncDriver

logger = logging.getLogger(__name__)

PROJECTION_PREFIX = "argusGraph"


# Every projection exposes exactly one weight property under this alias,
# whatever it was sourced from. GDS algorithms take a single
# `relationshipWeightProperty`, so without a common alias a multi-type
# projection could not be weighted at all.
WEIGHT_ALIAS = "argus_weight"


@dataclass(frozen=True)
class RelationshipSpec:
    rel_type: str
    orientation: str
    weight: float
    rationale: str
    weight_property: str | None = None
    """A property on the relationship to use as its weight, instead of the flat
    `weight` above. Only `amount` is used, and only in the money projection.

    It is deliberately not used in the entity projection: transfer amounts run
    into the hundreds of thousands, and mixing them with structural weights of
    3.0 would not balance the graph — it would make every other relationship
    type arithmetically invisible while appearing to include them."""


@dataclass(frozen=True)
class ProjectionSpec:
    """One named graph, with everything needed to reproduce it."""

    name: str
    title: str
    description: str
    node_labels: tuple[str, ...]
    relationships: tuple[RelationshipSpec, ...]
    caveats: tuple[str, ...] = field(default_factory=tuple)
    """What this projection cannot answer. Published with the results, because
    the most misleading thing about a graph metric is usually the part of the
    world the graph left out."""

    @property
    def relationship_types(self) -> tuple[str, ...]:
        return tuple(r.rel_type for r in self.relationships)

    def fingerprint(self) -> str:
        payload = {
            "nodes": sorted(self.node_labels),
            "relationships": sorted(
                [
                    [r.rel_type, r.orientation, r.weight, r.weight_property or ""]
                    for r in self.relationships
                ]
            ),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    def provenance(self) -> dict:
        """What every algorithm result carries with it."""
        return {
            "projection": self.name,
            "title": self.title,
            "description": self.description,
            "fingerprint": self.fingerprint(),
            "node_labels": list(self.node_labels),
            "relationships": [
                {
                    "type": r.rel_type,
                    "orientation": r.orientation,
                    "weight": r.weight,
                    "weight_property": r.weight_property,
                    "rationale": r.rationale,
                }
                for r in self.relationships
            ],
            "caveats": list(self.caveats),
        }


MONEY = ProjectionSpec(
    name="money",
    title="Money movement",
    description=(
        "Accounts joined by transfers, weighted by amount. The graph the original "
        "analytics ran on, kept unchanged so results from before this phase remain "
        "comparable with results from after it."
    ),
    node_labels=("Account",),
    relationships=(
        RelationshipSpec(
            rel_type="TRANSACTED_WITH",
            orientation="NATURAL",
            weight=1.0,
            weight_property="amount",
            rationale=(
                "Direction is the point: money flows one way, and a ranking that ignored that would rank payers and "
                "payees identically. Weighted by the amount moved."
            ),
        ),
    ),
    caveats=(
        "Contains no people or organisations. A high rank belongs to an account, and the "
        "person behind it is inferred from ownership afterwards.",
        "An account that receives many small transfers can outrank one that receives a "
        "single large one. Weighting is by amount, but structure dominates.",
    ),
)

ENTITY = ProjectionSpec(
    name="entity",
    title="Entity network",
    description=(
        "People, organisations, accounts and devices joined by ownership, direction, "
        "employment, money and communication. The graph most questions about "
        "'who is central here' actually mean, as opposed to the account-only graph "
        "those questions used to be answered on."
    ),
    node_labels=("Person", "Organization", "Account", "Device"),
    relationships=(
        RelationshipSpec(
            rel_type="OWNS_ACCOUNT",
            orientation="UNDIRECTED",
            weight=3.0,
            rationale=(
                "Ownership is the strongest tie in this graph and the one that makes an account's behaviour "
                "attributable to a person. Undirected because centrality should flow both ways along it."
            ),
        ),
        RelationshipSpec(
            rel_type="OWNS_DEVICE",
            orientation="UNDIRECTED",
            weight=3.0,
            rationale="Same reasoning as account ownership: it is what connects a communication record to a person.",
        ),
        RelationshipSpec(
            rel_type="DIRECTS",
            orientation="UNDIRECTED",
            weight=2.5,
            rationale=(
                "A declared, durable position of control. Weighted below ownership because a person may direct an "
                "organisation they have no financial stake in."
            ),
        ),
        RelationshipSpec(
            rel_type="EMPLOYED_BY",
            orientation="UNDIRECTED",
            weight=1.0,
            rationale=(
                "Real but weak. Thousands of people are employed by the same organisations, and weighting "
                "employment like directorship would make every large employer the centre of the graph."
            ),
        ),
        RelationshipSpec(
            rel_type="TRANSACTED_WITH",
            orientation="NATURAL",
            weight=1.5,
            rationale=(
                "Kept directed, unlike the structural edges: who paid whom is the asymmetry that makes a layering "
                "chain visible."
            ),
        ),
        RelationshipSpec(
            rel_type="COMMUNICATED_WITH",
            orientation="UNDIRECTED",
            weight=1.0,
            rationale=(
                "Who called whom carries little meaning at this granularity — a call is a contact in both "
                "directions — so direction is discarded rather than given false significance."
            ),
        ),
    ),
    caveats=(
        "`CONTROLS` and `SHARES_DEVICE` are deliberately excluded. Every instance of both "
        "in this world was written by the scenario generator's storyline injector, so a "
        "centrality score that used them would be ranking the answer key.",
        "Nodes with none of these relationships are included with no edges rather than left "
        "out — 1,321 of 8,750 on the current data. Their centrality is zero because they are "
        "unconnected, which is a finding; being absent from the graph would not be.",
        "Weights are an editorial judgement, not a measurement. A different set produces a "
        "different ranking, and both are defensible.",
        "Communities in this graph are shaped by employment, which is dense. A community is "
        "not evidence of coordination.",
    ),
)

SPECS: dict[str, ProjectionSpec] = {spec.name: spec for spec in (MONEY, ENTITY)}
DEFAULT_SPEC = MONEY


def spec_for(name: str | None) -> ProjectionSpec:
    if name is None:
        return DEFAULT_SPEC
    try:
        return SPECS[name]
    except KeyError:
        raise ValueError(
            f"unknown projection {name!r}; available: {', '.join(sorted(SPECS))}"
        ) from None


def _projection_query(spec: ProjectionSpec) -> str:
    """The Cypher that builds this projection.

    ## Why a Cypher projection rather than the simpler native one

    The native `gds.graph.project` takes a relationship map with a `defaultValue`
    per property, and the obvious way to give each relationship type a flat
    weight is to name a property that exists nowhere and let every edge fall back
    to the default. That does not work, and finding out cost a live run:

        Relationship properties not found: 'argus_weight'

    GDS validates that the source property exists on at least one relationship of
    the type before it will accept a default. So a flat per-type weight has to be
    *computed*, and a Cypher projection computes one without writing anything
    into the database. Writing `argus_weight` onto 60,000 relationships would
    also work, and would mean the correlator's own configuration had become part
    of the world it reads from.

    Built on `gds.graph.project` as an aggregation function rather than the
    `gds.graph.project.cypher` procedure, which GDS 2.13 reports as deprecated.

    ## Isolated nodes are included

    Nodes with none of the projected relationships are emitted with a null
    target, so they appear in the graph with no edges. Without that they would
    be silently absent — 1,321 of the entity graph's 8,750 nodes on the live
    data, mostly people with no account, device or employer — and the projection
    would claim to contain `Person, Organization, Account, Device` while
    excluding one node in seven of them. A centrality of zero and an absence
    from the graph are different statements.

    ## Direction

    `UNDIRECTED` types emit both directions, which is what undirected means to a
    Cypher projection. `NATURAL` types emit one, because who paid whom is the
    asymmetry that makes a layering chain visible.

    ## Injection

    Relationship types and node labels cannot be parameters in Cypher, so they
    are interpolated. Every value comes from the frozen `SPECS` registry in this
    module — never from a request — and `spec_for` rejects any name not in it,
    so no caller-supplied string reaches this function. Weights are interpolated
    as Python floats, not as text.
    """
    def labelled(variable: str) -> str:
        return " OR ".join(f"{variable}:{label}" for label in spec.node_labels)

    clauses: list[str] = []
    for relationship in spec.relationships:
        weight = (
            f"r.{relationship.weight_property}"
            if relationship.weight_property
            else repr(float(relationship.weight))
        )
        match = (
            f"MATCH (a)-[r:{relationship.rel_type}]->(b) "
            f"WHERE ({labelled('a')}) AND ({labelled('b')})"
        )
        clauses.append(
            f"{match} RETURN a AS source, b AS target, "
            f"'{relationship.rel_type}' AS relType, {weight} AS weight"
        )
        if relationship.orientation == "UNDIRECTED":
            clauses.append(
                f"{match} RETURN b AS source, a AS target, "
                f"'{relationship.rel_type}' AS relType, {weight} AS weight"
            )

    every_type = "|".join(r.rel_type for r in spec.relationships)
    clauses.append(
        f"MATCH (n) WHERE ({labelled('n')}) AND NOT (n)-[:{every_type}]-() "
        f"RETURN n AS source, null AS target, null AS relType, null AS weight"
    )

    union = " UNION ALL ".join(clauses)
    return (
        f"CALL {{ {union} }} "
        f"WITH source, target, relType, weight "
        f"RETURN gds.graph.project($name, source, target, {{"
        f"  sourceNodeLabels: labels(source),"
        f"  targetNodeLabels: CASE WHEN target IS NULL THEN [] ELSE labels(target) END,"
        f"  relationshipType: relType,"
        f"  relationshipProperties: CASE WHEN weight IS NULL THEN {{}} "
        f"                          ELSE {{ {WEIGHT_ALIAS}: weight }} END"
        f"}}) AS g"
    )


@asynccontextmanager
async def projection(driver: AsyncDriver, spec: ProjectionSpec) -> AsyncIterator[str]:
    """Create a private GDS projection for one job, and drop it afterwards.

    A per-job name rather than a shared one, carried over from the fix for audit
    B-06: every entry point used to share a projection called `entityGraph` and
    began by dropping it if it existed, so running two analytics jobs together —
    trivially done from the analytics page — had one drop the graph out from
    under the other mid-stream.
    """
    name = f"{PROJECTION_PREFIX}_{spec.name}_{uuid.uuid4().hex[:10]}"

    async with driver.session() as session:
        result = await session.run(_projection_query(spec), name=name)
        # Consumed, not merely issued. `session.run` is lazy: without reading a
        # record the statement's error surfaces whenever the driver next happens
        # to notice, which in practice meant a failed projection was reported
        # minutes later as `GraphNotFoundException` from the algorithm that tried
        # to use it — a misleading message pointing at the wrong component.
        # Reading the record here makes a projection failure fail here, with the
        # reason GDS actually gave.
        record = await result.single()
        if record is None:
            raise RuntimeError(f"GDS accepted no projection for spec {spec.name!r}")
        built = record["g"]
        logger.info(
            "projected %s: %s nodes, %s relationships",
            name,
            built.get("nodeCount") if isinstance(built, dict) else "?",
            built.get("relationshipCount") if isinstance(built, dict) else "?",
        )
    try:
        yield name
    finally:
        # In a finally block so a failed or cancelled job cannot leak a
        # projection, which would hold heap until the database restarts.
        # Best-effort: a drop failure must not mask the original error.
        try:
            async with driver.session() as session:
                await session.run(
                    "CALL gds.graph.drop($name, false) YIELD graphName RETURN graphName",
                    name=name,
                )
        except Exception:
            logger.warning("failed to drop GDS projection %s", name, exc_info=True)


def catalogue() -> list[dict]:
    """Every available projection, as the API publishes it."""
    return [spec.provenance() for spec in SPECS.values()]
