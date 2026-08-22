"""What makes two firings the same alert, and what makes several one group.

## Dedup

An alert's identity is `(rule_id, rule_version, scope)`. Re-running the rules
over an unchanged world must not produce a second row — it increments an
occurrence count and moves `last_seen_at`. This is the difference between a
queue that grows with time and one that grows with events.

`rule_version` is part of the key on purpose. A re-versioned rule is a
different question, and folding its firings into the old alert's occurrence
count would silently mix two measurements — the one thing calibration cannot
recover from later.

Scope is sorted before hashing, so a pair discovered as (A, B) and later as
(B, A) is one alert.

## Grouping

Alerts are grouped by **the correlated cluster their subjects belong to**,
falling back to the scope itself when no cluster contains them.

The alternative — transitive closure over shared subjects — was tried and
rejected for the reason Phase 6 rejected connected components for clustering:
chaining. Alert A about {x,y} and alert B about {y,z} and alert C about {z,w}
merge into one group with nothing in common at the ends, and on a dense
population that collapses the queue into a single item. The correlation phase
already solved this problem properly, with modularity and load-bearing bridges,
and its answer is the one to reuse rather than re-derive worse.

A group is therefore a claim ARGUS already made and can defend, not a new one
invented at display time.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from app.alerting.evidence import AlertingEvidence
from app.alerting.rules import RuleFiring

__all__ = [
    "AlertGroup",
    "alert_key",
    "group_firings",
    "group_key",
]


def alert_key(rule_id: str, rule_version: int, scope: tuple[str, ...]) -> str:
    """Stable identity for one alert. Same inputs, same key, forever."""
    payload = f"{rule_id}@{rule_version}::{'|'.join(sorted(scope))}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def group_key(basis: str, members: tuple[str, ...]) -> str:
    payload = f"{basis}::{'|'.join(sorted(members))}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


@dataclass
class AlertGroup:
    """Several alerts about one story.

    `basis` records *why* these are together, because "grouped" with no reason
    is the kind of thing an analyst has to take on faith.
    """

    key: str
    basis: str
    subjects: tuple[str, ...]
    alert_keys: list[str] = field(default_factory=list)
    rule_ids: set[str] = field(default_factory=set)

    @property
    def size(self) -> int:
        return len(self.alert_keys)

    def describe(self) -> str:
        rules = ", ".join(sorted(self.rule_ids))
        alerts = f"{self.size} alert{'' if self.size == 1 else 's'}"
        if self.basis.startswith("cluster:"):
            return (
                f"{alerts} about {len(self.subjects)} subjects ARGUS correlated "
                f"into one group ({rules})."
            )
        # A single alert that ARGUS could not correlate to anything is not a
        # group, and calling it one would overstate what was found. It is
        # carried here so the view accounts for every alert, and says plainly
        # that this one stands alone.
        if self.size == 1:
            return f"One alert ARGUS could not connect to any other finding ({rules})."
        return f"{alerts} about the same subjects ({rules})."


def group_firings(
    firings: list[RuleFiring], evidence: AlertingEvidence
) -> tuple[dict[str, AlertGroup], dict[str, str]]:
    """Assign every firing to a group.

    Returns the groups and a mapping from `alert_key` to `group_key`.
    """
    groups: dict[str, AlertGroup] = {}
    assignment: dict[str, str] = {}

    # A subject belongs to at most one cluster, so a lookup is enough and no
    # merge logic is needed — the merging was already done, properly, by the
    # correlation phase.
    cluster_of: dict[str, str] = {}
    cluster_members: dict[str, tuple[str, ...]] = {}
    for cluster in evidence.clusters:
        cluster_members[cluster.cluster_key] = cluster.members
        for member in cluster.members:
            cluster_of[member] = cluster.cluster_key

    by_key: dict[str, list[RuleFiring]] = defaultdict(list)
    for firing in firings:
        by_key[alert_key(firing.rule_id, firing.rule_version, firing.scope)].append(firing)

    for key, group_firing_list in sorted(by_key.items()):
        firing = group_firing_list[0]

        # A firing joins the cluster group if any of its subjects is in a
        # cluster. Where its subjects span two clusters — possible only for a
        # rule scoped across them — the lexicographically first is chosen, so
        # the assignment is deterministic rather than traversal-dependent.
        cluster_keys = sorted({cluster_of[s] for s in firing.scope if s in cluster_of})
        if cluster_keys:
            chosen = cluster_keys[0]
            basis = f"cluster:{chosen}"
            members = cluster_members[chosen]
        else:
            basis = "scope"
            members = tuple(sorted(firing.scope))

        gkey = group_key(basis, members)
        if gkey not in groups:
            groups[gkey] = AlertGroup(key=gkey, basis=basis, subjects=members)
        groups[gkey].alert_keys.append(key)
        groups[gkey].rule_ids.add(firing.rule_id)
        assignment[key] = gkey

    return groups, assignment
