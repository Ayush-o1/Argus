"""The one declaration of what ARGUS's intelligence is not allowed to see.

This lived inside `app/assessment/evidence.py` while assessment was the only
derived-intelligence package. Correlation is the second, and the boundary is one
property of the system rather than one per phase — so it is declared here, once,
and imported by both. Two copies would eventually disagree, and the copy that
was forgotten would be the one guarding the newer code.

## Why a whitelist exists at all

The scenario generator plants storylines and then writes down what it planted:
`risk_score` on the entities involved, `flagged` on the transactions it created,
`storyline_id` linking them back, `Incident` and `Case` nodes summarising them.
An analytic that reads any of those rediscovers the generator's own answer and
reports it as a finding. That is audit finding G-08, and it is the reason
Phases 5 and 6 exist.

## Two kinds of disqualification

**Answer keys** state the conclusion directly: `risk_score`, `risk_factors`,
`flags`, `flagged`, `storyline_id`, `community_ids`, `route_anomaly`,
`inconsistency_type`, and the `Storyline`, `Incident` and `Case` nodes with the
`INVOLVES` and `LINKED_TO` edges that hang off them.

**Structures that exist only because a storyline created them** carry no label
at all, and are the subtler half. `CONTROLS` (24 edges) and `SHARES_DEVICE` (2
edges) have no baseline population in this world: every one of them was written
by the storyline injector. A correlation dimension keyed on either would score
near-perfectly against ground truth and would have discovered nothing — it would
be reading the same label through the shape of the graph instead of through a
property. `Organization.type` is disqualified for the same reason: the
shell-company storyline overwrites it to `Shell`, so the attribute is partly an
answer key even though shell companies also occur in the baseline.

The consequence, in both phases, is that some planted phenomena cannot be found
by any admissible means. Each phase's evaluation module reports that as a
finding rather than working around it, because the alternative — an analytic
that reads the plant — is the exact failure this boundary exists to prevent.
"""

from __future__ import annotations

# Properties, node labels and relationship types that must never appear in a
# query on an intelligence path. Named explicitly so the isolation tests can
# grep for them rather than relying on a reviewer noticing.
#
# The test that enforces this reads source with docstrings and comments removed,
# so prose may name these freely — as this module's own docstring does — while a
# reference that could reach the database may not.
INADMISSIBLE_TOKENS: tuple[str, ...] = (
    "risk_score",
    "risk_factors",
    "flags",
    "flagged",
    "storyline_id",
    "community_ids",
    "route_anomaly",
    "inconsistency_type",
    "Storyline",
    "Incident",
    "CONTROLS",
    "SHARES_DEVICE",
)

# Added by Phase 6. `Case` nodes are seeded directly from storylines by the
# generator's case seeder, and `LINKED_TO` joins a Case to every entity its
# storyline named — which makes that edge a ready-made correlation between
# exactly the entities a correlation engine is supposed to discover
# independently. `INVOLVES` does the same job from the `Incident` side.
#
# Kept separate from the tuple above so Phase 5's guarantees are stated in the
# same terms they were written in, and so the reason these three were added
# later is not lost.
INADMISSIBLE_CORRELATION_TOKENS: tuple[str, ...] = (
    "Case",
    "INVOLVES",
    "LINKED_TO",
)

ALL_INADMISSIBLE_TOKENS: tuple[str, ...] = (
    *INADMISSIBLE_TOKENS,
    *INADMISSIBLE_CORRELATION_TOKENS,
)
