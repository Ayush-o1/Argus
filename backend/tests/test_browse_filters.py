"""Filter construction for GET /api/entities (app/repositories/graph_repo.py).

The risk filter was previously applied only to Person and Organization, so
browsing any other label with a minimum risk returned a full unfiltered page
presented to the analyst as matching their filter. These tests pin the
corrected behaviour.
"""

import pytest

from app.repositories.graph_repo import BROWSABLE_LABELS, build_browse_filters


@pytest.mark.parametrize("label", BROWSABLE_LABELS)
def test_risk_filter_applies_to_every_browsable_label(label):
    risk_filter, _ = build_browse_filters(label, risk_min=60, city=None)
    assert risk_filter == "AND n.risk_score >= $risk_min"


@pytest.mark.parametrize("label", BROWSABLE_LABELS)
def test_no_risk_filter_when_threshold_is_zero(label):
    risk_filter, _ = build_browse_filters(label, risk_min=0, city=None)
    assert risk_filter == ""


@pytest.mark.parametrize("label", ["Person", "Organization", "Location"])
def test_city_filter_applies_where_the_property_exists(label):
    _, city_filter = build_browse_filters(label, risk_min=0, city="Mumbai")
    assert city_filter == "AND n.city = $city"


@pytest.mark.parametrize("label", ["Vehicle", "Device"])
def test_city_filter_skipped_where_the_property_does_not_exist(label):
    _, city_filter = build_browse_filters(label, risk_min=0, city="Mumbai")
    assert city_filter == ""


def test_city_filter_skipped_when_no_city_given():
    _, city_filter = build_browse_filters("Person", risk_min=0, city=None)
    assert city_filter == ""
