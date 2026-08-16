"""The evaluation harness — and the ways a matcher can be measured flatteringly.

Two of these tests exist because the first version of the harness produced
precision 1.00 and recall 1.00, and both numbers were close to meaningless:

  * the negatives were random pairs of people, which no blocker would ever put
    in front of the matcher, so precision measured performance on a question it
    is never asked;
  * recall was measured on the scorer alone, so pairs that blocking never
    surfaces counted as successes.
"""

from __future__ import annotations

import random

import pytest

from app.resolution import evaluation
from app.resolution.blocking import blocking_keys
from app.resolution.profile import EntityProfile

RNG = random.Random(7)


def person(ref: str, **attributes: object) -> EntityProfile:
    return EntityProfile(ref=ref, entity_type="Person", attributes=dict(attributes))


def population(count: int = 60) -> list[EntityProfile]:
    surnames = ["Ellis", "Tanner", "Okafor", "Nakamura", "Sharma", "Alvarez"]
    firsts = ["Sarah", "Gwendolyn", "Chidi", "Haruki", "Aarav", "Lucia"]
    return [
        person(
            f"PRS-{i:07d}",
            name=f"{firsts[i % len(firsts)]} Quinn {surnames[i % len(surnames)]}",
            date_of_birth=f"19{50 + i % 45}-0{1 + i % 9}-1{i % 9}",
            phone=f"+1 55{i:07d}",
            city=["Toronto", "Lagos", "Osaka"][i % 3],
            country=["Canada", "Nigeria", "Japan"][i % 3],
            nationality=["Canada", "Nigeria", "Japan"][i % 3],
            occupation="Logistics Manager",
            gender="Female",
            state="Ontario",
        )
        for i in range(count)
    ]


# ── Corruptions ──────────────────────────────────────────────────────────────


def test_a_corruption_that_cannot_apply_returns_none_rather_than_an_unchanged_copy() -> None:
    """An unchanged "corrupted" pair scores 1.0 and silently inflates recall —
    the exact failure a labelled set exists to prevent."""
    single_token = person("PRS-0000001", name="Prince")
    assert evaluation.perturb(single_token, "name_middle_dropped", RNG) is None
    assert evaluation.perturb(single_token, "dob_missing", RNG) is None
    assert evaluation.perturb(single_token, "phone_missing", RNG) is None


@pytest.mark.parametrize("corruption", evaluation.CORRUPTIONS)
def test_every_corruption_either_changes_the_record_or_declines(corruption: str) -> None:
    original = population(1)[0]
    twin = evaluation.perturb(original, corruption, random.Random(3))
    if twin is None:
        return
    assert twin.attributes != original.attributes
    assert twin.ref != original.ref


def test_a_corrupted_copy_is_never_written_back_as_a_real_record() -> None:
    """Constructed pairs must not leak into the graph as discovered entities."""
    twin = evaluation.perturb(population(1)[0], "name_typo", random.Random(1))
    assert twin is not None
    assert twin.origin == "synthetic-evaluation"
    assert "~" in twin.ref


# ── The labelled set ─────────────────────────────────────────────────────────


def test_the_negative_set_contains_pairs_blocking_would_actually_produce() -> None:
    """Random pairs almost never collide, so a precision figure computed from
    them measures a question the matcher is never asked."""
    pairs = evaluation.build_synthetic_set(population(), negatives=40)
    hard = [p for p in pairs if p.corruption == "distinct_blocked"]
    assert hard, "no hard negatives were generated"
    for pair in hard:
        assert blocking_keys(pair.left) & blocking_keys(pair.right)
        assert pair.is_same is False


def test_the_labelled_set_is_reproducible_from_its_seed() -> None:
    """An evaluation whose numbers move between runs cannot be used to decide
    whether a weight change helped."""
    first = evaluation.build_synthetic_set(population(), seed=99)
    second = evaluation.build_synthetic_set(population(), seed=99)
    assert [(p.left.ref, p.right.ref, p.is_same) for p in first] == [
        (p.left.ref, p.right.ref, p.is_same) for p in second
    ]


def test_positive_and_negative_pairs_are_both_present() -> None:
    pairs = evaluation.build_synthetic_set(population(), negatives=30)
    assert any(p.is_same for p in pairs)
    assert any(not p.is_same for p in pairs)


# ── Metrics ──────────────────────────────────────────────────────────────────


def test_a_rate_with_no_denominator_is_none_rather_than_zero() -> None:
    empty = evaluation.Metrics()
    assert empty.precision is None
    assert empty.recall is None
    assert empty.f1 is None
    assert empty.blocking_recall is None


def test_blocking_recall_is_reported_separately_from_scorer_recall() -> None:
    """A pair blocking never surfaces is a miss no scoring can recover, and
    reporting only the scorer would claim recall the pipeline does not achieve."""
    left = person("PRS-0000001", name="Sarah Ellis", city="Toronto", country="Canada")
    # Same person by every attribute the scorer sees, but nothing the blocker
    # keys on is shared, so the live pipeline would never compare them.
    right = person("PRS-0000002", name="Sarah Ellis", city="Toronto", country="Canada")
    right = EntityProfile(
        ref="PRS-0000002", entity_type="Person", attributes=dict(right.attributes)
    )
    report = evaluation.evaluate(
        [evaluation.LabelledPair(left=left, right=right, is_same=True, corruption="x")],
        dataset="test",
    )
    # These two *do* share a name block, so this is the control: blocking found it.
    assert report.overall.blocking_recall == 1.0

    unblockable = person("PRS-0000003")
    report2 = evaluation.evaluate(
        [
            evaluation.LabelledPair(
                left=left, right=unblockable, is_same=True, corruption="x"
            )
        ],
        dataset="test",
    )
    assert report2.overall.blocking_recall == 0.0


def test_a_report_carries_the_exact_model_it_measured() -> None:
    report = evaluation.evaluate([], dataset="test")
    assert report.model_fingerprint
    assert report.model_version


def test_the_two_datasets_are_never_merged_into_one_figure() -> None:
    """They answer different questions; an average would describe neither."""
    synthetic = evaluation.evaluate([], dataset="synthetic")
    analyst = evaluation.evaluate([], dataset="analyst")
    assert synthetic.as_dict()["dataset"] == "synthetic"
    assert analyst.as_dict()["dataset"] == "analyst"


def test_misses_and_false_alarms_are_sampled_not_dumped() -> None:
    report = evaluation.EvaluationReport(
        dataset="test",
        model_version="v",
        model_fingerprint="f",
        overall=evaluation.Metrics(),
        misses=[{"left": str(i)} for i in range(100)],
    )
    payload = report.as_dict()
    assert len(payload["misses"]) == 25
    assert payload["miss_count"] == 100


def test_a_pair_the_matcher_declines_to_raise_counts_as_a_miss() -> None:
    """From an analyst's seat, a duplicate that never reaches the queue and one
    the matcher rejected are the same outcome."""
    thin_left = person("PRS-0000001", name="Sarah Ellis")
    thin_right = person("PRS-0000002", name="Sarah Ellis")
    report = evaluation.evaluate(
        [
            evaluation.LabelledPair(
                left=thin_left, right=thin_right, is_same=True, corruption="sparse"
            )
        ],
        dataset="test",
    )
    assert report.overall.false_negative == 1
    assert report.overall.recall == 0.0
