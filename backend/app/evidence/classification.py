"""Classification levels, handling caveats, and the rule that bounds export.

## Why these words and not the real ones

The four levels below are deliberately **not** the markings of any national
scheme. Borrowing OFFICIAL / SECRET / TOP SECRET would imply that this system
had been accredited to hold material under one, and it has not been. A marking
that looks official and means nothing is more dangerous than a neutral one that
means exactly what it says — an analyst who sees a familiar marking will apply
the handling rules that go with it, and none of those rules are implemented
here.

Mapping these to a real scheme is a deployment decision, and it is a decision
that needs an accreditation behind it rather than a rename in this file.

## The rule

    An actor may read, and may export, up to their clearance and no further.

Comparison needs an order, so each level carries a rank. Nothing else in the
codebase compares classifications by string, and nothing averages them — a rank
is an ordinal position, not a quantity.

## Retention

Each level carries how long an *export* of material at that level is kept before
automated disposal. Longer for more sensitive material rather than shorter,
which is the opposite of the intuitive answer and the right one: a restricted
export is the one whose custody record matters most, and disposing of it early
destroys the evidence of who held it.

Note what is **not** on a retention schedule: the audit log, the provenance
records, and the investigation history. Those are the record of what was done,
and a system that expires its own accountability trail has not implemented
retention — it has implemented forgetting.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CLASSIFICATIONS",
    "CLASSIFICATION_CODES",
    "DEFAULT_CLASSIFICATION",
    "Classification",
    "classification_by_code",
    "may_access",
    "rank",
    "retention_days",
]


@dataclass(frozen=True)
class Classification:
    code: str
    label: str
    rank: int
    """Ordinal position. Higher is more restricted. Never arithmetic."""
    means: str
    handling: str
    """What someone holding this is expected to do with it."""
    export_retention_days: int


CLASSIFICATIONS: tuple[Classification, ...] = (
    Classification(
        code="unrestricted",
        label="Unrestricted",
        rank=0,
        means="Nothing here would cause harm if it were seen outside the organisation.",
        handling="No restriction. May be shared freely.",
        export_retention_days=90,
    ),
    Classification(
        code="internal",
        label="Internal",
        rank=1,
        means="Ordinary working material. Not for publication, not otherwise sensitive.",
        handling="Share within the organisation. Do not publish or forward externally.",
        export_retention_days=365,
    ),
    Classification(
        code="confidential",
        label="Confidential",
        rank=2,
        means=(
            "Disclosure would damage an investigation, a relationship with a source, or a named person's interests."
        ),
        handling=(
            "Named recipients only. Do not forward. Store on managed systems. Report any loss or unintended disclosure."
        ),
        export_retention_days=1095,
    ),
    Classification(
        code="restricted",
        label="Restricted",
        rank=3,
        means=(
            "Disclosure would cause serious harm — to a person, to an ongoing "
            "operation, or to a source who could be identified from it."
        ),
        handling=(
            "Strict need-to-know. Named recipients only, recorded. Do not forward, "
            "print or copy. Any disclosure is a reportable incident."
        ),
        export_retention_days=2555,
    ),
)

CLASSIFICATION_CODES: frozenset[str] = frozenset(c.code for c in CLASSIFICATIONS)

DEFAULT_CLASSIFICATION = "internal"
"""What an investigation is created at when nobody says otherwise.

Deliberately not `unrestricted`. A default that under-classifies is a default
that leaks, and the cost of over-classifying by one level is an inconvenience
where the cost of under-classifying is the thing this vocabulary exists to
prevent.
"""

_BY_CODE: dict[str, Classification] = {c.code: c for c in CLASSIFICATIONS}


def classification_by_code(code: str) -> Classification:
    try:
        return _BY_CODE[code]
    except KeyError:
        raise ValueError(
            f"{code!r} is not a classification. Valid: " + ", ".join(sorted(CLASSIFICATION_CODES))
        ) from None


def rank(code: str) -> int:
    return classification_by_code(code).rank


def retention_days(code: str) -> int:
    return classification_by_code(code).export_retention_days


def may_access(clearance: str, classification: str) -> bool:
    """Whether an actor at `clearance` may see material at `classification`.

    Both arguments are validated rather than compared optimistically: an
    unrecognised clearance raises instead of quietly ranking as 0 and granting
    access to everything at `unrestricted`, or as -1 and granting nothing. A
    typo in a role mapping should be a loud failure at the point of the typo,
    not a silent widening or narrowing somewhere else.
    """
    return rank(clearance) >= rank(classification)
