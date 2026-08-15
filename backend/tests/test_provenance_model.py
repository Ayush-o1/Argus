"""The confidence model's guarantees, as pure assertions.

The most important test in this file asserts the *absence* of something. The
single change that would undo Phase 2 is somebody adding a `.score` or
`combined_confidence()` helper "for convenience" — at which point every surface
would start rendering one number, and the analyst would lose the ability to tell
one excellent source from four poor ones. Pinning the absence means that change
fails a named test instead of passing review.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import provenance as provenance_models
from app.models.provenance import (
    Assertion,
    Conflict,
    Credibility,
    EpistemicKind,
    Rating,
    Reliability,
)
from app.repositories.provenance_repo import canonical_hash


def test_rating_renders_both_axes_as_an_admiralty_code() -> None:
    rating = Rating(reliability=Reliability.B, credibility=Credibility.PROBABLY_TRUE)
    assert rating.code == "B2"
    assert rating.reliability_meaning == "Usually reliable"
    assert rating.credibility_meaning == "Probably true"


def test_unjudged_is_a_rating_not_missing_data() -> None:
    """F6 means "no basis for evaluation" on both axes. It must be expressible,
    and it must be distinguishable from a rating that was simply never set —
    which is why both fields are required rather than optional."""
    rating = Rating(reliability=Reliability.F, credibility=Credibility.CANNOT_BE_JUDGED)
    assert rating.is_unjudged()
    assert rating.code == "F6"

    assert not Rating(
        reliability=Reliability.A, credibility=Credibility.CONFIRMED
    ).is_unjudged()


def test_a_rating_cannot_be_created_without_both_axes() -> None:
    with pytest.raises(ValidationError):
        Rating(reliability=Reliability.A)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Rating(credibility=Credibility.CONFIRMED)  # type: ignore[call-arg]


def test_nothing_collapses_the_two_axes_into_one_number() -> None:
    """Guards the design decision, not an implementation detail.

    Reliability is a property of the source and credibility of the claim. They
    are ordinal scales on which arithmetic is meaningless: nothing establishes
    that A→B is the same distance as E→F. Averaging them produces a number that
    looks precise and answers no question an analyst has.
    """
    forbidden = {"score", "numeric", "combined", "confidence_score", "as_float", "value"}

    rating_attrs = {name for name in dir(Rating) if not name.startswith("_")}
    assert not (rating_attrs & forbidden), (
        f"Rating gained a scalar accessor: {sorted(rating_attrs & forbidden)}. "
        "Reliability and credibility must stay separate all the way to the UI."
    )

    module_functions = {
        name
        for name in dir(provenance_models)
        if callable(getattr(provenance_models, name)) and not name.startswith("_")
    }
    assert not (module_functions & forbidden), (
        f"app.models.provenance gained {sorted(module_functions & forbidden)}"
    )


def test_ratings_have_no_ordering() -> None:
    """Sorting by rating is how a "best source wins" tie-break gets built by
    accident. Rating deliberately implements no comparison."""
    a = Rating(reliability=Reliability.A, credibility=Credibility.CONFIRMED)
    b = Rating(reliability=Reliability.F, credibility=Credibility.CANNOT_BE_JUDGED)
    with pytest.raises(TypeError):
        _ = a < b  # type: ignore[operator]


def test_every_admiralty_value_has_a_stated_meaning() -> None:
    """A letter with no gloss is unreadable to anyone who has not memorised the
    code, and the UI renders these directly."""
    for reliability in Reliability:
        assert provenance_models.RELIABILITY_MEANING[reliability.value]
    for credibility in Credibility:
        assert provenance_models.CREDIBILITY_MEANING[credibility.value]


def test_the_four_epistemic_kinds_are_distinct_and_complete() -> None:
    assert {k.value for k in EpistemicKind} == {"observed", "reported", "inferred", "assessed"}


def test_canonical_hash_is_order_independent() -> None:
    """Idempotent ingestion depends on this: the same content must hash the same
    regardless of key order, or replaying a feed would create duplicate
    observations and inflate every corroboration count built on them."""
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})


def test_canonical_hash_distinguishes_nesting() -> None:
    assert canonical_hash({"a": {"b": 1}}) != canonical_hash({"a": {"b": "1"}})
    assert canonical_hash({"a": [1, 2]}) != canonical_hash({"a": [2, 1]})


def _assertion(value: str) -> Assertion:
    from datetime import UTC, datetime

    return Assertion(
        assertion_id=f"id-{value}",
        subject_ref="PRS-0000001",
        subject_type="Person",
        predicate="country",
        object_value=value,
        epistemic_kind=EpistemicKind.REPORTED,
        rating=Rating(reliability=Reliability.B, credibility=Credibility.PROBABLY_TRUE),
        method="source-report",
        asserted_by="user:test",
        asserted_by_display="Test Analyst",
        asserted_at=datetime.now(UTC),
    )


def test_a_conflict_has_no_winner() -> None:
    """The phase's most important behaviour, pinned as a shape.

    A `winner`, `preferred` or `resolved_value` field would let a surface render
    one side and drop the other, which hides the disagreement from the only
    person who can settle it. The model has no such field, and this test fails
    if one is added.
    """
    conflict = Conflict(
        subject_ref="PRS-0000001",
        predicate="country",
        assertions=[_assertion("Canada"), _assertion("Mexico")],
    )
    fields = set(Conflict.model_fields)
    assert fields == {"subject_ref", "predicate", "assertions"}
    assert not fields & {"winner", "preferred", "resolved", "resolved_value", "best"}
    assert len(conflict.assertions) == 2


def test_an_assertion_knows_whether_it_is_still_believed() -> None:
    from datetime import UTC, datetime

    live = _assertion("Canada")
    assert live.is_current

    retracted = _assertion("Canada").model_copy(
        update={
            "retracted_at": datetime.now(UTC),
            "retracted_by": "user:x",
            "retraction_reason": "source withdrawn",
        }
    )
    assert not retracted.is_current
