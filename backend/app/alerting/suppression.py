"""Suppression that hides an alert from the default queue and nothing more.

The audit's requirement was "retained and inspectable, never silent", and the
word doing the work is *never*. The failure mode being designed against is the
one every mature alerting system eventually has: a suppression added during an
incident three years ago, by someone who has left, silently eating the alerts
that would have caught the next one. Nobody can find it, because there is
nothing to find — the alerts simply never appeared.

So suppression here does not prevent an alert existing. Rules run, the alert is
written, dedup counts its occurrences, and it appears in the group it belongs
to. The suppression sets a flag, records who set it and why, and the alert is
excluded from the *default* filter — one query parameter away, with a count of
what is being hidden shown next to the queue.

Three further properties follow from the same reasoning:

  - **Expiry is mandatory.** An indefinite suppression is the permanent
    blindness above. A maximum is enforced; renewing is a deliberate act with a
    new record.
  - **A suppression is scoped, and the scope is explicit** — a rule, a subject,
    or a rule on a subject. There is no wildcard that silences everything.
  - **Matching is recorded.** `suppressed_by` on the alert names the
    suppression that hid it, so "why did I not see this" is answerable from the
    alert rather than by reading the suppression table and guessing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

__all__ = [
    "MAX_SUPPRESSION",
    "Suppression",
    "SuppressionScopeError",
    "matching_suppression",
    "validate_suppression",
]

# The longest a suppression may run before somebody has to look at it again.
# 90 days is long enough to cover a known remediation window and short enough
# that it cannot outlive the person who set it.
MAX_SUPPRESSION = timedelta(days=90)


class SuppressionScopeError(ValueError):
    """Raised for a suppression that would silence more than it should."""


@dataclass(frozen=True)
class Suppression:
    suppression_id: str
    rule_id: str | None
    subject_ref: str | None
    reason_code: str
    note: str
    created_by: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def is_active(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        if self.revoked_at is not None:
            return False
        return self.expires_at > now

    def matches(self, rule_id: str, scope: tuple[str, ...]) -> bool:
        """Whether this suppression covers a firing.

        A rule-only suppression covers every firing of that rule. A
        subject-only suppression covers any firing that names the subject. Both
        together require both, which is the narrowest and the one the UI offers
        by default.
        """
        if self.rule_id is not None and self.rule_id != rule_id:
            return False
        if self.subject_ref is not None and self.subject_ref not in scope:
            return False
        return True

    def describe(self) -> str:
        target = []
        if self.rule_id:
            target.append(f"rule {self.rule_id}")
        if self.subject_ref:
            target.append(f"subject {self.subject_ref}")
        return (
            f"{' and '.join(target)} suppressed by {self.created_by} until "
            f"{self.expires_at.date().isoformat()} ({self.reason_code})"
        )


def validate_suppression(
    *,
    rule_id: str | None,
    subject_ref: str | None,
    expires_at: datetime,
    note: str,
    now: datetime | None = None,
) -> None:
    """Reject suppressions that are too broad, too long, or unexplained."""
    now = now or datetime.now(UTC)

    if rule_id is None and subject_ref is None:
        raise SuppressionScopeError(
            "A suppression must name a rule, a subject, or both. There is no "
            "wildcard: a suppression that matches everything is an off switch "
            "for detection, and turning detection off should not look like "
            "triage."
        )
    if expires_at <= now:
        raise SuppressionScopeError("A suppression must expire in the future.")
    if expires_at - now > MAX_SUPPRESSION:
        raise SuppressionScopeError(
            f"A suppression may run for at most {MAX_SUPPRESSION.days} days. "
            "Renew it deliberately rather than setting one that outlives the "
            "reason for it."
        )
    if len(note.strip()) < 10:
        raise SuppressionScopeError(
            "A suppression needs a note explaining it — at least a sentence. "
            "The person who has to judge this in six months will not have the "
            "context you have now."
        )


def matching_suppression(
    suppressions: list[Suppression],
    rule_id: str,
    scope: tuple[str, ...],
    now: datetime | None = None,
) -> Suppression | None:
    """The narrowest active suppression covering this firing, if any.

    Narrowest wins so that a targeted suppression is what gets recorded against
    the alert, rather than a broad one that happens to sort first.
    """
    now = now or datetime.now(UTC)
    candidates = [s for s in suppressions if s.is_active(now) and s.matches(rule_id, scope)]
    if not candidates:
        return None

    def specificity(s: Suppression) -> tuple[int, str]:
        score = (1 if s.rule_id else 0) + (1 if s.subject_ref else 0)
        return (-score, s.suppression_id)

    return sorted(candidates, key=specificity)[0]
