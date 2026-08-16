"""Record mapping and timestamp normalisation, as pure assertions.

The timestamp rules are the important part. A feed's time field is the axis an
investigation orders everything by, so a wrong instant is not a cosmetic defect
— and the ways to get one wrong are all silent.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.ingestion.mapping import (
    InvalidMapping,
    MappingError,
    RecordMapping,
    apply_mapping,
    dig,
    field_paths,
    parse_timestamp,
)


def _mapping(**overrides: object) -> RecordMapping:
    base = {
        "content_type": "test.report",
        "subject_path": "entity_id",
        "occurred_at_path": "observed_at",
    }
    base.update(overrides)
    return RecordMapping.from_config(base)


# ── The rule that matters most ───────────────────────────────────────────────


def test_a_naive_timestamp_with_no_declared_zone_yields_no_instant() -> None:
    """The decisive behaviour of this module.

    ARGUS read the generator's naive local timestamps as UTC — an assumption
    wrong by up to a day, and invisible when it is (audit B-17). A wall-clock
    string with no zone is not an instant, and no amount of convenience makes it
    one. The value is preserved in the payload; the instant stays unknown.
    """
    mapping = _mapping()  # no `timezone` declared
    result = apply_mapping(
        {"entity_id": "PRS-0000001", "observed_at": "2026-08-01 10:00:00"}, mapping
    )
    assert result.occurred_at is None
    assert result.unresolved_timestamps
    assert "no timezone" in result.unresolved_timestamps[0]
    # And the raw value survives, so nothing is lost by declining to guess.
    assert result.payload["observed_at"] == "2026-08-01 10:00:00"


def test_a_declared_timezone_makes_a_naive_timestamp_usable() -> None:
    """The escape hatch is a *stated convention*, recorded per source, rather
    than a global assumption nobody made deliberately."""
    mapping = _mapping(timezone="Asia/Kolkata")
    result = apply_mapping(
        {"entity_id": "PRS-0000001", "observed_at": "2026-08-01 10:00:00"}, mapping
    )
    assert result.occurred_at == datetime(2026, 8, 1, 4, 30, tzinfo=UTC)
    assert not result.unresolved_timestamps


def test_an_offset_aware_timestamp_never_needs_a_declaration() -> None:
    """It carries its own answer; nothing is being assumed, so the source's
    declared zone is irrelevant."""
    for mapping in (_mapping(), _mapping(timezone="Asia/Kolkata")):
        result = apply_mapping(
            {"entity_id": "PRS-0000001", "observed_at": "2026-08-01T10:00:00+02:00"}, mapping
        )
        assert result.occurred_at == datetime(2026, 8, 1, 8, 0, tzinfo=UTC)


def test_an_unparseable_timestamp_is_reported_not_swallowed() -> None:
    mapping = _mapping(timezone="UTC")
    result = apply_mapping({"entity_id": "PRS-0000001", "observed_at": "last tuesday"}, mapping)
    assert result.occurred_at is None
    assert "unparseable" in result.unresolved_timestamps[0]


def test_a_declared_timezone_must_be_real() -> None:
    with pytest.raises(InvalidMapping):
        _mapping(timezone="Mars/Olympus_Mons")


# ── Timestamp parsing ────────────────────────────────────────────────────────


def test_epoch_seconds_and_milliseconds_are_distinguished() -> None:
    """Getting this wrong is a 1000x error in the field everything is ordered
    by, and it produces a date in the far future rather than an exception."""
    assert parse_timestamp(1_754_049_600) == datetime(2025, 8, 1, 12, 0, tzinfo=UTC)
    assert parse_timestamp(1_754_049_600_000) == datetime(2025, 8, 1, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "value",
    [
        "2026-08-01T10:00:00Z",
        "2026-08-01T10:00:00+00:00",
        "2026-08-01 10:00:00",
        "2026-08-01",
        "01/08/2026",
        "Sat, 01 Aug 2026 10:00:00 +0000",
    ],
)
def test_real_world_timestamp_shapes_parse(value: str) -> None:
    assert parse_timestamp(value) is not None


@pytest.mark.parametrize("value", ["", "   ", "not a date", None, {}, [], True])
def test_non_timestamps_return_none_rather_than_guessing(value: object) -> None:
    assert parse_timestamp(value) is None


# ── Subject resolution ───────────────────────────────────────────────────────


def test_an_unknown_subject_is_rejected_with_the_reason() -> None:
    """Ingestion records observations about entities that exist. Creating them
    from an unresolved feed is how one real person becomes three entities, so
    the record is dead-lettered — visibly, with an explanation — instead."""
    with pytest.raises(MappingError, match="does not match any known entity id prefix"):
        apply_mapping({"entity_id": "WHAT-0001", "observed_at": "2026-08-01T10:00:00Z"}, _mapping())


def test_a_missing_subject_is_rejected() -> None:
    with pytest.raises(MappingError, match="no subject"):
        apply_mapping({"observed_at": "2026-08-01T10:00:00Z"}, _mapping())


def test_required_fields_are_enforced_and_all_reported() -> None:
    mapping = _mapping(required_fields=["entity_id", "observed_at", "reporter"])
    with pytest.raises(MappingError) as exc:
        apply_mapping({"entity_id": "PRS-0000001"}, mapping)
    assert "observed_at" in str(exc.value)
    assert "reporter" in str(exc.value)


def test_the_subject_type_comes_from_the_id_prefix() -> None:
    result = apply_mapping(
        {"entity_id": "ORG-0000004", "observed_at": "2026-08-01T10:00:00Z"}, _mapping()
    )
    assert result.subject_type == "Organization"
    assert result.subject_ref == "ORG-0000004"


def test_a_mapping_needs_a_content_type_and_a_subject() -> None:
    with pytest.raises(InvalidMapping):
        RecordMapping.from_config({"content_type": "x"})
    with pytest.raises(InvalidMapping):
        RecordMapping.from_config({"subject_path": "x"})


# ── Paths ────────────────────────────────────────────────────────────────────


def test_dotted_paths_reach_nested_values() -> None:
    payload = {"a": {"b": {"c": 1}}, "list": [{"x": 2}]}
    assert dig(payload, "a.b.c") == 1
    assert dig(payload, "list.0.x") == 2
    assert dig(payload, "a.missing.c") is None
    assert dig(payload, "a.b.c.d") is None


def test_field_paths_enumerates_nested_structure() -> None:
    """Drift detection sees a renamed nested field, not just a top-level one."""
    paths = field_paths({"a": 1, "b": {"c": 2, "d": {"e": 3}}})
    assert paths == {"a", "b", "b.c", "b.d", "b.d.e"}


def test_field_paths_is_depth_bounded() -> None:
    """A pathological payload must not turn drift detection into an unbounded
    walk. Bounded, and the bound is not an error — just a stop."""
    deep: dict = {"leaf": 1}
    for _ in range(30):
        deep = {"nest": deep}
    paths = field_paths(deep)
    assert paths
    assert max(p.count(".") for p in paths) <= 6


# ── Match attributes (Phase 4) ───────────────────────────────────────────────


def test_a_mapping_may_declare_attributes_for_matching() -> None:
    mapping = RecordMapping.from_config(
        {
            "content_type": "t",
            "subject_path": "ref",
            "match_attributes": {"name": "subject.full_name", "phone": "subject.tel"},
        }
    )
    mapped = apply_mapping(
        {"ref": "PRS-0000001", "subject": {"full_name": "Sarah Ellis", "tel": "+1 645221119"}},
        mapping,
    )
    assert mapped.match_attributes == {"name": "Sarah Ellis", "phone": "+1 645221119"}


def test_an_unknown_match_attribute_is_refused_at_configuration_time() -> None:
    """Rather than being ignored at match time while appearing to do something.

    A feed that declares `email` — which no rule scores — would otherwise look
    configured for matching and contribute nothing.
    """
    with pytest.raises(InvalidMapping, match="unknown match attribute"):
        RecordMapping.from_config(
            {"content_type": "t", "subject_path": "ref", "match_attributes": {"email": "e"}}
        )


def test_match_attributes_are_optional() -> None:
    mapping = RecordMapping.from_config({"content_type": "t", "subject_path": "ref"})
    assert mapping.match_attributes == {}
    assert apply_mapping({"ref": "PRS-0000001"}, mapping).match_attributes == {}


def test_a_missing_match_attribute_is_absent_rather_than_empty() -> None:
    """An empty string is a value the comparators would try to compare."""
    mapping = RecordMapping.from_config(
        {
            "content_type": "t",
            "subject_path": "ref",
            "match_attributes": {"name": "n", "phone": "p"},
        }
    )
    mapped = apply_mapping({"ref": "PRS-0000001", "n": "Sarah Ellis", "p": ""}, mapping)
    assert mapped.match_attributes == {"name": "Sarah Ellis"}
