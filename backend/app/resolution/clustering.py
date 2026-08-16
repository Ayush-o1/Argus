"""Turning pairwise decisions into clusters, without resolving contradictions.

Identity is transitive: if A is B and B is C then A is C, and any resolution
system that does not close that transitively will show an analyst two records
it has already been told are the same. So clusters are the connected components
of the active `same` decisions.

Transitive closure is also how one bad merge spreads. A single wrong link joins
two groups that were never compared, and every record in each inherits the
other's. The defence is not to be cleverer about closure — it is to notice when
the result contradicts something ARGUS has been told and **refuse to resolve
it**:

    A cluster containing a pair explicitly judged `different` is marked
    `contested`. ARGUS does not drop the weakest link, does not re-score, and
    does not pick a side. It states the contradiction and leaves it to a person.

That is cross-phase invariant 6 ("no contradiction auto-resolved") applied to
identity, and it is the difference between a system that is confidently wrong
and one that is usefully uncertain.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Cluster:
    cluster_key: str
    entity_type: str
    members: list[str]
    canonical_ref: str
    canonical_basis: str
    contested: bool
    contested_reason: str | None


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, ref: str) -> None:
        self._parent.setdefault(ref, ref)

    def find(self, ref: str) -> str:
        self.add(ref)
        root = ref
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression, iterative — a deep chain of merges is plausible and
        # recursion would make it a stack overflow rather than a slow query.
        while self._parent[ref] != root:
            self._parent[ref], ref = root, self._parent[ref]
        return root

    def refs(self) -> list[str]:
        return sorted(self._parent)

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            # Attach the larger key under the smaller so the root is always the
            # lexicographically smallest member — which makes `cluster_key`
            # deterministic rather than dependent on insertion order.
            if left_root <= right_root:
                self._parent[right_root] = left_root
            else:
                self._parent[left_root] = right_root


def build_clusters(
    same_pairs: list[tuple[str, str, str]],
    different_pairs: set[tuple[str, str]],
    *,
    observation_counts: dict[str, int] | None = None,
    pinned: dict[str, str] | None = None,
) -> list[Cluster]:
    """Compute clusters from decisions.

    `same_pairs` is (entity_type, left, right); `different_pairs` is the set of
    pairs judged different, used only to detect contradiction — never to break
    a link.

    Only multi-member clusters are returned. A record that matched nothing is
    not a cluster of one: materialising those would make this table a second,
    stale copy of the entity population, and "is in no cluster" is already the
    answer to "is this a duplicate of anything".
    """
    counts = observation_counts or {}
    pins = pinned or {}

    union = _UnionFind()
    entity_types: dict[str, str] = {}
    for entity_type, left, right in same_pairs:
        union.union(left, right)
        entity_types[left] = entity_type
        entity_types[right] = entity_type

    groups: dict[str, list[str]] = defaultdict(list)
    for ref in union.refs():
        groups[union.find(ref)].append(ref)

    clusters: list[Cluster] = []
    for root, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        members = sorted(members)
        member_set = set(members)

        contradictions = [
            (left, right)
            for left, right in sorted(different_pairs)
            if left in member_set and right in member_set
        ]
        contested = bool(contradictions)
        reason = None
        if contested:
            shown = ", ".join(f"{left} / {right}" for left, right in contradictions[:3])
            more = "" if len(contradictions) <= 3 else f" (and {len(contradictions) - 3} more)"
            reason = (
                f"These {len(members)} records are linked into one identity by a chain of "
                f"merges, but {len(contradictions)} pair(s) within it have been judged "
                f"different: {shown}{more}. ARGUS will not choose which decision to discard."
            )

        canonical_ref, canonical_basis = _canonical(members, counts, pins)
        clusters.append(
            Cluster(
                cluster_key=root,
                entity_type=entity_types.get(members[0], "Unknown"),
                members=members,
                canonical_ref=canonical_ref,
                canonical_basis=canonical_basis,
                contested=contested,
                contested_reason=reason,
            )
        )
    return clusters


def _canonical(
    members: list[str], counts: dict[str, int], pins: dict[str, str]
) -> tuple[str, str]:
    """Pick the record that represents a cluster, and say why.

    "Canonical" is a choice, not a discovery, so the basis is stored alongside
    it and shown in the UI. A surface that presents one of several records as
    *the* entity without saying how it was chosen is asserting something ARGUS
    was never told.
    """
    pinned_members = [ref for ref in members if ref in pins]
    if pinned_members:
        chosen = pinned_members[0]
        if len(pinned_members) > 1:
            return chosen, (
                f"pinned by an analyst — {len(pinned_members)} members are pinned, "
                f"so the lowest id was taken"
            )
        return chosen, f"pinned by {pins[chosen]}"

    best = max(members, key=lambda ref: (counts.get(ref, 0), _reverse_key(ref)))
    best_count = counts.get(best, 0)
    if best_count == 0:
        return members[0], (
            "no observations are recorded against any member, so the lowest id was "
            "taken for stability"
        )
    tied = [ref for ref in members if counts.get(ref, 0) == best_count]
    if len(tied) > 1:
        return tied[0], (
            f"{best_count} observations — tied with {len(tied) - 1} other member(s), "
            "so the lowest id was taken"
        )
    return best, f"the most observations of any member ({best_count})"


def _reverse_key(ref: str) -> tuple[int, ...]:
    """Sort key making `max` prefer the *lowest* ref on a tie."""
    return tuple(-ord(ch) for ch in ref)
