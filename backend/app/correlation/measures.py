"""The arithmetic underneath the dimensions.

Pure functions over plain data: no graph, no model, no context. Everything here
can be checked against a worked example by hand, which is the only way to have
any confidence in a similarity number — the alternative is a formula nobody has
ever verified producing a value nobody can question.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat_a: float, lng_a: float, lat_b: float, lng_b: float) -> float:
    """Great-circle distance in kilometres.

    Used rather than a projected-plane approximation because the world spans
    ~30 degrees of latitude, where a flat approximation is wrong by several
    percent — small in absolute terms, but the co-location dimension turns
    distance into evidence, and evidence should not carry an error nobody
    accounted for.
    """
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = phi_b - phi_a
    d_lambda = math.radians(lng_b - lng_a)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def rarity_weight(shared_by: int, *, population: int) -> float:
    """How much it is worth that two subjects share one particular thing.

    Sharing a counterparty that four other people also use is evidence. Sharing
    one that four thousand people use is a fact about the counterparty, not
    about the pair — the clearing account of a large bank connects everybody to
    everybody, and a dimension that did not know this would rank the entire
    population as mutually correlated.

    This is inverse document frequency, and it is used for the reason IDF is
    normally used: to stop the most common term dominating every comparison.
    Normalised to [0, 1] against the population size so the value means the same
    thing across runs of different sizes.

        shared_by == population  ->  0.0   (everyone has it; it says nothing)
        shared_by == 2           ->  near 1 (only this pair has it)

    `shared_by < 2` returns 0: a thing only one subject touches cannot be shared,
    and treating it as maximally rare would be an off-by-one that rewarded
    non-evidence.
    """
    if shared_by < 2 or population < 2:
        return 0.0
    if shared_by >= population:
        return 0.0
    return math.log(population / shared_by) / math.log(population / 1)


def ramp(value: float, trigger: float, full: float) -> float:
    """Linear interpolation between "not evidence yet" and "as much as this counts".

    Identical in spirit to the assessment signals' ramp, and deliberately not a
    step function: a pair one kilometre outside a radius is not categorically
    different from one a kilometre inside it, and a threshold that says
    otherwise produces findings that flip on noise. Supports an inverted ramp
    (`full < trigger`) for measures where smaller is stronger, such as distance.
    """
    if full == trigger:
        return 1.0 if value >= trigger else 0.0
    if full > trigger:
        if value <= trigger:
            return 0.0
        return min(1.0, (value - trigger) / (full - trigger))
    if value >= trigger:
        return 0.0
    return min(1.0, (trigger - value) / (trigger - full))


def noisy_or(scores: Iterable[float]) -> float:
    """Combine independent evidence for the same conclusion.

    Each score is read as "the probability this piece of evidence alone would
    establish the link". The combination is one minus the probability that all
    of them failed to. It has the two properties that matter here:

      * **Monotone.** More evidence never lowers the strength, so a strong
        finding cannot be diluted by a weak one sitting beside it — the defect
        that made the first assessment scoring scheme unusable in Phase 5.
      * **Bounded.** No accumulation of partial evidence reaches 1: three
        dimensions at 0.9 combine to 0.999, not to certainty. It reaches 1 only
        when a single input is itself exactly 1, which happens when a dimension
        found something categorical — three or more direct communications
        between the pair, say. That is a fact rather than an inference, so a
        strength of 1 there is a statement about an observation, not a
        confidence level that was manufactured by adding things up.

    Independence is a real assumption and it is only defensible *between*
    families of evidence, which is why `linking.py` takes the maximum within a
    family before combining across families. Two financial measures over the
    same transactions are not independent, and multiplying them as though they
    were would manufacture confidence out of one fact counted twice.
    """
    residual = 1.0
    for score in scores:
        residual *= 1.0 - max(0.0, min(1.0, score))
    return 1.0 - residual


def overlap_weight(
    shared: Iterable[str],
    frequency: Mapping[str, int],
    *,
    population: int,
) -> float:
    """Total rarity-weighted evidence from a set of shared things.

    Summed rather than averaged, because two rare shared counterparties are
    stronger evidence than one — an average would say they were equally strong,
    and would let a single rare item be diluted by a common one.
    """
    return sum(rarity_weight(frequency.get(key, 0), population=population) for key in shared)


def excess_over_chance(observed: float, expected: float) -> float | None:
    """How many times more overlap there is than chance alone would produce.

    This exists because of a measurement, not a theory. The first version of the
    shared-counterparty dimension scored raw rarity-weighted overlap, and against
    the live graph it fired on 545 of 688 randomly chosen pairs with a median
    magnitude of 0.63. A dimension that fires on four out of five unrelated pairs
    is not evidence of anything; it is a description of how densely the world
    transacts.

    The reason is arithmetic. With 877 subjects touching a median of 40
    counterparties each, drawn from 2,811 distinct accounts, two subjects
    picked at random already share about 2.8 of them. The *expected* overlap was
    close to what the model was calling a full-strength finding.

    Measuring the excess fixes that by asking the question that was always meant:
    not "do they share counterparties" — everyone does — but "do they share more
    than they should". Chance is estimated as |A|·|B|/N, the standard
    independent-draw expectation, and the ratio is a lift.

    Returns None when chance predicts nothing at all, because a ratio against an
    expectation of zero is not a large number, it is an undefined one — and a
    dimension handed infinity would report certainty on the thinnest possible
    evidence.
    """
    if expected <= 0:
        return None
    return observed / expected


@dataclass(frozen=True)
class ReachedAccount:
    """An account reachable from a starting account by following transfers."""

    account: str
    hops: int
    retention: float
    """The share of the money that survived the whole route — the product of
    each hop's retention. A path that arrives with 1% of what set out is a path,
    but it is not the same money, and calling it one would turn every account in
    a busy graph into a correlate of every other."""

    first_seen: datetime
    last_seen: datetime
    """The span of the route. Kept because a chain whose hops are eighteen
    months apart is not a chain; the caller bounds it with a window."""

    origin: str = ""
    first_amount: float = 0.0
    """Which account the route left from, and how much left with it.

    Carried so the caller can ask what share of that account's whole year of
    outgoing payments this route represents. A transfer that is a third of
    everything an account sent is a relationship; one that is 3% of it is a
    transaction, and against the live graph the median payment between two
    flagged subjects is exactly that — 3.3%.
    """

    @property
    def span(self) -> timedelta:
        return self.last_seen - self.first_seen


def forward_reach(
    start_accounts: Sequence[str],
    adjacency: Mapping[str, Sequence[tuple[str, float, datetime]]],
    *,
    max_hops: int,
    min_hop_retention: float,
    min_total_retention: float,
    window: timedelta,
    max_frontier: int,
) -> tuple[dict[str, ReachedAccount], bool]:
    """Breadth-first search along transfers, keeping the best route to each account.

    A hop is only followed when the amount leaving is a plausible onward
    movement of the amount that arrived — between `min_hop_retention` and the
    full amount. That is the same value-preservation test the assessment phase
    uses for funds cycles, and it is what separates a laundering chain from the
    fact that busy accounts are all connected to each other if you walk far
    enough.

    Deliberately **not** time-ordered, for the reason Phase 5 discovered the
    hard way: the planted chains advance each hop by `hop * uniform(1, 6)`
    hours, which is not monotonic, and a detector requiring increasing
    timestamps found none of them. The whole route is required to fit inside
    `window` instead, which is the real constraint — money moving over eighteen
    months is not one movement.

    Returns the reachable set and a flag saying whether any frontier was
    truncated. The flag is returned rather than swallowed because a pair that
    was never compared must not be reported as a pair with nothing between them.
    """
    reached: dict[str, ReachedAccount] = {}
    truncated = False

    # account -> (amount still moving, retention, first seen, last seen,
    #             origin account, amount that left the origin)
    Entry = tuple[float, float, datetime, datetime, str, float]
    frontier: dict[str, Entry] = {}
    seen = set(start_accounts)

    for origin in start_accounts:
        for target, amount, occurred_at in adjacency.get(origin, ()):
            if target in seen or amount <= 0:
                continue
            best = frontier.get(target)
            if best is None or amount > best[0]:
                frontier[target] = (amount, 1.0, occurred_at, occurred_at, origin, amount)

    for hop in range(1, max_hops + 1):
        if not frontier:
            break

        for target, entry in frontier.items():
            _amount, retention, first_seen, last_seen, origin, first_amount = entry
            seen.add(target)
            reached[target] = ReachedAccount(
                account=target,
                hops=hop,
                retention=retention,
                first_seen=first_seen,
                last_seen=last_seen,
                origin=origin,
                first_amount=first_amount,
            )

        if hop == max_hops:
            break

        next_frontier: dict[str, Entry] = {}
        for account, entry in frontier.items():
            amount, retention, first_seen, last_seen, origin, first_amount = entry
            for target, onward, occurred_at in adjacency.get(account, ()):
                if target in seen or onward <= 0:
                    continue
                hop_retention = onward / amount
                if hop_retention < min_hop_retention or hop_retention > 1.0:
                    continue
                carried = retention * hop_retention
                if carried < min_total_retention:
                    continue
                first = min(first_seen, occurred_at)
                last = max(last_seen, occurred_at)
                if last - first > window:
                    continue
                best = next_frontier.get(target)
                if best is None or carried > best[1]:
                    next_frontier[target] = (
                        onward, carried, first, last, origin, first_amount
                    )

        if len(next_frontier) > max_frontier:
            truncated = True
            kept = sorted(next_frontier.items(), key=lambda item: item[1][1], reverse=True)[:max_frontier]
            next_frontier = dict(kept)
        frontier = next_frontier

    return reached, truncated


def window_overlap(
    times_a: Sequence[datetime],
    times_b: Sequence[datetime],
    *,
    window: timedelta,
) -> tuple[int, datetime | None]:
    """How often the two subjects were active within `window` of each other.

    Returns the count of coincidences and the earliest one, which is what an
    analyst wants to see first. Both sequences are sorted and swept together
    rather than compared pairwise, so this stays linear on subjects with long
    histories instead of quadratic.

    A coincidence is counted once per event in `times_a`, not once per pair:
    one transfer by A sitting inside a flurry of fifty by B is one coincidence,
    not fifty. Counting pairs would let a single busy subject manufacture
    arbitrarily strong temporal evidence against everyone.
    """
    if not times_a or not times_b:
        return 0, None

    sorted_a = sorted(times_a)
    sorted_b = sorted(times_b)
    count = 0
    earliest: datetime | None = None
    index = 0

    for moment in sorted_a:
        while index < len(sorted_b) and sorted_b[index] < moment - window:
            index += 1
        if index < len(sorted_b) and sorted_b[index] <= moment + window:
            count += 1
            candidate = min(moment, sorted_b[index])
            if earliest is None or candidate < earliest:
                earliest = candidate

    return count, earliest


def centroid(points: Sequence[tuple[float, float]]) -> tuple[float, float] | None:
    """The mean position of a set of (lat, lng) points, or None if there are none.

    Computed in three dimensions and projected back, rather than by averaging
    degrees. Averaging longitude degrees is wrong across the antimeridian, and
    while this world does not span it, a centroid helper that is quietly wrong
    in one hemisphere is the kind of thing that survives until it matters.
    """
    if not points:
        return None

    x = y = z = 0.0
    for lat, lng in points:
        phi, lam = math.radians(lat), math.radians(lng)
        x += math.cos(phi) * math.cos(lam)
        y += math.cos(phi) * math.sin(lam)
        z += math.sin(phi)

    count = len(points)
    x, y, z = x / count, y / count, z / count
    if abs(x) < 1e-12 and abs(y) < 1e-12 and abs(z) < 1e-12:
        return None

    lng = math.degrees(math.atan2(y, x))
    lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
    return lat, lng
