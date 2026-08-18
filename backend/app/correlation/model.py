"""The correlation model: every threshold in one place, fingerprinted.

The same discipline as `RiskModel`, for the same reason — a precision figure is
meaningless without a way to say which model produced it. The fingerprint
covers the parameters *and* the dimension registry, because adding a dimension
changes what a strength of 0.7 means just as surely as moving a threshold does.

## What a strength is, and what it is not

A link's strength is an answer to "how much reason is there to think these two
findings belong together" — bounded above by 1 and never reaching it. It is not
a probability that the two subjects are conspiring, and the UI never renders it
as one. ARGUS has no evidence about intent, and a number that implied otherwise
would be exactly the manufactured confidence this system is built to avoid.

## Why there are no severity words here

A link is `established`, `probable`, `possible` or nothing at all. Those name
how much corroboration was found, not how bad the link would be if real —
which is a judgement about the world that belongs to an analyst.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import timedelta

from app.correlation.dimensions import (
    DIMENSIONS,
    FAMILY_FINANCIAL,
    FAMILY_LOGISTICAL,
    FAMILY_SOCIAL,
    FAMILY_SPATIAL,
    FAMILY_TEMPORAL,
)

TIER_ESTABLISHED = "established"
TIER_PROBABLE = "probable"
TIER_POSSIBLE = "possible"

TIERS: tuple[str, ...] = (TIER_ESTABLISHED, TIER_PROBABLE, TIER_POSSIBLE)

TIER_MEANING: dict[str, str] = {
    TIER_ESTABLISHED: (
        "Two or more independent kinds of evidence identify this pair — financial, social "
        "or logistical — and each would point here on its own. Proximity and timing may "
        "have added to the strength but never count towards this: being in one place, or "
        "busy in one week, is true of enormous numbers of unrelated pairs. A connection "
        "worth an analyst's time, not a conclusion about what the connection means."
    ),
    TIER_PROBABLE: (
        "One kind of evidence identifies this pair strongly, and nothing independent "
        "corroborates it. Real structure was found; it has one explanation and no second "
        "opinion."
    ),
    TIER_POSSIBLE: (
        "Something connects these two, weakly. Shown so it can be dismissed with the reason "
        "visible, rather than omitted so it looks as though nothing was found."
    ),
}


@dataclass(frozen=True)
class CorrelationModel:
    """Every parameter that can change a link.

    Defaults were chosen by running the dimensions against the live graph and
    reading the resulting distributions — picking values that sit in the gap
    between populations, not values that maximised agreement with the
    generator's storylines. Tuning to the storylines would produce a better
    number and a worse model, because the storylines are the thing the
    correlator is not allowed to see.
    """

    version: str = "argus.correlation@v1"

    # ── Scope ────────────────────────────────────────────────────────────────
    max_anchors: int = 12_000
    """A ceiling on how many findings enter one run, so a pathological
    assessment generation cannot turn correlation into an unbounded job. Runs
    that hit it record the fact; they do not silently correlate a subset."""

    max_shared_key_fanout: int = 250
    """A counterparty, event or organisation touched by more anchors than this
    generates no candidate pairs. Not a scoring decision — those are still
    weighted by rarity — but a blocking one: a hub touched by 3,000 anchors
    would generate 4.5 million pairs to score, all of which would then be
    weighted to nearly nothing anyway."""

    # ── Financial ────────────────────────────────────────────────────────────
    counterparty_trigger: float = 3.0
    counterparty_full: float = 8.0
    """**Lift**, not raw overlap: how many times more rarity-weighted
    counterparty overlap the pair has than chance predicts for two subjects
    dealing with that many counterparties each.

    Set from the measured distribution on the live graph, where randomly chosen
    pairs have a median lift of 1.26, a 90th percentile of 2.5 and a 99th of
    5.0. A trigger of 3 therefore sits above roughly 95% of unrelated pairs, and
    8 is beyond all but a handful.

    The first version scored raw rarity-weighted overlap with a trigger of 0.55,
    and fired on 545 of 688 random pairs at a median magnitude of 0.63 — because
    two subjects picked at random already share about 2.8 counterparties in a
    world this dense. It was measuring the world, not the pair."""

    path_max_hops: int = 4
    path_min_hop_retention: float = 0.80
    path_min_total_retention: float = 0.55
    path_window_days: int = 30
    path_max_frontier: int = 400
    path_hops_trigger: float = 4.0
    path_hops_full: float = 1.0
    """Inverted: fewer hops is stronger. A direct transfer is the strongest
    financial link there is; a four-hop route is barely evidence."""

    path_concentration_trigger: float = 0.05
    path_concentration_full: float = 0.30
    """What share of the sending account's whole year of outgoing payments left
    along this route. Multiplied by the hop score, so distance and significance
    both have to hold.

    Distance alone was not enough. Against the live graph 5,527 pairs of flagged
    subjects have a direct transfer between them and the median one is 3.3% of
    the sender's annual outflow — two busy parties who once did business, not a
    relationship. Scoring on hops alone put 6,960 of those in `probable`.

    The thresholds come from that same distribution: 5% is above the median,
    leaving 1,857 pairs; 30% leaves 134, which is the tail where a payment is a
    substantial part of what an account does at all."""

    # ── Social ───────────────────────────────────────────────────────────────
    co_attendance_trigger: float = 0.60
    co_attendance_full: float = 2.00

    contact_direct_full: int = 3
    """Direct communications between the two subjects' devices needed for the
    dimension to reach its ceiling. One call is a fact; three is a pattern."""
    contact_shared_trigger: float = 0.70
    contact_shared_full: float = 2.20
    """For the weaker form: not speaking to each other, but both speaking to
    the same third party."""

    affiliation_trigger: float = 0.40
    affiliation_full: float = 1.60

    # ── Spatial ──────────────────────────────────────────────────────────────
    proximity_trigger_km: float = 25.0
    proximity_full_km: float = 2.0
    """Inverted: closer is stronger. The trigger is deliberately tight. Two
    people in the same metropolitan area are not correlated by that fact, and a
    radius generous enough to feel productive would link most of the population
    to most of the rest."""

    min_activity_points_for_place: int = 2
    """A centroid computed from a single observation is that observation, not a
    centre of activity. Below this the dimension is *not evaluable*, which is a
    different statement from "they were far apart"."""

    # ── Temporal ─────────────────────────────────────────────────────────────
    coincidence_window_hours: int = 24
    coincidence_trigger: float = 1.8
    coincidence_full: float = 2.6
    """Lift again, and the tightest range in the model because the measured
    spread is tiny: random pairs run from a median of 1.22 to a maximum of 2.65.

    That narrowness is itself the finding. Temporal coincidence carries very
    little information at this density, which is why its family ceiling is the
    lowest of the five and why it can never corroborate a link. Scoring the raw
    count instead made it fire at full magnitude on 797 of 797 random pairs,
    where it acted as a permanent second voice and pushed 59,056 links into the
    top tier."""
    min_activity_points_for_time: int = 3

    # ── Aggregation ──────────────────────────────────────────────────────────
    dimension_floor: float = 0.25
    """Below this a dimension is recorded but does not count as corroboration.
    Everything that was measured is stored either way — a dimension that
    returned nearly nothing is a finding, and hiding it would make the surviving
    evidence look more unanimous than it was."""

    min_strength: float = 0.30
    """Below this no link is recorded at all. Above zero because in a graph this
    dense, every pair of subjects has *some* faint connection, and a store
    containing all of them would be a store containing no information."""

    established_strength: float = 0.60
    probable_strength: float = 0.45
    established_min_families: int = 2

    # ── Clustering ───────────────────────────────────────────────────────────
    cluster_min_strength: float = 0.45
    cluster_min_size: int = 3
    max_cluster_size: int = 60
    """A component larger than this is reported as an over-merge rather than as
    a discovery. Connected components in a dense graph collapse without warning,
    and a 900-member "cluster" is a bug wearing a finding's clothes."""

    def family_ceiling(self, family: str) -> float:
        """The most a single family of evidence may contribute on its own.

        Not every kind of evidence deserves the same voice. Two subjects being
        active in the same week is real but weak; a direct value-preserving
        transfer between them is not. Capping each family separately means a
        weak family can corroborate a strong one without ever being able to
        establish a link by itself — which is what "spatial proximity alone is
        not a correlation" has to mean in arithmetic.
        """
        return FAMILY_CEILINGS.get(family, 1.0)

    def fingerprint(self) -> str:
        payload = {
            "parameters": asdict(self),
            "family_ceilings": dict(sorted(FAMILY_CEILINGS.items())),
            "dimensions": [
                {
                    "id": d.dimension_id,
                    "family": d.family,
                    "subject_types": sorted(d.subject_types),
                    "reads": sorted(d.reads),
                }
                for d in sorted(DIMENSIONS, key=lambda d: d.dimension_id)
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def short_fingerprint(self) -> str:
        return self.fingerprint()[:12]

    @property
    def method(self) -> str:
        return f"{self.version}+{self.short_fingerprint}"

    @property
    def path_window(self) -> timedelta:
        return timedelta(days=self.path_window_days)

    @property
    def coincidence_window(self) -> timedelta:
        return timedelta(hours=self.coincidence_window_hours)


FAMILIES: tuple[str, ...] = (
    FAMILY_FINANCIAL,
    FAMILY_SOCIAL,
    FAMILY_LOGISTICAL,
    FAMILY_SPATIAL,
    FAMILY_TEMPORAL,
)

# How much each family can contribute to a link's strength by itself.
#
# Financial, social and logistical evidence *identify a pair*: a rare shared
# counterparty, a direct communication, a corridor carrying three shipments in
# the whole world — each is about these two and few others. Spatial and temporal
# evidence do not. Being in the same city, or busy in the same week, is true of
# enormous numbers of unrelated pairs, and a system that let either establish a
# link would spend its time reporting that cities and weeks exist.
#
# Both are kept, because a financial link that also lands in the same week is a
# better link than one that does not. Both are capped below `min_strength`, so
# neither can produce a link alone however extreme it gets. That is the
# arithmetic meaning of "proximity is corroboration, not evidence".
#
# These are a stated policy rather than a derived value. The per-dimension
# precision in the evaluation report is the check on whether the policy was
# right, and it is published whether it flatters these numbers or not.
FAMILY_CEILINGS: dict[str, float] = {
    FAMILY_FINANCIAL: 1.00,
    FAMILY_SOCIAL: 1.00,
    FAMILY_LOGISTICAL: 0.85,
    FAMILY_SPATIAL: 0.25,
    FAMILY_TEMPORAL: 0.20,
}

# Families whose evidence is *about this pair* rather than about a place or a
# week. At least one of these must fire before any link is recorded.
#
# The ceilings alone do not guarantee this. Spatial at its cap (0.25) combined
# with temporal at its cap (0.20) gives a strength of 0.40, which clears
# `min_strength` — so without this rule, two subjects in one city who were both
# busy in March would be recorded as correlated. In practice candidate
# generation never proposes such a pair, because proximity and coincidence are
# deliberately not used for blocking. But that is a property of the blocking,
# not of the model, and a rule that holds only because of how candidates happen
# to be generated is a rule that breaks the first time blocking is tuned.
IDENTIFYING_FAMILIES: frozenset[str] = frozenset(
    {FAMILY_FINANCIAL, FAMILY_SOCIAL, FAMILY_LOGISTICAL}
)

FAMILY_MEANING: dict[str, str] = {
    FAMILY_FINANCIAL: "Money moved between them, or through the same hands.",
    FAMILY_SOCIAL: "They met, spoke, or answer to the same organisation.",
    FAMILY_LOGISTICAL: "They move goods along the same route.",
    FAMILY_SPATIAL: "Their activity is concentrated in the same place.",
    FAMILY_TEMPORAL: "They were active at the same times.",
}


def default_model() -> CorrelationModel:
    return CorrelationModel()
