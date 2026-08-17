"""Filter construction for GET /api/entities (app/repositories/graph_repo.py).

Two behaviours are pinned here, from two different phases.

The filter was once applied only to Person and Organization, so browsing any
other label with a minimum risk returned a full unfiltered page presented to
the analyst as matching their filter.

It filtered on the scenario generator's `risk_score` — the answer key — which
Phase 5 replaced with ARGUS's own assessment band. The band is the honest unit
to filter on: a score is a share of whatever could be evaluated for that
subject, so a numeric threshold across mixed subject types compares numbers
with different denominators.
"""

import pytest

from app.repositories.graph_repo import BROWSABLE_BANDS, BROWSABLE_LABELS, build_browse_filters


@pytest.mark.parametrize("label", BROWSABLE_LABELS)
def test_band_filter_applies_to_every_browsable_label(label):
    band_filter, _ = build_browse_filters(label, band="elevated", city=None)
    assert band_filter == "AND n.argus_band = $band"


@pytest.mark.parametrize("label", BROWSABLE_LABELS)
def test_no_band_filter_when_none_requested(label):
    band_filter, _ = build_browse_filters(label, band=None, city=None)
    assert band_filter == ""


def test_unassessed_selects_the_absence_of_a_band() -> None:
    """`unassessed` is not a synonym for clean, and it cannot be expressed as an
    equality: entity types ARGUS does not assess carry no band at all."""
    band_filter, _ = build_browse_filters("Person", band="unassessed", city=None)
    assert band_filter == "AND n.argus_band IS NULL"


def test_the_generator_score_is_not_filterable() -> None:
    """The browse filter must not reach the planted number under any band."""
    for band in (*BROWSABLE_BANDS, None):
        band_filter, _ = build_browse_filters("Person", band=band, city=None)
        assert "risk_score" not in band_filter


@pytest.mark.parametrize("label", ["Person", "Organization", "Location"])
def test_city_filter_applies_where_the_property_exists(label):
    _, city_filter = build_browse_filters(label, band=None, city="Mumbai")
    assert city_filter == "AND n.city = $city"


@pytest.mark.parametrize("label", ["Vehicle", "Device"])
def test_city_filter_skipped_where_the_property_does_not_exist(label):
    _, city_filter = build_browse_filters(label, band=None, city="Mumbai")
    assert city_filter == ""


def test_city_filter_skipped_when_no_city_given():
    _, city_filter = build_browse_filters("Person", band=None, city=None)
    assert city_filter == ""
