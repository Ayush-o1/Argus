"""The boundary that stops alerts becoming the answer key again.

Before this phase, `GET /api/alerts` was a severity filter over `Incident`
nodes — one written by the generator per storyline, summarising the storyline
it had just planted. Every alert was correct and none of them was found.

`Incident` has been on the inadmissible list since Phase 5; the alert path was
simply never held to it. These tests hold it, by inspecting code rather than by
trusting a reading of it, and they are deliberately blunt for the same reason
the correlation ones are: this is the property that must not be satisfiable by
accident.

The scan reuses `_planted_references` — matching the forms in which a token can
actually reach a database, not every occurrence of the letters — so prose in
this package remains free to name what it forbids.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from app.alerting import evaluation, identity, lifecycle, priority, rules, suppression
from app.alerting import evidence as evidence_module
from app.alerting.evidence import ADMISSIBLE_INPUTS
from app.alerting.rules import RULES
from app.integrity import ALL_INADMISSIBLE_TOKENS
from app.repositories import alert_findings_repo, alert_repo

ALERTING_PACKAGE = Path(inspect.getfile(evidence_module)).parent

# Modules on the alerting path. The evaluation *service* reads ground truth via
# the correlation graph repository; that function is listed nowhere here and is
# called only after alerting has finished.
ALERTING_MODULES = (evidence_module, rules, identity, priority, lifecycle, suppression, evaluation)


def _code_without_prose(path: Path) -> str:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        kept = [
            statement
            for statement in body
            if not (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            )
        ]
        node.body = kept or [ast.Pass()]  # type: ignore[attr-defined]
    return ast.unparse(ast.fix_missing_locations(tree))


def _planted_references(code: str, tokens: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for token in tokens:
        pattern = re.compile(
            rf"""(?:
                    [.:]{re.escape(token)}\b
                  | ["']{re.escape(token)}["']
                )""",
            re.VERBOSE,
        )
        if pattern.search(code):
            found.append(token)
    return found


# ── the package may not reference the plant ──────────────────────────────────


@pytest.mark.parametrize("path", sorted(ALERTING_PACKAGE.glob("*.py")), ids=lambda p: p.name)
def test_alerting_package_never_references_planted_data(path: Path) -> None:
    found = _planted_references(_code_without_prose(path), ALL_INADMISSIBLE_TOKENS)
    assert not found, (
        f"{path.name} references generator-planted data: {found}. "
        "An alert derived from the answer key is the defect this phase removed."
    )


@pytest.mark.parametrize(
    "module",
    [alert_findings_repo, alert_repo],
    ids=lambda m: m.__name__.rsplit(".", 1)[-1],
)
def test_alert_repositories_never_reference_planted_data(module) -> None:
    """The repositories are where a query could actually reach `Incident`.

    `alert_findings_repo` reads only ARGUS's own published findings, and
    `alert_repo` only the alerting tables. Neither may join to a planted node.
    """
    found = _planted_references(_code_without_prose(Path(inspect.getfile(module))), ALL_INADMISSIBLE_TOKENS)
    assert not found, f"{module.__name__} references generator-planted data: {found}"


def test_alerts_route_never_references_planted_data() -> None:
    """The route is the surface that used to *be* the violation."""
    from app.api.routes import alerts as alerts_route

    found = _planted_references(
        _code_without_prose(Path(inspect.getfile(alerts_route))), ALL_INADMISSIBLE_TOKENS
    )
    assert not found, f"alerts route references generator-planted data: {found}"


def test_alerting_package_issues_no_cypher() -> None:
    """No module in the package may talk to the graph at all.

    Alerting reads ARGUS's own findings from PostgreSQL. A Cypher query here
    would be a second, unreviewed route to the graph — which is exactly how the
    old implementation reached `Incident`.
    """
    for path in sorted(ALERTING_PACKAGE.glob("*.py")):
        code = _code_without_prose(path)
        for marker in ("MATCH (", "MERGE (", "driver.session", "AsyncDriver"):
            assert marker not in code, f"{path.name} contains {marker!r}: alerting must not query the graph"


# ── rules declare what they read, and it is checked ──────────────────────────


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.rule_id)
def test_every_rule_reads_only_admissible_inputs(rule) -> None:
    undeclared = rule.reads - ADMISSIBLE_INPUTS
    assert not undeclared, (
        f"{rule.rule_id} declares inputs outside the admissible set: {sorted(undeclared)}"
    )


@pytest.mark.parametrize("rule", RULES, ids=lambda r: r.rule_id)
def test_every_rule_states_what_would_make_it_wrong(rule) -> None:
    """A rule with no falsifying condition cannot be tuned or retired."""
    assert len(rule.would_be_wrong_if.strip()) > 40, f"{rule.rule_id} has no meaningful falsifier"
    assert len(rule.means.strip()) > 40, f"{rule.rule_id} does not say what a firing means"


def test_rule_ids_and_versions_are_unique() -> None:
    seen = [(r.rule_id, r.version) for r in RULES]
    assert len(set(seen)) == len(seen), "two rules share an id and version; dedup keys would collide"


def test_admissible_inputs_are_all_derived_findings() -> None:
    """Every admissible input names an ARGUS output, not a graph attribute.

    The prefix is the check: alerting consumes assessments, signals, links and
    clusters. Anything else would mean a rule reading the world directly, which
    is assessment's job and not alerting's.
    """
    allowed_prefixes = ("assessment.", "assessment_signal.", "correlation_link.", "correlation_cluster.")
    for item in ADMISSIBLE_INPUTS:
        assert item.startswith(allowed_prefixes), f"{item} is not a derived ARGUS finding"


# ── the scanner itself still catches real violations ─────────────────────────


@pytest.mark.parametrize(
    "snippet",
    [
        'MATCH (i:Incident) WHERE i.severity IN ["High"]',
        "row.risk_score > 80",
        'alert["storyline_id"]',
        "MATCH (a)-[:CONTROLS]->(b)",
        'WHERE r.flagged = true',
        'MATCH (c:Case)-[:LINKED_TO]->(e)',
        "node.community_ids",
        'params["Storyline"]',
    ],
)
def test_scanner_catches_real_violations(snippet: str) -> None:
    assert _planted_references(snippet, ALL_INADMISSIBLE_TOKENS), (
        f"scanner missed a genuine violation: {snippet!r}"
    )


@pytest.mark.parametrize(
    "snippet",
    [
        "flagged_members = 0",
        "class CaseStatus:",
        'raise HTTPException(404, "Case not found")',
        "incident_count = 0",
        "storyline_types_note = 'prose'",
    ],
)
def test_scanner_does_not_fire_on_argus_own_identifiers(snippet: str) -> None:
    """The narrowing must not be a relaxation in disguise, nor a source of
    false positives that would pressure someone to delete an explanation."""
    assert not _planted_references(snippet, ALL_INADMISSIBLE_TOKENS), (
        f"scanner fired on ARGUS's own identifier: {snippet!r}"
    )
