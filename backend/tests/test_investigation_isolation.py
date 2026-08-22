"""The boundary between what an analyst concluded and what the generator planted.

Every `Case` node in this world was written by the scenario generator from its
own storylines: titled after the storyline, noted "Auto-seeded from storyline
STL-…", linked to exactly the entity list the storyline planted, and assigned to
one of five invented analyst names. Twenty of twenty. Zero were opened by a
person.

That makes the case surface the most dangerous place in ARGUS for the G-08
family of defect. Elsewhere the answer key is presented as a machine finding,
which is bad; here it would be presented as **human judgement**, which is worse,
because a reader has no way to discount it.

So investigations are a separate object in PostgreSQL, and these tests assert —
by inspecting code rather than trusting a reading of it — that nothing on the
investigation path can reach the graph's planted cases at all.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from app.integrity import ALL_INADMISSIBLE_TOKENS
from app.investigation import history, lifecycle, outcomes
from app.repositories import investigation_repo

INVESTIGATION_PACKAGE = Path(inspect.getfile(outcomes)).parent


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
    """Matches the forms in which a token can actually reach a database.

    `.token`, `:token` and `"token"` — a property access, a Cypher label or
    relationship type, and a string literal. Not every occurrence of the
    letters, so prose in these modules stays free to name what it forbids, as
    this file's own docstring does.
    """
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


@pytest.mark.parametrize(
    "path", sorted(INVESTIGATION_PACKAGE.glob("*.py")), ids=lambda p: p.name
)
def test_investigation_package_never_references_planted_data(path: Path) -> None:
    found = _planted_references(_code_without_prose(path), ALL_INADMISSIBLE_TOKENS)
    assert not found, (
        f"{path.name} references generator-planted data: {found}. An investigation "
        "surface that reads the answer key presents it as human judgement."
    )


def test_the_investigation_repository_never_references_planted_data() -> None:
    """The repository is where a query could actually reach a planted `Case`."""
    found = _planted_references(
        _code_without_prose(Path(inspect.getfile(investigation_repo))),
        ALL_INADMISSIBLE_TOKENS,
    )
    assert not found, f"investigation_repo references generator-planted data: {found}"


def test_the_investigations_route_never_references_planted_data() -> None:
    from app.api.routes import investigations as route

    found = _planted_references(
        _code_without_prose(Path(inspect.getfile(route))), ALL_INADMISSIBLE_TOKENS
    )
    assert not found, f"investigations route references generator-planted data: {found}"


def test_the_investigation_path_issues_no_cypher() -> None:
    """Nothing on this path may talk to the graph.

    An investigation records a judgement about ARGUS's own findings, which live
    in PostgreSQL. A Cypher query here would be a second, unreviewed route to a
    store that also holds twenty generator-authored cases — and the whole point
    of building this object separately is that the two can never be confused.
    """
    paths = [*INVESTIGATION_PACKAGE.glob("*.py"), Path(inspect.getfile(investigation_repo))]
    for path in paths:
        code = _code_without_prose(path)
        for marker in ("MATCH (", "MERGE (", "driver.session", "AsyncDriver"):
            assert marker not in code, (
                f"{path.name} contains {marker!r}: the investigation path must not query the graph"
            )


def test_nothing_here_writes_to_the_machine_assessment(monkeypatch) -> None:
    """G-15's central guarantee, asserted against the SQL rather than the intent.

    An analyst's judgement sits beside the model's and never replaces it. If any
    statement in this module wrote to `assessments` or `assessment_current`, the
    dissent record would become an overwrite — and a reader would lose the one
    thing that makes it valuable, which is being able to see that two people
    disagree.
    """
    source = Path(inspect.getfile(investigation_repo)).read_text()
    statements = re.findall(r'"""\s*\n?\s*((?:UPDATE|INSERT|DELETE)[^"]*)"""', source)
    for statement in statements:
        collapsed = " ".join(statement.split()).upper()
        for table in ("ASSESSMENTS", "ASSESSMENT_CURRENT"):
            assert f"INTO {table}" not in collapsed, f"writes to {table}: {collapsed[:80]}"
            assert f"UPDATE {table}" not in collapsed, f"writes to {table}: {collapsed[:80]}"
            assert f"FROM {table} WHERE" not in collapsed or "SELECT" in collapsed


def test_the_modules_that_matter_are_actually_covered() -> None:
    """A scan over an empty file set passes vacuously.

    The correlation and alerting isolation suites both carry a check like this,
    for the same reason: the failure mode of a code scan is that it silently
    stops looking at anything.
    """
    scanned = {p.name for p in INVESTIGATION_PACKAGE.glob("*.py")}
    assert {"outcomes.py", "lifecycle.py", "history.py"} <= scanned
    assert history and lifecycle and outcomes
