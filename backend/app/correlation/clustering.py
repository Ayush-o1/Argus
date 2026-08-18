"""Groups of linked findings — and how fragile each group is.

## Why these are not called campaigns or threat actors

The audit asked for `ThreatActor` and `Campaign` entities (gap G-31). This
package deliberately produces neither, and the reason is the same one that runs
through the rest of the system.

A `ThreatActor` asserts agency: that there is a *someone* behind the pattern,
with intent and continuity. A `Campaign` asserts a plan. ARGUS has evidence for
neither. What it has is a set of subjects it independently found something in,
joined by structure it can name and measure. Calling that a threat actor would
be inventing the most consequential part of the claim — the part an analyst
would actually act on — out of nothing, and dressing it in an entity type so it
looked like a finding rather than a guess.

So the object is a `CorrelatedCluster`: a group, its members, the links holding
it together, and what those links are made of. It fills the same structural role
G-31 wanted — a durable, addressable thing that alerting and case management can
attach to — while claiming only what was measured. An analyst who concludes that
a cluster *is* a campaign can record that judgement in Phase 9, attributed to
them, which is where a claim about intent belongs.

## Fragility is part of the finding

Connected components collapse. One incorrect link between two real groups
merges them into a single object that looks twice as significant as either, and
nothing in the component itself reveals that it is held together by a single
edge. So every cluster is published with its **bridges** — the links whose
removal would split it — and its weakest one. A cluster hanging on one
`possible` link is presented as exactly that, rather than as a discovery of
eleven connected subjects.

Components above `max_cluster_size` are reported as over-merged rather than as
findings. A 900-member cluster is not an insight; it is a threshold set too low,
and saying so is more useful than rendering it.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from app.correlation.linking import CorrelationLink
from app.correlation.model import CorrelationModel


@dataclass(frozen=True)
class ClusterMember:
    ref: str
    subject_type: str
    band: str
    score: float | None
    degree: int
    """How many links inside the cluster touch this member. A member joined by
    one weak link is at the edge of the group, not at its centre, and the
    difference matters to whoever reads it."""


@dataclass(frozen=True)
class CorrelatedCluster:
    cluster_key: str
    members: tuple[ClusterMember, ...]
    links: tuple[CorrelationLink, ...]
    families: tuple[str, ...]
    """Every family contributing at least one corroborating link, so a cluster
    resting entirely on one kind of evidence is visibly doing so."""
    mean_strength: float
    min_strength: float
    bridges: tuple[tuple[str, str], ...]
    """Links whose removal would split the cluster in two."""
    weakest_bridge: float | None
    """The strength of the weakest such link — the cluster's true load-bearing
    strength. None when the cluster has no bridge at all, which means every
    member is held by at least two independent routes."""
    over_merged: bool
    computed_at: datetime

    @property
    def size(self) -> int:
        return len(self.members)

    def basis(self) -> str:
        families = ", ".join(self.families) if self.families else "no corroborating family"
        if self.over_merged:
            return (
                f"{self.size} subjects joined into one component, which is above the size at "
                f"which a component stops being a finding. Reported so the threshold can be "
                f"reconsidered, not as a discovery."
            )
        if self.weakest_bridge is not None:
            return (
                f"{self.size} subjects, linked on {families}. The group depends on "
                f"{len(self.bridges)} load-bearing "
                f"{'link' if len(self.bridges) == 1 else 'links'}, the weakest at "
                f"{self.weakest_bridge:.2f} — if that one is wrong, the group splits."
            )
        return (
            f"{self.size} subjects, linked on {families}. Every member is held by at least "
            f"two independent routes, so no single link holds the group together."
        )


def _louvain(
    adjacency: dict[str, dict[str, float]], *, passes: int = 10
) -> list[set[str]]:
    """Weighted modularity communities — the Louvain method, locally implemented.

    Connected components were the obvious choice here and they are the wrong
    one. Measured against the live graph, 454 anchors joined by 1,219 links
    collapsed into a single 351-member component, and raising the link threshold
    did not fix it: at a strength of 0.90 — links so strong they are nearly all
    direct transfers — there was still a 111-member blob. That is not a
    thresholding mistake, it is the giant-component phenomenon. Any graph with
    average degree above about 1 has one, and chaining A–B–C–D into one group
    says nothing about whether A and D belong together.

    Modularity asks a different and better question: are these subjects more
    densely connected to each other than to the rest of the graph? That is what
    a group of associates actually looks like, and it does not chain.

    Implemented here rather than called from GDS because it runs on ARGUS's own
    link graph — a few thousand edges that exist only in this process — and
    round-tripping them into a database projection to get them back would be
    more machinery for less control. It is deterministic: nodes are visited in
    sorted order and ties are broken by community key, so the same links always
    produce the same communities.
    """
    if not adjacency:
        return []

    total_weight = sum(w for nbrs in adjacency.values() for w in nbrs.values()) / 2
    if total_weight <= 0:
        return [{node} for node in adjacency]

    # Each node starts alone; `node_to_community` is refined in place.
    community_of: dict[str, str] = {node: node for node in adjacency}
    degree: dict[str, float] = {
        node: sum(nbrs.values()) for node, nbrs in adjacency.items()
    }
    community_degree: dict[str, float] = dict(degree)

    for _ in range(passes):
        moved = False
        for node in sorted(adjacency):
            current = community_of[node]
            k_i = degree[node]
            community_degree[current] -= k_i

            # Weight from this node into each neighbouring community.
            into: dict[str, float] = defaultdict(float)
            for neighbour, weight in adjacency[node].items():
                if neighbour != node:
                    into[community_of[neighbour]] += weight
            into.setdefault(current, 0.0)

            best_community, best_gain = current, None
            for candidate in sorted(into):
                gain = into[candidate] - community_degree.get(candidate, 0.0) * k_i / (
                    2 * total_weight
                )
                if best_gain is None or gain > best_gain:
                    best_community, best_gain = candidate, gain

            community_degree[best_community] = (
                community_degree.get(best_community, 0.0) + k_i
            )
            if best_community != current:
                community_of[node] = best_community
                moved = True

        if not moved:
            break

    grouped: dict[str, set[str]] = defaultdict(set)
    for node, community in community_of.items():
        grouped[community].add(node)
    return sorted(grouped.values(), key=lambda members: (-len(members), sorted(members)[0]))


def _components(adjacency: dict[str, set[str]]) -> list[set[str]]:
    """Connected components, iteratively.

    Iterative rather than recursive because a long chain of linked subjects
    would otherwise be limited by Python's stack depth — a cluster of a
    thousand would raise `RecursionError` in the middle of a run rather than
    returning a large cluster that the over-merge check would catch and report.
    """
    seen: set[str] = set()
    found: list[set[str]] = []
    for start in sorted(adjacency):
        if start in seen:
            continue
        component: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            stack.extend(adjacency[node] - component)
        seen |= component
        found.append(component)
    return found


def _bridges(nodes: set[str], adjacency: dict[str, set[str]]) -> set[tuple[str, str]]:
    """Edges whose removal disconnects the component — Tarjan's algorithm.

    Iterative, for the reason above. `discovery` is the order a node was first
    reached; `low` is the earliest-discovered node reachable from its subtree
    without using the edge it was reached by. An edge is a bridge exactly when
    the child's `low` exceeds the parent's `discovery`: nothing below it has a
    way back up.
    """
    discovery: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    found: set[tuple[str, str]] = set()
    timer = 0

    for root in sorted(nodes):
        if root in discovery:
            continue
        parent[root] = None
        stack: list[tuple[str, list[str]]] = [(root, sorted(adjacency[root]))]
        discovery[root] = low[root] = timer
        timer += 1

        while stack:
            node, pending = stack[-1]
            if pending:
                neighbour = pending.pop()
                if neighbour == parent.get(node):
                    continue
                if neighbour in discovery:
                    low[node] = min(low[node], discovery[neighbour])
                else:
                    parent[neighbour] = node
                    discovery[neighbour] = low[neighbour] = timer
                    timer += 1
                    stack.append((neighbour, sorted(adjacency[neighbour])))
            else:
                stack.pop()
                if stack:
                    above = stack[-1][0]
                    low[above] = min(low[above], low[node])
                    if low[node] > discovery[above]:
                        edge = (above, node) if above <= node else (node, above)
                        found.add(edge)

    return found


def build_clusters(
    links: list[CorrelationLink],
    model: CorrelationModel,
    anchors: dict[str, tuple[str, str, float | None]],
) -> list[CorrelatedCluster]:
    """Group links into clusters.

    `anchors` maps ref -> (subject_type, band, score), so the cluster can
    describe its members without reaching back into the graph.

    Only links at or above `cluster_min_strength` participate. A cluster built
    from every link would be one component containing everything, which is the
    predictable end state of connected components on a dense graph and tells an
    analyst nothing.
    """
    eligible = [link for link in links if link.strength >= model.cluster_min_strength]
    if not eligible:
        return []

    adjacency: dict[str, set[str]] = defaultdict(set)
    weighted: dict[str, dict[str, float]] = defaultdict(dict)
    by_edge: dict[tuple[str, str], CorrelationLink] = {}
    for link in eligible:
        adjacency[link.ref_a].add(link.ref_b)
        adjacency[link.ref_b].add(link.ref_a)
        weighted[link.ref_a][link.ref_b] = link.strength
        weighted[link.ref_b][link.ref_a] = link.strength
        by_edge[link.key] = link

    clusters: list[CorrelatedCluster] = []
    now = datetime.now(UTC)

    for component in _louvain(dict(weighted)):
        if len(component) < model.cluster_min_size:
            continue

        inside = [
            link
            for link in eligible
            if link.ref_a in component and link.ref_b in component
        ]
        strengths = [link.strength for link in inside]
        degree: dict[str, int] = defaultdict(int)
        for link in inside:
            degree[link.ref_a] += 1
            degree[link.ref_b] += 1

        families: set[str] = set()
        for link in inside:
            families |= set(link.corroborating_families)

        # Restricted to the community: an edge leaving it is not a bridge
        # *within* it, and counting one would describe the group's internal
        # fragility using links that are not holding it together.
        inside_adjacency = {
            ref: adjacency[ref] & component for ref in component if ref in adjacency
        }
        bridge_edges = _bridges(component, inside_adjacency)
        bridge_strengths = [
            by_edge[edge].strength for edge in bridge_edges if edge in by_edge
        ]

        members = tuple(
            ClusterMember(
                ref=ref,
                subject_type=anchors.get(ref, ("Unknown", "unknown", None))[0],
                band=anchors.get(ref, ("Unknown", "unknown", None))[1],
                score=anchors.get(ref, ("Unknown", "unknown", None))[2],
                degree=degree[ref],
            )
            for ref in sorted(component)
        )

        clusters.append(
            CorrelatedCluster(
                # Derived from the membership rather than minted, so the same
                # group of subjects keeps the same key between runs and can be
                # followed over time. A random id would make every run look like
                # a set of brand-new discoveries.
                cluster_key=_cluster_key(component),
                members=members,
                links=tuple(sorted(inside, key=lambda link: link.strength, reverse=True)),
                families=tuple(sorted(families)),
                mean_strength=round(sum(strengths) / len(strengths), 4),
                min_strength=round(min(strengths), 4),
                bridges=tuple(sorted(bridge_edges)),
                weakest_bridge=round(min(bridge_strengths), 4) if bridge_strengths else None,
                over_merged=len(component) > model.max_cluster_size,
                computed_at=now,
            )
        )

    clusters.sort(key=lambda c: (c.over_merged, -c.size, -c.mean_strength))
    return clusters


def _cluster_key(members: set[str]) -> str:
    """A stable identifier for a set of subjects.

    A hash of the sorted membership: two runs that find the same group produce
    the same key, and a run that finds one more member produces a different one.
    That is the intended behaviour — a cluster that gained a member is not the
    same cluster, and pretending otherwise would silently rewrite the history of
    what ARGUS claimed.
    """
    joined = "|".join(sorted(members))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:16]
