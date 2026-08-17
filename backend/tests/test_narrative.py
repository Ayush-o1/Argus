"""Unit tests for deterministic template narratives (app/services/narrative.py).

These are the "local intelligence" feature ARGUS_PLAN.md positions as an
LLM-free alternative to AI-generated summaries — every sentence must map
1:1 to a fact that was actually queried, so these tests pin that contract.
"""

from app.services.narrative import compose_case_narrative, compose_entity_narrative


def test_person_narrative_includes_bio_and_the_assessment() -> None:
    text = compose_entity_narrative(
        "Person",
        "Aarav Sharma",
        {
            "dob": "1990-01-01",
            "occupation": "Analyst",
            "city": "Pune",
            "state": "Maharashtra",
            "argus_band": "elevated",
            "argus_score": 82.0,
            "argus_coverage": 0.75,
        },
        {"Account": 2, "Device": 1},
    )
    assert "Aarav Sharma" in text
    assert "Pune, Maharashtra" in text
    assert "warranting review" in text
    assert "score 82 of 100" in text
    # The denominator travels with the number, in prose as everywhere else.
    assert "75% of its model" in text
    assert "2 accounts" in text
    assert "1 device" in text


def test_an_unassessed_entity_is_not_described_as_low_risk() -> None:
    """The narrative used to print "Risk score: 0/100 (low)" for an entity with
    no score at all — a reassuring sentence about a subject nothing was known
    about, in the confident voice of an analyst's summary."""
    text = compose_entity_narrative("Person", "Jane Doe", {}, {})
    assert "Jane Doe is individual." in text
    assert "no risk assessment" in text
    assert "0/100" not in text
    assert "low" not in text.lower().replace("logistics", "")


def test_an_unassessable_entity_says_so_without_a_score() -> None:
    text = compose_entity_narrative(
        "Person",
        "Jane Doe",
        {"argus_band": "insufficient_evidence", "argus_coverage": 0.12},
        {},
    )
    assert "does not have enough evidence" in text
    assert "no score is published" in text


def test_a_clean_entity_is_described_as_examined_not_as_safe() -> None:
    text = compose_entity_narrative(
        "Organization",
        "Acme Logistics",
        {
            "industry": "Logistics",
            "registered_city": "Mumbai",
            "state": "Maharashtra",
            "argus_band": "routine",
            "argus_score": 0.0,
            "argus_coverage": 1.0,
        },
        {},
    )
    assert (
        "Acme Logistics is an organization operating in Logistics registered in "
        "Mumbai, Maharashtra." in text
    )
    assert "examined the available evidence and found nothing of note" in text


def test_the_generators_risk_factors_are_never_recited() -> None:
    """They are the storyline the generator planted, phrased as an analyst's
    citation — "The risk assessment cites: linked to money routing network."
    That is the answer key in its most persuasive possible form."""
    text = compose_entity_narrative(
        "Person",
        "Jane Doe",
        {
            "risk_score": 70,
            "risk_factors": ["Linked to money routing network (Critical)"],
            "argus_band": "routine",
            "argus_score": 0.0,
            "argus_coverage": 1.0,
        },
        {},
    )
    assert "money routing" not in text.lower()
    assert "70" not in text


def test_case_narrative_with_no_linked_entities():
    text = compose_case_narrative({"title": "Suspicious Transfers", "status": "Open", "priority": "High"}, [])
    assert "Suspicious Transfers" in text
    assert "No entities have been linked" in text


def test_case_narrative_with_linked_entities_and_notes():
    case = {"title": "Cross-border Ring", "status": "UnderReview", "priority": "Critical", "notes": "Escalated."}
    linked = [{"label": "Person"}, {"label": "Person"}, {"label": "Account"}]
    text = compose_case_narrative(case, linked)
    assert "2 people" in text
    assert "1 account" in text
    assert "Analyst notes: Escalated." in text
