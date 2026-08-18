"""Which pairs are worth scoring at all.

Scoring every pair of anchors is quadratic: eight thousand findings is
thirty-two million comparisons, and the overwhelming majority of them are two
subjects with nothing whatsoever between them. This is the same blocking
problem Phase 4 solved for entity resolution, and it is solved the same way —
build inverted indexes on things that could constitute a link, and only compare
subjects that share one.

## What may generate a candidate, and what may not

Only the **identifying** dimensions block: shared counterparty, funds path,
co-attendance, communication, affiliation, shared corridor. Proximity and
coincidence never do.

That is not a performance decision. Blocking on location would propose every
pair in a city and blocking on time would propose every pair in a week, so both
would reinstate the quadratic behaviour while filling the candidate set with
pairs that cannot, by the family ceilings, produce a link. The model states the
same rule independently in `IDENTIFYING_FAMILIES`, so the guarantee does not
rest on this module remembering it.

## Fan-out, and what is lost

A key touched by more anchors than `max_shared_key_fanout` generates no pairs.
A counterparty account used by three thousand subjects would propose four and a
half million pairs, every one of which the rarity weighting would then score at
approximately nothing. Skipping it is not a loss of evidence — it is declining
to compute a number already known to be zero.

The skipped keys are counted and reported on the run, because "we did not look
there" is a fact about a result, and a candidate count with no note attached
would read as exhaustive.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from app.correlation.dimensions import CorrelationContext


@dataclass
class CandidateSet:
    """The pairs to score, and an honest account of how they were chosen."""

    pairs: set[tuple[str, str]] = field(default_factory=set)

    keys_considered: int = 0
    keys_skipped: int = 0
    """Keys whose fan-out exceeded the cap. Reported, never hidden."""

    skipped_examples: list[str] = field(default_factory=list)
    pairs_by_source: dict[str, int] = field(default_factory=dict)
    """How many pairs each blocking index proposed, before de-duplication.
    Useful for the same reason per-signal counts were useful in Phase 5: an
    index proposing nothing is either a dead index or a dead dimension, and
    without this the two look identical."""

    def add(self, a: str, b: str) -> None:
        if a == b:
            return
        self.pairs.add((a, b) if a <= b else (b, a))


def _block_on(
    index: dict[str, set[str]],
    candidates: CandidateSet,
    *,
    source: str,
    max_fanout: int,
) -> None:
    """Emit every pair sharing a key, skipping keys that are too common."""
    proposed = 0
    for key, members in index.items():
        candidates.keys_considered += 1
        if len(members) < 2:
            continue
        if len(members) > max_fanout:
            candidates.keys_skipped += 1
            if len(candidates.skipped_examples) < 10:
                candidates.skipped_examples.append(f"{source}:{key} ({len(members)} subjects)")
            continue
        ordered = sorted(members)
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                candidates.add(left, right)
                proposed += 1
    candidates.pairs_by_source[source] = candidates.pairs_by_source.get(source, 0) + proposed


def generate(ctx: CorrelationContext) -> CandidateSet:
    """Propose the pairs worth scoring."""
    candidates = CandidateSet()
    anchors = ctx.evidence.anchors
    max_fanout = ctx.model.max_shared_key_fanout

    # ── Shared counterparty ──────────────────────────────────────────────────
    by_counterparty: dict[str, set[str]] = defaultdict(set)
    for ref, partners in ctx.counterparties.items():
        for account in partners:
            by_counterparty[account].add(ref)
    _block_on(by_counterparty, candidates, source="shared_counterparty", max_fanout=max_fanout)

    # ── Funds path ───────────────────────────────────────────────────────────
    # Not a shared key: reachability is directed and asymmetric, so this walks
    # each anchor's reachable set and pairs it with whoever owns what it found.
    owner_of_account: dict[str, set[str]] = defaultdict(set)
    for ref, owned in ctx.accounts_of.items():
        for account in owned:
            owner_of_account[account].add(ref)

    path_pairs = 0
    for ref, reached in ctx.reach.items():
        for account in reached:
            for other in owner_of_account.get(account, ()):  # noqa: PERF401
                if other != ref:
                    candidates.add(ref, other)
                    path_pairs += 1
    candidates.pairs_by_source["funds_path"] = path_pairs

    # ── Co-attendance ────────────────────────────────────────────────────────
    by_event: dict[str, set[str]] = defaultdict(set)
    for ref, events in ctx.events_of.items():
        for event in events:
            by_event[event].add(ref)
    _block_on(by_event, candidates, source="co_attendance", max_fanout=max_fanout)

    # ── Communication ────────────────────────────────────────────────────────
    # Two indexes: people who spoke to each other, and people who spoke to the
    # same third party. The first is exact and needs no fan-out cap — a direct
    # contact is a pair, not a key — while the second is a shared key and does.
    direct = 0
    for ref, contacts in ctx.correspondents.items():
        if ref not in anchors:
            continue
        for other in contacts:
            if other in anchors and other != ref:
                candidates.add(ref, other)
                direct += 1
    candidates.pairs_by_source["communication_direct"] = direct

    by_correspondent: dict[str, set[str]] = defaultdict(set)
    for ref, contacts in ctx.correspondents.items():
        if ref not in anchors:
            continue
        for other in contacts:
            by_correspondent[other].add(ref)
    _block_on(
        by_correspondent, candidates, source="communication_shared", max_fanout=max_fanout
    )

    # ── Affiliation ──────────────────────────────────────────────────────────
    by_org: dict[str, set[str]] = defaultdict(set)
    for ref, orgs in ctx.orgs_of.items():
        for org in orgs:
            by_org[org].add(ref)
    _block_on(by_org, candidates, source="affiliation", max_fanout=max_fanout)

    # ── Shared corridor ──────────────────────────────────────────────────────
    by_corridor: dict[str, set[str]] = defaultdict(set)
    for ref, corridor in ctx.corridor_of.items():
        if ref in anchors:
            by_corridor[corridor].add(ref)
    _block_on(by_corridor, candidates, source="shared_corridor", max_fanout=max_fanout)

    # Anything proposed for a subject that is not an anchor cannot be scored —
    # there is no assessment behind it to correlate. Dropped here rather than
    # inside each index so the rule is stated once.
    candidates.pairs = {
        (a, b) for a, b in candidates.pairs if a in anchors and b in anchors
    }
    return candidates
