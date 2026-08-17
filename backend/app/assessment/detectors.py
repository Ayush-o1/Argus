"""The algorithms, separated from the scoring that uses them.

Each function here answers one factual question about a set of events and
returns what it found, including when it found nothing. None of them knows what
a risk score is, which is what makes them testable against hand-built inputs
whose right answer is obvious by inspection.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.assessment.evidence import Transfer

# ─────────────────────────────────────────────────────────────────────────────
# Value-preserving funds cycles
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FundsCycle:
    """A closed loop of transfers in which value is largely preserved at each
    hop and the whole loop completes inside a bounded window.

    The shape, not the amount, is what carries meaning: money that leaves an
    account and returns to it having lost only a percentage at each step has
    done no economic work. A single large transfer is unremarkable; the same
    sum going around a ring is the layering pattern by definition.
    """

    accounts: tuple[str, ...]
    """The loop, starting and ending at the same account."""
    transfers: tuple[str, ...]
    total_amount: float
    retained_fraction: float
    """Value at the end of the loop as a share of value at the start."""
    span_hours: float

    @property
    def hops(self) -> int:
        return len(self.transfers)


def _within(a: datetime, b: datetime, window: timedelta) -> bool:
    return abs((a - b).total_seconds()) <= window.total_seconds()


def find_funds_cycles(
    transfers: list[Transfer],
    *,
    retention_low: float,
    retention_high: float,
    window: timedelta,
    min_hops: int,
    max_hops: int,
    max_paths: int = 500_000,
) -> tuple[list[FundsCycle], bool]:
    """Find value-preserving cycles. Returns the cycles and whether the search
    was truncated.

    Hops are *not* required to be in ascending time order, only to fall inside
    one window. Real feeds carry clock skew and out-of-order delivery, and this
    world's own planted chains are frequently out of order — a detector that
    insisted on monotonic timestamps found none of them at all, which was how
    this requirement was discovered rather than assumed.

    The truncation flag is returned rather than logged because a search that
    stopped early has under-reported, and a caller that presents its output as
    complete would be making exactly the kind of claim this phase removes.
    """
    if min_hops < 2 or max_hops < min_hops:
        raise ValueError("min_hops must be >= 2 and max_hops >= min_hops")

    outgoing: dict[str, list[Transfer]] = defaultdict(list)
    for transfer in transfers:
        outgoing[transfer.source_account].append(transfer)

    # The value-preserving successor relation. Building it once turns the cycle
    # search from a walk over 40k edges into a walk over the few hundred pairs
    # that could possibly continue a chain.
    successors: dict[str, list[Transfer]] = defaultdict(list)
    by_id: dict[str, Transfer] = {t.transfer_id: t for t in transfers}
    for transfer in transfers:
        if transfer.amount <= 0:
            continue
        for candidate in outgoing.get(transfer.target_account, ()):
            if candidate.transfer_id == transfer.transfer_id:
                continue
            if not _within(candidate.occurred_at, transfer.occurred_at, window):
                continue
            ratio = candidate.amount / transfer.amount
            if retention_low <= ratio <= retention_high:
                successors[transfer.transfer_id].append(candidate)

    for key in successors:
        successors[key].sort(key=lambda t: (t.occurred_at, t.transfer_id))

    found: dict[frozenset[str], FundsCycle] = {}
    explored = 0
    truncated = False

    for start in sorted(transfers, key=lambda t: t.transfer_id):
        if start.transfer_id not in successors:
            continue
        origin = start.source_account
        stack: list[tuple[Transfer, tuple[str, ...], frozenset[str]]] = [
            (start, (start.transfer_id,), frozenset({origin, start.target_account}))
        ]
        while stack:
            current, path, visited = stack.pop()
            explored += 1
            if explored > max_paths:
                truncated = True
                stack.clear()
                break
            if len(path) >= max_hops:
                continue
            for nxt in successors.get(current.transfer_id, ()):
                if nxt.target_account == origin:
                    if len(path) + 1 >= min_hops:
                        cycle = _build_cycle(path + (nxt.transfer_id,), by_id, origin)
                        found.setdefault(frozenset(cycle.transfers), cycle)
                    continue
                if nxt.target_account in visited:
                    continue
                stack.append((nxt, path + (nxt.transfer_id,), visited | {nxt.target_account}))
        if truncated:
            break

    return sorted(found.values(), key=lambda c: (-c.total_amount, c.accounts)), truncated


def _build_cycle(
    transfer_ids: tuple[str, ...], by_id: dict[str, Transfer], origin: str
) -> FundsCycle:
    legs = [by_id[tid] for tid in transfer_ids]
    accounts = (origin,) + tuple(leg.target_account for leg in legs)
    times = [leg.occurred_at for leg in legs]
    first, last = legs[0].amount, legs[-1].amount
    return FundsCycle(
        accounts=accounts,
        transfers=transfer_ids,
        total_amount=round(sum(leg.amount for leg in legs), 2),
        retained_fraction=round(last / first, 4) if first else 0.0,
        span_hours=round((max(times) - min(times)).total_seconds() / 3600, 2),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Activity bursts
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BurstProfile:
    """How concentrated a subject's activity is, against its own history.

    The comparison is to the subject's own rate rather than to a population
    average, because "busy" and "suddenly busy" are different findings and only
    the second one is interesting. An account that transacts daily is not
    anomalous for transacting today.
    """

    event_count: int
    span_hours: float
    peak_count: int
    """Most events observed in any window of the configured width."""
    expected_count: float
    """Events that window would hold at the subject's own average rate."""
    ratio: float
    peak_start: datetime | None


def burst_profile(
    times: list[datetime], *, window: timedelta, floor_expected: float = 0.5
) -> BurstProfile | None:
    """None when there is not enough history to say anything.

    `floor_expected` stops the ratio exploding for subjects whose baseline rate
    rounds to nothing: without it, two events a year apart produce an infinite
    ratio and a subject with almost no history outranks one with a genuine
    spike. The floor is a stated parameter of the model rather than a fudge —
    it is part of the fingerprint, so a report cannot be re-attributed to a
    model that used a different one.
    """
    if len(times) < 2:
        return None

    ordered = sorted(times)
    span_seconds = (ordered[-1] - ordered[0]).total_seconds()
    if span_seconds <= 0:
        return None

    width = window.total_seconds()
    peak = 0
    peak_start: datetime | None = None
    left = 0
    for right in range(len(ordered)):
        while (ordered[right] - ordered[left]).total_seconds() > width:
            left += 1
        if right - left + 1 > peak:
            peak = right - left + 1
            peak_start = ordered[left]

    span_hours = span_seconds / 3600
    expected = len(ordered) * (width / span_seconds)
    return BurstProfile(
        event_count=len(ordered),
        span_hours=round(span_hours, 2),
        peak_count=peak,
        expected_count=round(expected, 3),
        ratio=round(peak / max(expected, floor_expected), 2),
        peak_start=peak_start,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Population-relative rarity
# ─────────────────────────────────────────────────────────────────────────────


def corridor_frequencies(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], float]:
    """Share of traffic on each origin→destination corridor.

    Rarity is measured against what this world actually contains rather than
    against an external list of plausible routes. A corridor is unusual here if
    few shipments use it, which is a statement ARGUS can support from its own
    data — where "this route is implausible" would be an assertion about the
    world that ARGUS has no source for.
    """
    if not pairs:
        return {}
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for pair in pairs:
        counts[pair] += 1
    total = len(pairs)
    return {pair: count / total for pair, count in counts.items()}


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile. None for an empty input, rather than 0 — a
    percentile of nothing is undefined, and returning a number would let a
    caller compare against it as though it meant something."""
    if not values:
        return None
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be in [0, 1]")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def rank_of(values: list[float], value: float) -> float | None:
    """Share of `values` at or below `value`. None when there is nothing to
    rank against."""
    if not values:
        return None
    ordered = sorted(values)
    return bisect_left(ordered, value) / len(ordered)
