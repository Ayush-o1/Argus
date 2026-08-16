"""The matching core: normalisation, comparators, scoring, blocking, clustering.

Pure functions, no database. That is the point of the layering — the decision
path that merges two people can be exercised, and re-derived years later,
without a running stack.

Several tests here exist because the behaviour they pin was wrong first, and
those say so.
"""

from __future__ import annotations

import pytest

from app.resolution import similarity
from app.resolution.blocking import (
    MAX_BLOCK_SIZE,
    blocking_keys,
    candidate_pairs,
    order_pair,
)
from app.resolution.clustering import build_clusters
from app.resolution.normalize import (
    identifier_key,
    name_tokens,
    normalize_text,
    parse_date,
    phone_digits,
    phonetic_token,
    soundex,
)
from app.resolution.profile import EntityProfile, profile_from_node, profile_from_record
from app.resolution.scoring import (
    BAND_AUTO,
    BAND_INSUFFICIENT,
    BAND_REJECT,
    BAND_REVIEW,
    DEFAULT_MODEL,
    MatchModel,
    compare,
)


def person(ref: str, **attributes: object) -> EntityProfile:
    coordinates = attributes.pop("coordinates", None)
    return EntityProfile(
        ref=ref,
        entity_type="Person",
        attributes=dict(attributes),
        coordinates=coordinates,  # type: ignore[arg-type]
    )


# ── Normalisation ────────────────────────────────────────────────────────────


def test_accents_fold_onto_base_letters() -> None:
    assert normalize_text("José Álvarez") == "jose alvarez"


def test_dotted_acronyms_join_rather_than_splitting_into_letters() -> None:
    """`B.V.` must not become the two tokens `b` and `v`.

    It did, and the single letters then looked exactly like personal initials —
    which made "Alpine Exports B.V." and "Zenith Medical Systems B.V." score as
    an agreeing name in a live matcher run.
    """
    assert normalize_text("Alpine Exports B.V.") == "alpine exports bv"
    assert normalize_text("U.S.A. Holdings") == "usa holdings"


def test_a_single_personal_initial_is_left_alone() -> None:
    """The acronym rule must not eat "J. Smith" — that initial is real signal."""
    assert normalize_text("J. Smith") == "j smith"


def test_legal_forms_are_dropped_for_organisations_only() -> None:
    assert name_tokens("Alpine Exports B.V.", kind="organization") == ["alpine", "exports"]
    assert "ltd" in name_tokens("Ltd", kind="person")


def test_a_name_made_entirely_of_noise_keeps_its_tokens() -> None:
    """An empty comparison key silently matches everything — the worst outcome."""
    assert name_tokens("The Group Holdings", kind="organization") != []


def test_soundex_is_stable_and_classic() -> None:
    assert soundex("Robert") == "R163"
    assert soundex("Rupert") == "R163"
    assert soundex("Tymczak") == "T522"


@pytest.mark.parametrize("name", ["김동현", "الأستاذة", "Χατζαντώνης", "李帆"])
def test_non_latin_names_still_produce_a_blocking_token(name: str) -> None:
    """Soundex returns nothing for a non-Latin script.

    Left as-is, that meant every person whose name is not written in Latin
    letters joined no name block, was never compared with anything, and could
    not be deduplicated — silently, and only for them. Found by the evaluation
    harness reporting blocking recall below 1.0.
    """
    assert soundex(name) == ""
    assert phonetic_token(name) != ""


def test_phone_digits_strip_formatting() -> None:
    assert phone_digits("+1 (645) 221-119") == "1645221119"


def test_identifier_key_ignores_separators_and_case() -> None:
    assert identifier_key("gj-10 bb 9031") == identifier_key("GJ10BB9031")


def test_an_unparseable_date_is_none_rather_than_a_guess() -> None:
    assert parse_date("not a date") is None
    assert parse_date("") is None
    assert parse_date("1998-09-16") is not None


# ── Comparators: the None contract ───────────────────────────────────────────


@pytest.mark.parametrize(
    "comparator,left,right",
    [
        (similarity.name_similarity, None, "Sarah Ellis"),
        (similarity.exact_similarity, "Canada", None),
        (similarity.identifier_similarity, "", "GJ10BB9031"),
        (similarity.phone_similarity, "+1 645221119", None),
        (similarity.date_similarity, "1998-09-16", None),
        (similarity.set_similarity, [], ["x"]),
        (similarity.geo_similarity, None, (1.0, 2.0)),
    ],
)
def test_a_missing_value_is_not_comparable_rather_than_zero(
    comparator: object, left: object, right: object
) -> None:
    """The central contract of this module.

    Scoring a missing attribute as 0.0 would refuse obvious matches; scoring it
    as 1.0 would merge strangers. Both produce confident output while lying
    about what is known.
    """
    assert comparator(left, right) is None  # type: ignore[operator]


def test_names_match_across_reordering_and_missing_middle_names() -> None:
    assert similarity.name_similarity("Sarah Ellis", "Ellis Sarah") == 1.0
    assert (similarity.name_similarity("Sarah Jane Ellis", "Sarah Ellis") or 0) >= 0.85


def test_personal_initials_match_but_organisations_have_none() -> None:
    assert (similarity.name_similarity("J. Smith", "John A Smith") or 0) >= 0.85
    unrelated = similarity.name_similarity(
        "Alpine Exports B.V.", "Zenith Medical Systems B.V.", kind="organization"
    )
    assert unrelated is not None and unrelated < 0.7


def test_a_transposed_date_gets_partial_credit_but_a_nearby_one_gets_none() -> None:
    """"Close in time" is not evidence of being the same birth date.

    The last assertion is the one that matters: two different days in the same
    month scored 0.5 for a while, which was enough to stop date of birth
    disqualifying a pair it should have.
    """
    assert similarity.date_similarity("1998-09-04", "1998-04-09") == 0.7
    assert similarity.date_similarity("1998-09-01", "1998-09-16") == 0.5
    assert similarity.date_similarity("1998-09-16", "1998-09-23") == 0.0


def test_a_phone_suffix_match_is_worth_less_than_a_full_match() -> None:
    full = similarity.phone_similarity("+1 645221119", "1645221119")
    suffix = similarity.phone_similarity("+1 645221119", "+44 645221119")
    assert full == 1.0
    assert suffix is not None and suffix < 1.0


# ── Scoring ──────────────────────────────────────────────────────────────────


def test_evidence_weight_is_the_denominator_of_the_score() -> None:
    """A score computed from two attributes is not the same claim as one
    computed from eight, and the result must carry both numbers."""
    thin = compare(
        person("PRS-0000001", name="Sarah Ellis"),
        person("PRS-0000002", name="Sarah Ellis"),
    )
    assert thin.score == 1.0
    assert thin.evidence_weight < 0.3
    assert thin.band == BAND_INSUFFICIENT
    assert "comparable" in thin.band_reason


def test_a_disqualifying_disagreement_beats_any_amount_of_agreement() -> None:
    left = person(
        "PRS-0000001", name="Sarah Ellis", date_of_birth="1998-09-16",
        phone="+1 645221119", city="Toronto", country="Canada", nationality="Canada",
    )
    right = person(
        "PRS-0000002", name="Sarah Ellis", date_of_birth="1971-02-03",
        phone="+1 645221119", city="Toronto", country="Canada", nationality="Canada",
    )
    result = compare(left, right)
    assert result.band == BAND_REJECT
    assert "Date of birth" in result.band_reason


def test_soft_agreement_alone_never_reaches_the_auto_band() -> None:
    """The roadmap asked for "auto-merge above a high threshold". A high score
    from soft attributes is similarity, not identity, so this deliberately
    requires an exact identifier as well."""
    left = person(
        "PRS-0000001", name="Sarah Ellis", date_of_birth="1998-09-16",
        city="Toronto", state="Ontario", country="Canada",
        nationality="Canada", occupation="Logistics Manager", gender="Female",
    )
    right = person(
        "PRS-0000002", name="Sarah Ellis", date_of_birth="1998-09-16",
        city="Toronto", state="Ontario", country="Canada",
        nationality="Canada", occupation="Logistics Manager", gender="Female",
    )
    result = compare(left, right)
    assert result.score == 1.0
    assert result.band == BAND_REVIEW
    assert "no identifier matched exactly" in result.band_reason


def test_an_exact_identifier_with_nothing_disagreeing_reaches_auto() -> None:
    left = person(
        "PRS-0000001", name="Sarah Ellis", date_of_birth="1998-09-16",
        phone="+1 645221119", city="Toronto", state="Ontario", country="Canada",
        nationality="Canada", occupation="Logistics Manager", gender="Female",
    )
    right = person(
        "PRS-0000002", name="Sarah Ellis", date_of_birth="1998-09-16",
        phone="1645221119", city="Toronto", state="Ontario", country="Canada",
        nationality="Canada", occupation="Logistics Manager", gender="Female",
    )
    result = compare(left, right)
    assert result.band == BAND_AUTO


def test_an_exact_identifier_does_not_override_a_contradiction() -> None:
    """Cross-phase invariant 6, applied to a single pair."""
    left = person(
        "PRS-0000001", name="Sarah Ellis", date_of_birth="1998-09-16",
        phone="+1 645221119", city="Toronto", country="Canada", nationality="Canada",
        occupation="Logistics Manager", gender="Female", state="Ontario",
    )
    # Everything agrees, the phone matches exactly, and the score clears the
    # auto threshold — but the two records disagree about gender. That single
    # contradiction is enough to hand the decision to a person.
    right = person(
        "PRS-0000002", name="Sarah Ellis", date_of_birth="1998-09-16",
        phone="1645221119", city="Toronto", country="Canada", nationality="Canada",
        occupation="Logistics Manager", gender="Male", state="Ontario",
    )
    result = compare(left, right)
    assert result.score is not None and result.score >= DEFAULT_MODEL.auto_score
    assert result.band == BAND_REVIEW
    assert "disagrees" in result.band_reason
    assert "never resolved automatically" in result.band_reason


def test_two_records_with_nothing_in_common_have_no_score_at_all() -> None:
    """None, not 0.0 — "no idea" and "definitely different" are different claims."""
    result = compare(
        person("PRS-0000001", name="Sarah Ellis"),
        person("PRS-0000002", city="Lagos"),
    )
    assert result.score is None
    assert result.band == BAND_INSUFFICIENT


def test_comparing_across_entity_types_is_refused() -> None:
    with pytest.raises(ValueError, match="never across"):
        compare(
            person("PRS-0000001", name="X"),
            EntityProfile(ref="ORG-1", entity_type="Organization", attributes={"name": "X"}),
        )


def test_every_comparison_is_kept_including_the_ones_that_could_not_be_made() -> None:
    """Storing only the agreements would produce a review screen that argues
    for the merge and never against it."""
    result = compare(
        person("PRS-0000001", name="Sarah Ellis", city="Toronto"),
        person("PRS-0000002", name="Sarah Ellis", city="Toronto"),
    )
    keys = {c.key for c in result.comparisons}
    assert {"name", "date_of_birth", "phone", "gender", "coordinates"} <= keys
    assert result.not_comparable


def test_the_fingerprint_changes_when_a_threshold_changes() -> None:
    """An evaluation report must not be re-attributable to a model whose
    parameters have since moved."""
    assert DEFAULT_MODEL.fingerprint() != MatchModel(auto_score=0.99).fingerprint()


def test_scoring_is_deterministic() -> None:
    left = person("PRS-0000001", name="Sarah Ellis", date_of_birth="1998-09-16")
    right = person("PRS-0000002", name="Sarah J Ellis", date_of_birth="1998-09-16")
    assert compare(left, right).score == compare(left, right).score


# ── Blocking ─────────────────────────────────────────────────────────────────


def test_pair_ordering_is_canonical_in_both_directions() -> None:
    assert order_pair("B", "A") == order_pair("A", "B") == ("A", "B")


def test_a_record_with_no_usable_attribute_joins_no_block() -> None:
    assert blocking_keys(person("PRS-0000001")) == set()


def test_blocking_finds_a_reordered_name_and_says_which_key_did_it() -> None:
    left = person("PRS-0000001", name="Sarah Ellis", city="Toronto")
    right = person("PRS-0000002", name="Ellis Sarah", city="Toronto")
    pairs, report = candidate_pairs([left, right])
    assert ("PRS-0000001", "PRS-0000002") in pairs
    assert any("name_phonetic" in key for key in pairs[("PRS-0000001", "PRS-0000002")])
    assert report.unblocked == []


def test_an_oversized_block_is_reported_rather_than_silently_skipped() -> None:
    """A key matching thousands of records has stopped discriminating. Hiding
    that would make the recall loss undetectable."""
    crowd = [
        person(f"PRS-{i:07d}", name="Sarah Ellis", city="Toronto")
        for i in range(MAX_BLOCK_SIZE + 5)
    ]
    pairs, report = candidate_pairs(crowd)
    assert pairs == {}
    assert report.oversized
    assert all(size > MAX_BLOCK_SIZE for size in report.oversized.values())


def test_unblockable_records_are_counted() -> None:
    _, report = candidate_pairs([person("PRS-0000001"), person("PRS-0000002")])
    assert report.unblocked == ["PRS-0000001", "PRS-0000002"]


# ── Clustering ───────────────────────────────────────────────────────────────


def test_identity_is_transitive() -> None:
    clusters = build_clusters(
        [("Person", "PRS-A", "PRS-B"), ("Person", "PRS-B", "PRS-C")], set()
    )
    assert len(clusters) == 1
    assert clusters[0].members == ["PRS-A", "PRS-B", "PRS-C"]


def test_a_contradiction_inside_a_cluster_is_flagged_not_resolved() -> None:
    """ARGUS does not drop the weakest link or pick a side. It says so."""
    clusters = build_clusters(
        [("Person", "PRS-A", "PRS-B"), ("Person", "PRS-B", "PRS-C")],
        {("PRS-A", "PRS-C")},
    )
    assert clusters[0].contested is True
    assert clusters[0].contested_reason is not None
    assert "PRS-A / PRS-C" in clusters[0].contested_reason
    # Nothing was removed to make the contradiction go away.
    assert clusters[0].members == ["PRS-A", "PRS-B", "PRS-C"]


def test_a_record_that_matched_nothing_is_not_a_cluster_of_one() -> None:
    assert build_clusters([], set()) == []


def test_the_canonical_record_is_the_best_corroborated_and_says_so() -> None:
    clusters = build_clusters(
        [("Person", "PRS-A", "PRS-B")],
        set(),
        observation_counts={"PRS-A": 2, "PRS-B": 40},
    )
    assert clusters[0].canonical_ref == "PRS-B"
    assert "40" in clusters[0].canonical_basis


def test_canonical_selection_is_stable_when_nothing_distinguishes_the_members() -> None:
    clusters = build_clusters([("Person", "PRS-B", "PRS-A")], set())
    assert clusters[0].canonical_ref == "PRS-A"
    assert "lowest id" in clusters[0].canonical_basis


def test_an_analyst_pin_overrides_the_rule_and_the_basis_says_which() -> None:
    clusters = build_clusters(
        [("Person", "PRS-A", "PRS-B")],
        set(),
        observation_counts={"PRS-A": 99},
        pinned={"PRS-B": "Jordan Vale"},
    )
    assert clusters[0].canonical_ref == "PRS-B"
    assert "pinned by Jordan Vale" in clusters[0].canonical_basis


def test_cluster_keys_do_not_depend_on_the_order_decisions_arrived_in() -> None:
    forward = build_clusters(
        [("Person", "PRS-A", "PRS-B"), ("Person", "PRS-B", "PRS-C")], set()
    )
    backward = build_clusters(
        [("Person", "PRS-B", "PRS-C"), ("Person", "PRS-A", "PRS-B")], set()
    )
    assert forward[0].cluster_key == backward[0].cluster_key


# ── Profiles ─────────────────────────────────────────────────────────────────


def test_a_node_without_an_id_produces_no_profile() -> None:
    assert profile_from_node("Person", {"name": "Nobody"}) is None


def test_an_unsupported_type_produces_no_profile() -> None:
    assert profile_from_node("Storyline", {"storyline_id": "STL-1"}) is None


def test_a_feed_cannot_introduce_an_attribute_the_model_does_not_score() -> None:
    profile = profile_from_record(
        "PRS-0000001", "Person", {"name": "Sarah Ellis", "shoe_size": 9}, origin="feed"
    )
    assert profile is not None
    assert "shoe_size" not in profile.attributes
