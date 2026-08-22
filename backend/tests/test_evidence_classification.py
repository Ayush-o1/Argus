"""Classification, clearance, and the export retention schedule."""

from __future__ import annotations

import pytest

from app.evidence.artifacts import digest, verify
from app.evidence.classification import (
    CLASSIFICATIONS,
    DEFAULT_CLASSIFICATION,
    classification_by_code,
    may_access,
    rank,
    retention_days,
)


def test_clearance_bounds_access_in_both_directions():
    assert may_access("restricted", "internal")
    assert may_access("internal", "internal")
    assert not may_access("internal", "confidential")
    assert not may_access("unrestricted", "internal")


def test_the_order_is_a_rank_and_not_the_alphabet():
    """The bug this exists to prevent.

    `confidential` sorts before `internal` alphabetically, so a string
    comparison would let an internal clearance read confidential material — the
    kind of mistake that works in every test except the one level that matters.
    """
    assert "confidential" < "internal"  # what the alphabet says
    assert rank("confidential") > rank("internal")  # what the scheme says
    assert not may_access("internal", "confidential")


def test_the_default_does_not_under_classify():
    # A default that leaks is worse than one that inconveniences.
    assert DEFAULT_CLASSIFICATION == "internal"
    assert rank(DEFAULT_CLASSIFICATION) > rank("unrestricted")


def test_more_sensitive_material_is_retained_longer_not_shorter():
    """The counter-intuitive half of the retention design.

    A restricted export is the one whose custody record matters most; disposing
    of it early destroys the evidence of who held it.
    """
    days = [retention_days(c.code) for c in CLASSIFICATIONS]
    assert days == sorted(days), "retention must not decrease as sensitivity rises"


def test_every_level_states_how_to_handle_it():
    for level in CLASSIFICATIONS:
        assert level.handling.strip()
        assert level.means.strip()


def test_an_unknown_level_raises_rather_than_defaulting():
    # Failing loudly at the typo beats silently ranking it 0 and granting
    # everything, or -1 and granting nothing.
    with pytest.raises(ValueError, match="not a classification"):
        classification_by_code("top-secret")
    with pytest.raises(ValueError):
        may_access("wizard", "internal")


class TestArtifacts:
    def test_identical_bytes_hash_identically(self):
        assert digest(b"abc").sha256 == digest(b"abc").sha256

    def test_a_single_changed_byte_changes_the_hash(self):
        assert digest(b"report v1").sha256 != digest(b"report v2").sha256

    def test_verify_accepts_untouched_content(self):
        artifact = digest(b"an investigation")
        ok, explanation = verify(artifact.content, artifact.sha256)
        assert ok
        assert "re-hashes to the value recorded" in explanation

    def test_verify_rejects_altered_content(self):
        artifact = digest(b"an investigation")
        ok, explanation = verify(b"a different investigation", artifact.sha256)
        assert not ok
        assert "have changed since they were produced" in explanation

    def test_a_disposed_artifact_is_not_reported_as_corrupted(self):
        """Routine disposal and tampering must not look the same.

        Conflating them would make every scheduled disposal surface as an
        integrity incident, which is the fastest way to get integrity alerts
        ignored.
        """
        ok, explanation = verify(b"", digest(b"anything").sha256)
        assert not ok
        assert "disposed of" in explanation
        assert "changed" not in explanation
