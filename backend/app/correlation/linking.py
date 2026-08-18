"""Turning dimension outcomes into a link — or declining to.

The combination rule is the whole argument of this module, so it is worth
stating plainly before the code:

    strength = noisy-OR over families
             = 1 - Π_families (1 - ceiling(family) × max(dimensions in family))

Three decisions are packed into that line.

**Maximum within a family.** Shared counterparty and funds path both read the
same transaction ledger. Treating them as two independent votes would count one
fact twice and manufacture confidence out of it. Taking the strongest and
discarding the rest understates the evidence, which is the correct direction to
be wrong in.

**Noisy-OR across families.** Independence between families is a real
assumption and roughly defensible: who someone pays and who they stood next to
at an event are different observations of the world. Noisy-OR is monotone, so
extra evidence can never lower a strength — the dilution defect that made
Phase 5's first scoring scheme unusable cannot recur here — and it is bounded
below 1, so no accumulation of circumstantial evidence ever reaches certainty.

**Ceilings before combination.** A family's ceiling caps its voice before it
enters the product, which is what makes "spatial proximity alone is not a
correlation" true in arithmetic rather than only in the documentation.

## Coverage, again

A pair where six of eight dimensions could not be evaluated has not been
examined; it has been glanced at. Coverage travels with every link for the same
reason it travels with every assessment, and a link that clears the strength
threshold on thin coverage is reported as `possible` however strong its one
surviving dimension was.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.correlation.dimensions import (
    DIMENSIONS,
    CorrelationContext,
    DimensionOutcome,
    evaluate_pair,
)
from app.correlation.evidence import Anchor
from app.correlation.measures import noisy_or
from app.correlation.model import (
    IDENTIFYING_FAMILIES,
    TIER_ESTABLISHED,
    TIER_POSSIBLE,
    TIER_PROBABLE,
    CorrelationModel,
)
from app.models.provenance import Credibility, Reliability


@dataclass(frozen=True)
class FamilyContribution:
    """What one family of evidence contributed, and which dimension carried it."""

    family: str
    dimension_id: str
    raw: float
    """The winning dimension's own magnitude, before the family ceiling."""
    contribution: float
    """What actually entered the combination: `raw × ceiling`. Shown alongside
    `raw` so a capped family is visibly capped rather than quietly small."""
    ceiling: float


@dataclass(frozen=True)
class CorrelationLink:
    """ARGUS's claim that two of its findings belong together, with the reasons."""

    ref_a: str
    ref_b: str
    type_a: str
    type_b: str
    strength: float
    tier: str
    coverage: float
    """Share of the dimensions that apply to this pair which could be evaluated."""
    evaluable_dimensions: int
    applicable_dimensions: int
    families: tuple[FamilyContribution, ...]
    corroborating_families: tuple[str, ...]
    """Identifying families scoring at or above the corroboration floor. The
    count of these, not the strength, is what separates `established` from
    `probable`."""
    outcomes: tuple[DimensionOutcome, ...]
    model_fingerprint: str
    model_version: str
    computed_at: datetime

    # Declared last only because it carries a default; it belongs beside
    # `corroborating_families` and is read alongside it everywhere.
    supporting_families: tuple[str, ...] = ()
    """Non-identifying families that also cleared the floor. These add to the
    strength but never to the corroboration count: being in the same place, or
    busy in the same week, is not a second opinion about a pair. Recorded
    separately rather than dropped, so a reader can see what contributed."""

    @property
    def key(self) -> tuple[str, str]:
        return (self.ref_a, self.ref_b)

    @property
    def fired(self) -> tuple[DimensionOutcome, ...]:
        return tuple(o for o in self.outcomes if o.fired)

    @property
    def unevaluable(self) -> tuple[DimensionOutcome, ...]:
        return tuple(o for o in self.outcomes if not o.evaluable)

    @property
    def reliability(self) -> Reliability:
        """F, for the same reason every assessment is F.

        The source is ARGUS's own algorithm, whose precision has been measured
        against exactly one synthetic world. That establishes the code does what
        it says on that world. It does not establish a track record, and rating
        it above F would launder one measurement into one.
        """
        return Reliability.F

    @property
    def credibility(self) -> Credibility:
        if len(self.corroborating_families) >= 2:
            return Credibility.PROBABLY_TRUE
        if self.corroborating_families:
            return Credibility.POSSIBLY_TRUE
        return Credibility.CANNOT_BE_JUDGED

    def basis(self) -> str:
        """One sentence naming what holds the link together, and what does not.

        Written here rather than in the UI so that every surface — the graph,
        the entity profile, the correlation page, an eventual alert — says the
        same thing about the same link. A strength rendered with its reasons in
        one place and bare in another is how the flattering version travels.
        """
        if not self.fired:
            return "No dimension fired. This link should not exist; it is a defect if shown."

        reasons = "; ".join(o.summary for o in self.fired)
        families = len(self.corroborating_families)
        if families >= 2:
            lead = f"{families} independent kinds of evidence agree"
        elif families == 1:
            lead = f"One kind of evidence supports this ({self.corroborating_families[0]}), uncorroborated"
        else:
            lead = "Nothing reached the corroboration floor"

        blind = len(self.unevaluable)
        tail = ""
        if blind:
            tail = (
                f" {blind} of {self.applicable_dimensions} dimensions could not be evaluated, "
                f"so this is what was visible, not all there is."
            )
        return f"{lead}. {reasons}.{tail}"


def _tier_for(
    strength: float,
    corroborating: tuple[str, ...],
    coverage: float,
    model: CorrelationModel,
) -> str | None:
    """The tier, or None when the link is too weak to record at all.

    Two gates precede the strength comparison.

    An **identifying family** must have fired. Proximity and coincidence are
    corroboration; between them they can reach 0.40, which clears
    `min_strength`, and a link resting on nothing else would be the claim that
    two people in one city who were both busy in March are connected.

    **Corroboration** gates the top tier, mirroring the way coverage gates the
    assessment bands. A single dimension at 0.95 is one observation, however
    emphatic, and calling it `established` would let one measurement speak with
    the authority of several.
    """
    families = len(corroborating)
    if not IDENTIFYING_FAMILIES.intersection(corroborating):
        return None
    if strength < model.min_strength:
        return None
    if (
        strength >= model.established_strength
        and families >= model.established_min_families
        and coverage >= 0.5
    ):
        return TIER_ESTABLISHED
    if strength >= model.probable_strength:
        return TIER_PROBABLE
    return TIER_POSSIBLE


def link_pair(ctx: CorrelationContext, a: Anchor, b: Anchor) -> CorrelationLink | None:
    """Score one pair. Returns None when nothing worth recording was found."""
    if a.ref == b.ref:
        return None

    # A subject and something it structurally contains are one entity seen
    # twice, not two entities that might be connected. Their counterparties are
    # identical by construction, so every financial dimension scores them at
    # full strength — and against the live graph this produced 38,142 links of
    # the form "PRS-0000834 is strongly correlated with ACC-0000003", which is
    # ARGUS discovering that a person holds their own bank account.
    if ctx.same_entity(a.ref, b.ref):
        return None

    left, right = (a, b) if a.ref <= b.ref else (b, a)
    outcomes = evaluate_pair(ctx, left, right)
    if not outcomes:
        return None

    model = ctx.model
    evaluable = [o for o in outcomes if o.evaluable]
    coverage = len(evaluable) / len(outcomes) if outcomes else 0.0

    best_by_family: dict[str, DimensionOutcome] = {}
    for outcome in evaluable:
        current = best_by_family.get(outcome.family)
        if current is None or (outcome.magnitude or 0.0) > (current.magnitude or 0.0):
            best_by_family[outcome.family] = outcome

    families: list[FamilyContribution] = []
    for family, outcome in sorted(best_by_family.items()):
        raw = outcome.magnitude or 0.0
        ceiling = model.family_ceiling(family)
        families.append(
            FamilyContribution(
                family=family,
                dimension_id=outcome.dimension_id,
                raw=round(raw, 4),
                contribution=round(raw * ceiling, 4),
                ceiling=ceiling,
            )
        )

    strength = noisy_or(f.contribution for f in families)

    # Corroboration counts *identifying* families only. Spatial and temporal
    # evidence still adds to the strength, but neither is a second opinion about
    # a pair: being in one city or busy in one week is true of enormous numbers
    # of unrelated subjects. Counting them on the raw magnitude — as the first
    # version did — meant a saturated coincidence score acted as a full
    # corroborating voice, and 59,056 of 91,212 links came out `established`.
    corroborating = tuple(
        f.family
        for f in families
        if f.raw >= model.dimension_floor and f.family in IDENTIFYING_FAMILIES
    )
    supporting = tuple(
        f.family
        for f in families
        if f.raw >= model.dimension_floor and f.family not in IDENTIFYING_FAMILIES
    )
    tier = _tier_for(strength, corroborating, coverage, model)
    if tier is None:
        return None

    return CorrelationLink(
        ref_a=left.ref,
        ref_b=right.ref,
        type_a=left.subject_type,
        type_b=right.subject_type,
        strength=round(strength, 4),
        tier=tier,
        coverage=round(coverage, 4),
        evaluable_dimensions=len(evaluable),
        applicable_dimensions=len(outcomes),
        families=tuple(families),
        corroborating_families=corroborating,
        supporting_families=supporting,
        outcomes=tuple(outcomes),
        model_fingerprint=model.short_fingerprint,
        model_version=model.version,
        computed_at=datetime.now(UTC),
    )


def dimension_catalogue() -> list[dict]:
    """The registry, as the API publishes it.

    Every dimension is listed whether or not it ever fires, together with the
    question it asks and the inputs it is permitted to read. A model that only
    describes the parts of itself that produced results is not a description of
    a model.
    """
    return [
        {
            "dimension_id": d.dimension_id,
            "family": d.family,
            "label": d.label,
            "question": d.question,
            "rationale": d.rationale,
            "reads": sorted(d.reads),
            "subject_types": sorted(d.subject_types),
        }
        for d in DIMENSIONS
    ]
