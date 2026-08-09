"""Unit tests for deterministic template narratives (app/services/narrative.py).

These are the "local intelligence" feature ARGUS_PLAN.md positions as an
LLM-free alternative to AI-generated summaries — every sentence must map
1:1 to a fact that was actually queried, so these tests pin that contract.
"""

from app.services.narrative import compose_case_narrative, compose_entity_narrative


def test_person_narrative_includes_bio_and_risk():
    text = compose_entity_narrative(
        "Person",
        "Aarav Sharma",
        {"dob": "1990-01-01", "occupation": "Analyst", "city": "Pune", "state": "Maharashtra", "risk_score": 82},
        {"Account": 2, "Device": 1},
    )
    assert "Aarav Sharma" in text
    assert "Pune, Maharashtra" in text
    assert "Risk score: 82/100 (critical)" in text
    assert "2 accounts" in text
    assert "1 device" in text


def test_person_narrative_handles_missing_optional_fields():
    text = compose_entity_narrative("Person", "Jane Doe", {}, {})
    assert "Jane Doe is individual." in text
    assert "Risk score: 0/100 (low)" in text


def test_organization_narrative():
    text = compose_entity_narrative(
        "Organization",
        "Acme Logistics",
        {"industry": "Logistics", "registered_city": "Mumbai", "state": "Maharashtra", "risk_score": 45},
        {},
    )
    assert "Acme Logistics is an organization operating in Logistics registered in Mumbai, Maharashtra." in text
    assert "moderate" in text


def test_risk_factors_are_cited():
    text = compose_entity_narrative(
        "Person",
        "Jane Doe",
        {"risk_score": 70, "risk_factors": ["Frequent high-value transfers"]},
        {},
    )
    assert "frequent high-value transfers" in text


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
