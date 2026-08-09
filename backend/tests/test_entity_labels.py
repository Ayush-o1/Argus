"""Unit tests for human-ID -> Neo4j label resolution (app/repositories/entity_labels.py).

Every route that accepts a human-readable ID (GET /api/entities/{id}, case
evidence linking, etc.) depends on this resolving correctly — a wrong label
or id_field here means silently querying the wrong node type.
"""

from app.repositories.entity_labels import ENTITY_LABELS, resolve_label


def test_resolves_every_known_prefix():
    for prefix, info in ENTITY_LABELS.items():
        resolved = resolve_label(f"{prefix}-0000001")
        assert resolved == info


def test_resolves_person_id():
    info = resolve_label("PRS-0003296")
    assert info is not None
    assert info.label == "Person"
    assert info.id_field == "person_id"
    assert info.name_field == "name"


def test_unknown_prefix_returns_none():
    assert resolve_label("XYZ-0000001") is None


def test_id_without_hyphen_returns_none():
    assert resolve_label("PRS0003296") is None


def test_empty_string_returns_none():
    assert resolve_label("") is None
