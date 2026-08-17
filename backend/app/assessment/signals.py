"""The signal registry: what ARGUS looks for, and what it says when it cannot look.

Every signal answers one question with three possible answers — *yes, to this
degree*, *no*, and *I cannot tell* — and the third is a first-class result
rather than a zero. An account with no transaction history is not a
low-velocity account; a person with no registered device has not been quiet.
Collapsing those into "0" is how a system comes to present ignorance as
reassurance, so `evaluable=False` travels all the way to the screen.

Each definition declares the graph data it reads. The declaration is checked
against `ADMISSIBLE_INPUTS` by test, so adding a signal that consults the
generator's answer key fails the build rather than quietly inflating the
model's apparent accuracy.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.assessment.detectors import (
    BurstProfile,
    FundsCycle,
    burst_profile,
    corridor_frequencies,
    find_funds_cycles,
)
from app.assessment.evidence import (
    SUBJECT_ACCOUNT,
    SUBJECT_ORGANIZATION,
    SUBJECT_PERSON,
    SUBJECT_SHIPMENT,
    EvidenceBundle,
)

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from app.assessment.model import RiskModel


@dataclass(frozen=True)
class SignalDefinition:
    """One question the model asks, and the weight of its answer."""

    signal_id: str
    title: str
    question: str
    """Stated as a question, in the words an analyst would use. It is rendered
    verbatim in the UI beside the answer, so a reader can judge whether the
    question was worth asking rather than only whether the number is large."""
    subject_types: frozenset[str]
    weight: float
    family: str
    """Signals in one family draw on the same kind of evidence. Corroboration
    is counted in families rather than in signals, because two findings from
    the same transaction feed are one voice — the same reasoning that makes
    provenance count independence groups rather than observations."""
    reads: tuple[str, ...]
    rationale: str
    """Why this is evidence of anything. A signal that cannot state one has no
    business contributing to a score."""


@dataclass(frozen=True)
class SignalOutcome:
    """The answer for one subject, including the answer "cannot tell"."""

    signal_id: str
    evaluable: bool
    magnitude: float | None
    """0.0–1.0 when evaluable; None when not. Never defaulted to 0."""
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def fired(self) -> bool:
        return self.evaluable and (self.magnitude or 0.0) > 0.0


def _ramp(value: float, trigger: float, full: float) -> float:
    """Linear ramp from `trigger` (0.0) to `full` (1.0), clamped.

    A step function would make a score jump on a rounding difference; an
    unbounded scale would let one extreme subject compress everyone else. The
    ramp's two ends are model parameters and are part of the fingerprint.
    """
    if full <= trigger:
        raise ValueError("full must exceed trigger")
    if value < trigger:
        return 0.0
    return min(1.0, (value - trigger) / (full - trigger))


# ─────────────────────────────────────────────────────────────────────────────
# Definitions
# ─────────────────────────────────────────────────────────────────────────────

FUNDS_CYCLE = SignalDefinition(
    signal_id="funds_cycle",
    title="Circular movement of funds",
    question="Does money leave this subject's accounts and return to them, largely intact?",
    subject_types=frozenset({SUBJECT_PERSON, SUBJECT_ORGANIZATION, SUBJECT_ACCOUNT}),
    weight=5.0,
    family="financial_flow",
    reads=("TRANSACTED_WITH.amount", "TRANSACTED_WITH.timestamp", "OWNS_ACCOUNT"),
    rationale=(
        "Funds that traverse a ring of accounts and come back having lost only a percentage at "
        "each hop have performed no economic function. The pattern is the definition of "
        "layering, and unlike a large transfer it has no ordinary explanation."
    ),
)

TRANSACTION_BURST = SignalDefinition(
    signal_id="transaction_burst",
    title="Sudden transaction velocity",
    question="Did this subject's account activity spike far above its own normal rate?",
    subject_types=frozenset({SUBJECT_PERSON, SUBJECT_ORGANIZATION, SUBJECT_ACCOUNT}),
    weight=4.0,
    family="financial_flow",
    reads=("TRANSACTED_WITH.timestamp", "OWNS_ACCOUNT", "Account.account_id"),
    rationale=(
        "Compared against the account's own history rather than a population average, because "
        "a habitually busy account is not anomalous for being busy. A short window holding many "
        "times the account's usual throughput is a change in behaviour, which is what warrants "
        "a look."
    ),
)

COMMUNICATION_BURST = SignalDefinition(
    signal_id="communication_burst",
    title="Concentrated contact activity",
    question="Did this person's communications concentrate sharply into a short window?",
    subject_types=frozenset({SUBJECT_PERSON}),
    weight=4.0,
    family="communications",
    reads=("COMMUNICATED_WITH.timestamp", "OWNS_DEVICE"),
    rationale=(
        "Coordination leaves a timing signature: contact that is normally spread over months "
        "compressing into two days is a deviation from the person's own pattern. It says "
        "nothing about what was discussed, and the finding is worded accordingly."
    ),
)

OFFSHORE_BANKING = SignalDefinition(
    signal_id="offshore_banking",
    title="Banking outside the holder's region",
    question="Are this subject's accounts held outside the region they are registered in?",
    subject_types=frozenset({SUBJECT_PERSON, SUBJECT_ORGANIZATION, SUBJECT_ACCOUNT}),
    weight=1.0,
    family="banking_profile",
    reads=("Account.offshore", "OWNS_ACCOUNT"),
    rationale=(
        "A weak signal deliberately weighted as one: banking abroad is lawful and common, and "
        "on its own it means very little. It carries a small amount of information only "
        "alongside something else, which is exactly what a low weight expresses."
    ),
)

DIRECTORSHIP_SPREAD = SignalDefinition(
    signal_id="directorship_spread",
    title="Directorships across many organisations",
    question="Does this person hold directorships across an unusual number of organisations?",
    subject_types=frozenset({SUBJECT_PERSON}),
    weight=2.0,
    family="corporate_structure",
    reads=("DIRECTS",),
    rationale=(
        "Serving on several boards is ordinary; serving on many, in a population where most "
        "people serve on none, is a structural position worth knowing about. This is a "
        "statement about corporate structure, not about conduct."
    ),
)

MANIFEST_DISCREPANCY = SignalDefinition(
    signal_id="manifest_discrepancy",
    title="Cargo does not match the declaration",
    question="Does the manifest recorded on arrival differ from what was declared at origin?",
    subject_types=frozenset({SUBJECT_SHIPMENT}),
    weight=4.0,
    family="cargo_records",
    reads=("Shipment.manifest", "Shipment.declared_manifest"),
    rationale=(
        "Two records of the same cargo disagreeing is a documented fact rather than an "
        "inference. It does not establish intent — clerical error produces the same "
        "discrepancy — but it is a hard finding that a person should resolve."
    ),
)

ROUTE_DETOUR = SignalDefinition(
    signal_id="route_detour",
    title="Route substantially longer than direct",
    question="Did this shipment travel materially further than the direct route required?",
    subject_types=frozenset({SUBJECT_SHIPMENT}),
    weight=3.0,
    family="route_geometry",
    reads=("Shipment.detour_ratio",),
    rationale=(
        "A measured ratio of distance travelled to distance required. Freight is priced by "
        "distance, so a long detour costs someone money and is worth an explanation."
    ),
)

RARE_CORRIDOR = SignalDefinition(
    signal_id="rare_corridor",
    title="Seldom-used trade corridor",
    question="How much other freight moves between these two regions?",
    subject_types=frozenset({SUBJECT_SHIPMENT}),
    weight=2.0,
    family="route_geometry",
    reads=("Shipment.origin_region", "Shipment.destination_region"),
    rationale=(
        "Rarity is measured against the corridors this dataset actually contains, so the claim "
        "is 'few other shipments do this', which ARGUS can support — not 'this route is "
        "implausible', which it has no source for."
    ),
)

SIGNALS: tuple[SignalDefinition, ...] = (
    FUNDS_CYCLE,
    TRANSACTION_BURST,
    COMMUNICATION_BURST,
    OFFSHORE_BANKING,
    DIRECTORSHIP_SPREAD,
    MANIFEST_DISCREPANCY,
    ROUTE_DETOUR,
    RARE_CORRIDOR,
)

SIGNALS_BY_ID: dict[str, SignalDefinition] = {s.signal_id: s for s in SIGNALS}


def signals_for(subject_type: str) -> tuple[SignalDefinition, ...]:
    return tuple(s for s in SIGNALS if subject_type in s.subject_types)


# ─────────────────────────────────────────────────────────────────────────────
# Precomputed context
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SignalContext:
    """Everything derived once per run, so per-subject evaluation is a lookup.

    Built from the bundle and the model together: the model's thresholds decide
    what the detectors search for, so a context is only valid for the model that
    produced it. Both fingerprints are recorded on the run.
    """

    bundle: EvidenceBundle
    model: RiskModel

    cycles: list[FundsCycle] = field(default_factory=list)
    cycle_search_truncated: bool = False
    cycles_by_account: dict[str, list[FundsCycle]] = field(default_factory=dict)

    account_bursts: dict[str, BurstProfile] = field(default_factory=dict)
    account_transfer_counts: dict[str, int] = field(default_factory=dict)
    contact_bursts: dict[str, BurstProfile] = field(default_factory=dict)
    contact_counts: dict[str, int] = field(default_factory=dict)

    accounts_by_owner: dict[str, list[str]] = field(default_factory=dict)
    offshore_by_account: dict[str, bool] = field(default_factory=dict)
    directorship_counts: dict[str, int] = field(default_factory=dict)

    shipments: dict[str, Any] = field(default_factory=dict)
    corridor_share: dict[tuple[str, str], float] = field(default_factory=dict)


def build_context(bundle: EvidenceBundle, model: RiskModel) -> SignalContext:
    ctx = SignalContext(bundle=bundle, model=model)

    ctx.cycles, ctx.cycle_search_truncated = find_funds_cycles(
        bundle.transfers,
        retention_low=model.cycle_retention_low,
        retention_high=model.cycle_retention_high,
        window=timedelta(days=model.cycle_window_days),
        min_hops=model.cycle_min_hops,
        max_hops=model.cycle_max_hops,
    )
    by_account: dict[str, list[FundsCycle]] = defaultdict(list)
    for cycle in ctx.cycles:
        for account in set(cycle.accounts):
            by_account[account].append(cycle)
    ctx.cycles_by_account = dict(by_account)

    times_by_account: dict[str, list] = defaultdict(list)
    for transfer in bundle.transfers:
        times_by_account[transfer.source_account].append(transfer.occurred_at)
        times_by_account[transfer.target_account].append(transfer.occurred_at)
    window = timedelta(hours=model.transaction_window_hours)
    for account, times in times_by_account.items():
        ctx.account_transfer_counts[account] = len(times)
        if len(times) < model.transaction_min_events:
            continue
        profile = burst_profile(times, window=window, floor_expected=model.burst_floor_expected)
        if profile is not None:
            ctx.account_bursts[account] = profile

    times_by_person: dict[str, list] = defaultdict(list)
    for contact in bundle.contacts:
        times_by_person[contact.person_a].append(contact.occurred_at)
        if contact.person_b != contact.person_a:
            times_by_person[contact.person_b].append(contact.occurred_at)
    contact_window = timedelta(hours=model.contact_window_hours)
    for person, times in times_by_person.items():
        ctx.contact_counts[person] = len(times)
        if len(times) < model.contact_min_events:
            continue
        profile = burst_profile(
            times, window=contact_window, floor_expected=model.burst_floor_expected
        )
        if profile is not None:
            ctx.contact_bursts[person] = profile

    owned: dict[str, list[str]] = defaultdict(list)
    for fact in bundle.accounts:
        ctx.offshore_by_account[fact.account_id] = fact.offshore
        if fact.owner_ref:
            owned[fact.owner_ref].append(fact.account_id)
    ctx.accounts_by_owner = {ref: sorted(ids) for ref, ids in owned.items()}

    counts: dict[str, int] = defaultdict(int)
    for directorship in bundle.directorships:
        counts[directorship.person_ref] += 1
    ctx.directorship_counts = dict(counts)

    ctx.shipments = {s.shipment_id: s for s in bundle.shipments}
    ctx.corridor_share = corridor_frequencies(
        [
            (s.origin_region, s.destination_region)
            for s in bundle.shipments
            if s.origin_region and s.destination_region
        ]
    )
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# Evaluation
# ─────────────────────────────────────────────────────────────────────────────


def _accounts_of(subject_ref: str, subject_type: str, ctx: SignalContext) -> list[str]:
    if subject_type == SUBJECT_ACCOUNT:
        return [subject_ref]
    return ctx.accounts_by_owner.get(subject_ref, [])


def _not_evaluable(signal: SignalDefinition, why: str) -> SignalOutcome:
    return SignalOutcome(signal_id=signal.signal_id, evaluable=False, magnitude=None, summary=why)


def _evaluate_funds_cycle(refs: list[str], ctx: SignalContext) -> SignalOutcome:
    if not refs:
        return _not_evaluable(
            FUNDS_CYCLE, "No account is linked to this subject, so its funds cannot be traced."
        )

    hits = [cycle for ref in refs for cycle in ctx.cycles_by_account.get(ref, [])]
    unique = {cycle.transfers: cycle for cycle in hits}
    if not unique:
        return SignalOutcome(
            signal_id=FUNDS_CYCLE.signal_id,
            evaluable=True,
            magnitude=0.0,
            summary=(
                f"No circular flow found across {len(refs)} linked account(s)."
                + (
                    " The cycle search stopped at its path limit, so this is not a complete"
                    " answer."
                    if ctx.cycle_search_truncated
                    else ""
                )
            ),
            detail={"accounts_examined": len(refs), "search_truncated": ctx.cycle_search_truncated},
        )

    strongest = max(unique.values(), key=lambda c: (c.hops, c.total_amount))
    magnitude = _ramp(
        float(strongest.hops), ctx.model.cycle_hops_trigger, ctx.model.cycle_hops_full
    )
    magnitude = max(magnitude, ctx.model.cycle_minimum_magnitude)
    return SignalOutcome(
        signal_id=FUNDS_CYCLE.signal_id,
        evaluable=True,
        magnitude=round(magnitude, 4),
        summary=(
            f"Funds moved through a {strongest.hops}-account ring and returned to the start "
            f"within {strongest.span_hours:.0f}h, retaining "
            f"{strongest.retained_fraction * 100:.0f}% of the opening amount."
        ),
        detail={
            "cycles": len(unique),
            "hops": strongest.hops,
            "accounts": list(strongest.accounts),
            "transfers": list(strongest.transfers),
            "total_amount": strongest.total_amount,
            "retained_fraction": strongest.retained_fraction,
            "span_hours": strongest.span_hours,
        },
    )


def _evaluate_transaction_burst(refs: list[str], ctx: SignalContext) -> SignalOutcome:
    if not refs:
        return _not_evaluable(
            TRANSACTION_BURST, "No account is linked to this subject, so it has no activity rate."
        )
    profiles = {ref: ctx.account_bursts[ref] for ref in refs if ref in ctx.account_bursts}
    if not profiles:
        observed = sum(ctx.account_transfer_counts.get(ref, 0) for ref in refs)
        return _not_evaluable(
            TRANSACTION_BURST,
            f"Too little transaction history to establish a normal rate "
            f"({observed} transfer(s) across {len(refs)} account(s); "
            f"{ctx.model.transaction_min_events} needed on a single account).",
        )

    ref, best = max(profiles.items(), key=lambda item: (item[1].ratio, item[1].peak_count))
    if best.peak_count < ctx.model.transaction_min_peak or best.ratio < ctx.model.burst_ratio_trigger:
        return SignalOutcome(
            signal_id=TRANSACTION_BURST.signal_id,
            evaluable=True,
            magnitude=0.0,
            summary=(
                f"Busiest {ctx.model.transaction_window_hours}h window held {best.peak_count} "
                f"transfer(s), {best.ratio:.1f}× the account's own average — within normal "
                f"variation."
            ),
            detail={"account": ref, "peak_count": best.peak_count, "ratio": best.ratio},
        )

    magnitude = _ramp(best.ratio, ctx.model.burst_ratio_trigger, ctx.model.burst_ratio_full)
    return SignalOutcome(
        signal_id=TRANSACTION_BURST.signal_id,
        evaluable=True,
        magnitude=round(magnitude, 4),
        summary=(
            f"{best.peak_count} transfers on {ref} inside "
            f"{ctx.model.transaction_window_hours}h — {best.ratio:.0f}× the "
            f"{best.expected_count:.1f} that account's own rate predicts."
        ),
        detail={
            "account": ref,
            "peak_count": best.peak_count,
            "expected_count": best.expected_count,
            "ratio": best.ratio,
            "peak_start": best.peak_start.isoformat() if best.peak_start else None,
            "history_events": best.event_count,
            "history_hours": best.span_hours,
        },
    )


def _evaluate_communication_burst(subject_ref: str, ctx: SignalContext) -> SignalOutcome:
    if subject_ref not in ctx.bundle.persons_with_devices:
        return _not_evaluable(
            COMMUNICATION_BURST,
            "No device is registered to this person, so ARGUS observes no communications "
            "either way — this is absence of collection, not absence of contact.",
        )
    profile = ctx.contact_bursts.get(subject_ref)
    if profile is None:
        observed = ctx.contact_counts.get(subject_ref, 0)
        return _not_evaluable(
            COMMUNICATION_BURST,
            f"Only {observed} communication(s) observed; "
            f"{ctx.model.contact_min_events} are needed before a normal rate means anything.",
        )

    if profile.peak_count < ctx.model.contact_min_peak or profile.ratio < ctx.model.burst_ratio_trigger:
        return SignalOutcome(
            signal_id=COMMUNICATION_BURST.signal_id,
            evaluable=True,
            magnitude=0.0,
            summary=(
                f"Busiest {ctx.model.contact_window_hours}h window held {profile.peak_count} "
                f"contact(s), {profile.ratio:.1f}× this person's own average."
            ),
            detail={"peak_count": profile.peak_count, "ratio": profile.ratio},
        )

    magnitude = _ramp(profile.ratio, ctx.model.burst_ratio_trigger, ctx.model.burst_ratio_full)
    return SignalOutcome(
        signal_id=COMMUNICATION_BURST.signal_id,
        evaluable=True,
        magnitude=round(magnitude, 4),
        summary=(
            f"{profile.peak_count} communications inside {ctx.model.contact_window_hours}h — "
            f"{profile.ratio:.0f}× this person's own rate over "
            f"{profile.span_hours / 24:.0f} days of history."
        ),
        detail={
            "peak_count": profile.peak_count,
            "expected_count": profile.expected_count,
            "ratio": profile.ratio,
            "peak_start": profile.peak_start.isoformat() if profile.peak_start else None,
            "history_events": profile.event_count,
            "history_hours": profile.span_hours,
        },
    )


def _evaluate_offshore(refs: list[str], ctx: SignalContext) -> SignalOutcome:
    if not refs:
        return _not_evaluable(OFFSHORE_BANKING, "No account is linked to this subject.")
    offshore = [ref for ref in refs if ctx.offshore_by_account.get(ref)]
    share = len(offshore) / len(refs)
    if not offshore:
        return SignalOutcome(
            signal_id=OFFSHORE_BANKING.signal_id,
            evaluable=True,
            magnitude=0.0,
            summary=f"All {len(refs)} linked account(s) are held in the holder's own region.",
            detail={"accounts": len(refs), "offshore": 0},
        )
    return SignalOutcome(
        signal_id=OFFSHORE_BANKING.signal_id,
        evaluable=True,
        magnitude=round(share, 4),
        summary=(
            f"{len(offshore)} of {len(refs)} linked account(s) are held outside the holder's "
            f"region."
        ),
        detail={"accounts": len(refs), "offshore": len(offshore), "offshore_accounts": offshore},
    )


def _evaluate_directorships(subject_ref: str, ctx: SignalContext) -> SignalOutcome:
    count = ctx.directorship_counts.get(subject_ref, 0)
    if count < ctx.model.directorship_trigger:
        return SignalOutcome(
            signal_id=DIRECTORSHIP_SPREAD.signal_id,
            evaluable=True,
            magnitude=0.0,
            summary=f"Holds {count} directorship(s).",
            detail={"directorships": count},
        )
    magnitude = _ramp(
        float(count), ctx.model.directorship_trigger, ctx.model.directorship_full
    )
    return SignalOutcome(
        signal_id=DIRECTORSHIP_SPREAD.signal_id,
        evaluable=True,
        magnitude=round(magnitude, 4),
        summary=f"Holds directorships in {count} organisations.",
        detail={"directorships": count},
    )


def _evaluate_manifest(subject_ref: str, ctx: SignalContext) -> SignalOutcome:
    shipment = ctx.shipments.get(subject_ref)
    if shipment is None or shipment.manifest is None or shipment.declared_manifest is None:
        return _not_evaluable(
            MANIFEST_DISCREPANCY, "Both a declared and an arrival manifest are needed to compare."
        )
    if shipment.manifest == shipment.declared_manifest:
        return SignalOutcome(
            signal_id=MANIFEST_DISCREPANCY.signal_id,
            evaluable=True,
            magnitude=0.0,
            summary="Arrival manifest matches the declaration.",
            detail={"manifest": shipment.manifest},
        )
    return SignalOutcome(
        signal_id=MANIFEST_DISCREPANCY.signal_id,
        evaluable=True,
        magnitude=1.0,
        summary=(
            f"Declared as {shipment.declared_manifest!r} at origin; recorded as "
            f"{shipment.manifest!r} on arrival."
        ),
        detail={"declared": shipment.declared_manifest, "arrived": shipment.manifest},
    )


def _evaluate_detour(subject_ref: str, ctx: SignalContext) -> SignalOutcome:
    shipment = ctx.shipments.get(subject_ref)
    if shipment is None or shipment.detour_ratio is None:
        return _not_evaluable(
            ROUTE_DETOUR, "No routed distance was recorded, so no detour can be measured."
        )
    ratio = shipment.detour_ratio
    if ratio < ctx.model.detour_trigger:
        return SignalOutcome(
            signal_id=ROUTE_DETOUR.signal_id,
            evaluable=True,
            magnitude=0.0,
            summary=f"Routed distance is {ratio:.2f}× the direct distance.",
            detail={"detour_ratio": ratio},
        )
    return SignalOutcome(
        signal_id=ROUTE_DETOUR.signal_id,
        evaluable=True,
        magnitude=round(_ramp(ratio, ctx.model.detour_trigger, ctx.model.detour_full), 4),
        summary=f"Travelled {ratio:.2f}× the direct distance between origin and destination.",
        detail={"detour_ratio": ratio},
    )


def _evaluate_corridor(subject_ref: str, ctx: SignalContext) -> SignalOutcome:
    shipment = ctx.shipments.get(subject_ref)
    if shipment is None or not shipment.origin_region or not shipment.destination_region:
        return _not_evaluable(RARE_CORRIDOR, "Origin or destination region is not recorded.")
    corridor = (shipment.origin_region, shipment.destination_region)
    share = ctx.corridor_share.get(corridor)
    if share is None:
        return _not_evaluable(RARE_CORRIDOR, "No corridor traffic is recorded to compare against.")
    if share >= ctx.model.corridor_trigger:
        return SignalOutcome(
            signal_id=RARE_CORRIDOR.signal_id,
            evaluable=True,
            magnitude=0.0,
            summary=(
                f"{share * 100:.1f}% of shipments run {corridor[0]} → {corridor[1]}; an "
                f"ordinary corridor."
            ),
            detail={"corridor": list(corridor), "share": round(share, 5)},
        )
    # Rarer is stronger, so the ramp runs downward from the trigger to the floor.
    magnitude = _ramp(
        ctx.model.corridor_trigger - share,
        0.0,
        ctx.model.corridor_trigger - ctx.model.corridor_full,
    )
    return SignalOutcome(
        signal_id=RARE_CORRIDOR.signal_id,
        evaluable=True,
        magnitude=round(magnitude, 4),
        summary=(
            f"Only {share * 100:.2f}% of shipments in this dataset run "
            f"{corridor[0]} → {corridor[1]}."
        ),
        detail={"corridor": list(corridor), "share": round(share, 5)},
    )


def evaluate_subject(
    subject_ref: str, subject_type: str, ctx: SignalContext
) -> list[SignalOutcome]:
    """Every signal that applies to this subject type, evaluated in registry order."""
    accounts = _accounts_of(subject_ref, subject_type, ctx)
    outcomes: list[SignalOutcome] = []
    for signal in signals_for(subject_type):
        if signal is FUNDS_CYCLE:
            outcomes.append(_evaluate_funds_cycle(accounts, ctx))
        elif signal is TRANSACTION_BURST:
            outcomes.append(_evaluate_transaction_burst(accounts, ctx))
        elif signal is COMMUNICATION_BURST:
            outcomes.append(_evaluate_communication_burst(subject_ref, ctx))
        elif signal is OFFSHORE_BANKING:
            outcomes.append(_evaluate_offshore(accounts, ctx))
        elif signal is DIRECTORSHIP_SPREAD:
            outcomes.append(_evaluate_directorships(subject_ref, ctx))
        elif signal is MANIFEST_DISCREPANCY:
            outcomes.append(_evaluate_manifest(subject_ref, ctx))
        elif signal is ROUTE_DETOUR:
            outcomes.append(_evaluate_detour(subject_ref, ctx))
        elif signal is RARE_CORRIDOR:
            outcomes.append(_evaluate_corridor(subject_ref, ctx))
        else:  # pragma: no cover - unreachable while SIGNALS and this match
            raise AssertionError(f"no evaluator wired for signal {signal.signal_id}")
    return outcomes


FAMILIES: tuple[str, ...] = tuple(sorted({s.family for s in SIGNALS}))
