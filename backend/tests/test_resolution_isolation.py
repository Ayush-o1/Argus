"""The matcher must not read conclusions, and must not read labels.

Two separate boundaries, both structural rather than conventional, because the
audit's central finding was that convention is exactly what produced ARGUS's
presentation defects.

  **Conclusions.** `risk_score`, `flags`, `risk_factors` and `community_ids`
  are things ARGUS decided. A matcher that resolves identity partly from them
  would be reasoning from its own output — the same circularity the audit found
  in risk scoring (G-08). `storyline_id` and `flagged` are worse: they are
  generator ground truth, and reading them would let the matcher "discover"
  answers that were planted.

  **Labels.** The evaluation harness knows which pairs are truly the same. If
  any part of the scoring path could reach that, every precision and recall
  figure ARGUS publishes would be meaningless.

These are asserted against the source text and the import graph, not against
behaviour, because a test that merely checks the output today would pass again
the moment someone adds the field back.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.repositories.resolution_graph_repo import _projection
from app.resolution.profile import (
    SUPPORTED_TYPES,
    EntityProfile,
    profile_from_node,
    profile_from_record,
)
from app.resolution.scoring import RULES, compare

RESOLUTION_DIR = Path(__file__).resolve().parents[1] / "app" / "resolution"

# Properties that are conclusions or ground truth. None may reach the matcher.
FORBIDDEN = (
    "risk_score",
    "risk_factors",
    "flags",
    "flagged",
    "community_ids",
    "storyline_id",
)

# The pure decision path. `evaluation` is deliberately excluded — it is the one
# module that *is* allowed to know the truth about a pair.
DECISION_MODULES = ("normalize.py", "similarity.py", "profile.py", "scoring.py", "blocking.py",
                    "clustering.py")


@pytest.mark.parametrize("entity_type", sorted(SUPPORTED_TYPES))
def test_the_cypher_projection_never_names_a_conclusion(entity_type: str) -> None:
    """Stronger than filtering after the fetch: the query does not select them,
    so no code path can reach them even by mistake."""
    projection = _projection(entity_type)
    for forbidden in FORBIDDEN:
        assert forbidden not in projection


@pytest.mark.parametrize("entity_type", sorted(SUPPORTED_TYPES))
def test_a_node_carrying_conclusions_yields_a_profile_without_them(entity_type: str) -> None:
    node = {
        "person_id": "PRS-0000001",
        "org_id": "ORG-0000001",
        "vehicle_id": "VEH-0000001",
        "device_id": "DEV-0000001",
        "name": "Sarah Ellis",
        "plate": "GJ10BB9031",
        "imei": "854132366162523",
        "risk_score": 91.4,
        "flags": ["watchlist"],
        "risk_factors": ["storyline"],
        "community_ids": [3],
        "storyline_id": "STL-0000001",
        "flagged": True,
    }
    profile = profile_from_node(entity_type, node)
    assert profile is not None
    for forbidden in FORBIDDEN:
        assert forbidden not in profile.attributes


def test_a_feed_cannot_smuggle_a_conclusion_in_through_a_record() -> None:
    profile = profile_from_record(
        "PRS-0000001",
        "Person",
        {"name": "Sarah Ellis", "risk_score": 99.0, "storyline_id": "STL-0000001"},
        origin="feed",
    )
    assert profile is not None
    assert profile.attributes == {"name": "Sarah Ellis"}


def test_no_scoring_rule_is_defined_over_a_conclusion() -> None:
    for rules in RULES.values():
        for rule in rules:
            assert rule.key not in FORBIDDEN


def test_the_score_is_unchanged_by_conclusions_attached_to_a_profile() -> None:
    """Belt and braces: even if a profile somehow carried one, no rule reads it."""
    plain = EntityProfile(
        ref="PRS-0000001", entity_type="Person", attributes={"name": "Sarah Ellis"}
    )
    loaded = EntityProfile(
        ref="PRS-0000002",
        entity_type="Person",
        attributes={"name": "Sarah Ellis", "risk_score": 99.0, "flagged": True},
    )
    baseline = EntityProfile(
        ref="PRS-0000002", entity_type="Person", attributes={"name": "Sarah Ellis"}
    )
    assert compare(plain, loaded).score == compare(plain, baseline).score


@pytest.mark.parametrize("module", DECISION_MODULES)
def test_the_decision_path_does_not_import_the_evaluation_harness(module: str) -> None:
    """The harness holds the answers. The import must stay one-way."""
    tree = ast.parse((RESOLUTION_DIR / module).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)
    assert not any("evaluation" in name for name in imported), sorted(imported)


@pytest.mark.parametrize("module", DECISION_MODULES)
def test_the_decision_path_never_mentions_a_ground_truth_field(module: str) -> None:
    """Source-text assertion on purpose. A behavioural check would pass again
    the moment the field was reintroduced."""
    source = (RESOLUTION_DIR / module).read_text(encoding="utf-8")
    code_lines = [
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    ]
    body = "\n".join(code_lines)
    # `profile.py` names them once, in the comment listing what is banned —
    # comments are stripped above, so any remaining mention is real code.
    for forbidden in ("storyline_id", "flagged", "risk_score"):
        assert forbidden not in body, f"{module} references {forbidden}"
