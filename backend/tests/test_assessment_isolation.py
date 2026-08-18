"""The boundary between what the generator planted and what ARGUS discovered.

The audit's headline finding was that ARGUS displayed the scenario generator's
own answer key with the authority of an analytic conclusion. Phase 5 replaces
that number with one ARGUS derives — which is only worth anything if the
derivation genuinely cannot see the answer.

These tests assert that by inspecting the code rather than by trusting a
reading of it. They are deliberately blunt: they read source text and fail on a
substring. A subtler test would be easier to satisfy accidentally, and this is
the one property of this phase that must not be satisfiable by accident.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.assessment import evidence as evidence_module
from app.assessment import scoring, signals
from app.assessment.evidence import ADMISSIBLE_INPUTS, INADMISSIBLE_TOKENS
from app.assessment.signals import SIGNALS
from app.repositories import assessment_graph_repo

# The functions on the scoring path. Ground truth is fetched by a separate
# function, listed nowhere here, and called only by the evaluation service.
SCORING_PATH = (
    assessment_graph_repo.fetch_evidence,
    assessment_graph_repo.project_assessments,
    assessment_graph_repo.clear_projection,
    assessment_graph_repo.band_counts,
)

ASSESSMENT_PACKAGE = Path(inspect.getfile(evidence_module)).parent


def test_every_signal_declares_only_admissible_inputs() -> None:
    for signal in SIGNALS:
        undeclared = set(signal.reads) - ADMISSIBLE_INPUTS
        assert not undeclared, (
            f"signal {signal.signal_id!r} reads {sorted(undeclared)}, which is not on the "
            f"admissibility whitelist in evidence.py"
        )


def test_every_signal_declares_something() -> None:
    """A signal with no declared inputs would pass the check above vacuously."""
    for signal in SIGNALS:
        assert signal.reads, f"signal {signal.signal_id!r} declares no inputs"


@pytest.mark.parametrize("function", SCORING_PATH, ids=lambda f: f.__name__)
def test_no_scoring_query_mentions_an_answer_key(function) -> None:
    source = inspect.getsource(function)
    for token in INADMISSIBLE_TOKENS:
        assert token not in source, (
            f"{function.__name__} mentions {token!r}. Even reading it to filter it out is "
            f"forbidden: the guarantee is that no code path exists, not that one is guarded."
        )


def _code_without_prose(path: Path) -> str:
    """The module's executable content, with comments and docstrings removed.

    Prose has to be excluded, because the prohibition is explained in prose all
    over this package — the docstrings name the forbidden fields in order to say
    why they are forbidden. What must not appear is a *reference*: an
    identifier, an attribute, or a string that reaches the database.
    """
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


def test_the_assessment_package_never_names_an_answer_key() -> None:
    """Applies to the whole package, including modules added later.

    Nothing here is excluded any more except `evaluation.py`, which is checked
    by the test below instead. `evidence.py` used to be exempt because it
    *declared* the prohibition — a list of forbidden tokens is necessarily made
    of them. Phase 6 moved that declaration to `app/integrity.py` so both
    intelligence packages share one boundary, which as a side effect brought
    `evidence.py` under the same scan as everything else.
    """
    for path in sorted(ASSESSMENT_PACKAGE.glob("*.py")):
        if path.name == "evaluation.py":
            continue
        code = _code_without_prose(path)
        for token in INADMISSIBLE_TOKENS:
            assert token not in code, f"{path.name} references the answer key {token!r}"


def test_only_evaluation_may_speak_of_storylines() -> None:
    """`evaluation.py` is the one module permitted to know ground truth exists.

    It is checked separately rather than exempted, because what makes it
    acceptable there is that it measures — it must not score.
    """
    text = Path(inspect.getfile(__import__("app.assessment.evaluation", fromlist=["x"]))).read_text()
    assert "storyline" in text.lower(), "evaluation.py is expected to reference ground truth"
    for forbidden in ("def assess", "def build_context", "SignalContext"):
        assert forbidden not in text, (
            f"evaluation.py contains {forbidden!r} — the module that reads labels must not "
            f"also be able to produce a score"
        )


def test_the_evidence_bundle_has_nowhere_to_carry_a_label() -> None:
    """Structural, not procedural: even a careless future edit to the graph
    query could not smuggle a risk field through, because there is no field on
    any evidence type that would hold one."""
    from dataclasses import fields

    from app.assessment.evidence import (
        AccountFact,
        Contact,
        Directorship,
        EvidenceBundle,
        ShipmentFact,
        Transfer,
    )

    for kind in (Transfer, Contact, AccountFact, ShipmentFact, Directorship, EvidenceBundle):
        names = {f.name for f in fields(kind)}
        for token in INADMISSIBLE_TOKENS:
            assert not any(token.lower() in name for name in names), (
                f"{kind.__name__} has a field that could carry {token!r}"
            )


def test_the_projection_never_writes_to_the_generators_risk_score() -> None:
    """The generator's number stays exactly where it is.

    Overwriting it would destroy a source's claim — and provenance holds an
    assertion pointing at it, rated F6, which would then describe a value that
    no longer exists.
    """
    source = inspect.getsource(assessment_graph_repo)
    write_clauses = [
        line for line in source.splitlines() if "SET n." in line or "REMOVE n." in line
    ]
    assert write_clauses, "expected the projection to write something"
    for line in write_clauses:
        assert "argus_" in line, f"projection writes a non-argus property: {line.strip()!r}"


def test_projected_properties_are_enumerated() -> None:
    """So a future edit that adds a sixth property has to say so out loud."""
    source = inspect.getsource(assessment_graph_repo)
    for prop in assessment_graph_repo.PROJECTED_PROPERTIES:
        assert prop.startswith("argus_")
        assert prop in source


def test_the_matcher_still_cannot_see_the_assessment() -> None:
    """Phase 4's isolation, extended.

    An assessment is derived intelligence. Letting the entity matcher see it
    would make two records more likely to be judged the same person because
    ARGUS already thought both were interesting — which is the same circularity
    in a different place.
    """
    from app.resolution import profile

    source = inspect.getsource(profile)
    for prop in assessment_graph_repo.PROJECTED_PROPERTIES:
        assert prop not in source or f"# {prop}" in source

    allowed = set()
    for entity_type in profile.SUPPORTED_TYPES:
        allowed |= set(profile.allowed_source_keys(entity_type))
    for prop in assessment_graph_repo.PROJECTED_PROPERTIES:
        assert prop not in allowed, f"the matcher can see {prop}"


def _imported_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_scoring_and_signals_do_not_import_the_evaluation_module() -> None:
    """An import is a path. There must not be one from the scorer to the labels.

    Checked against the import graph rather than the file text, because the
    word "evaluation" appears throughout this package in its ordinary sense —
    a signal is *evaluated* for a subject, which has nothing to do with
    measuring the model.
    """
    for module in (scoring, signals):
        imports = _imported_modules(Path(inspect.getfile(module)))
        offending = {name for name in imports if "assessment.evaluation" in name}
        assert not offending, f"{module.__name__} imports {sorted(offending)}"


# ─────────────────────────────────────────────────────────────────────────────
# The regression that made this phase necessary
# ─────────────────────────────────────────────────────────────────────────────

# Modules permitted to name the generator's risk fields, and why:
#
#   provenance   — records the generator's score as a source's claim, rated F6.
#                  That is the whole point: the number is preserved and
#                  labelled rather than deleted.
#   assessment   — the isolation machinery, which must name what it forbids.
#   resolution   — the matcher's own exclusion list, from Phase 4.
#
# Everything else in the application must be unable to reach it. A surface that
# reads `risk_score` is a surface presenting the answer key as a finding, which
# is audit finding G-08 and the reason Phase 5 exists.
GENERATOR_RISK_FIELDS = ("risk_score", "risk_factors")

PERMITTED_TO_NAME_IT = (
    "app/integrity.py",
    "app/services/provenance.py",
    "app/repositories/provenance_repo.py",
    "app/api/routes/provenance.py",
    "app/assessment/",
    "app/resolution/",
    "app/repositories/assessment_graph_repo.py",
    "app/repositories/resolution_graph_repo.py",
)


def test_no_application_surface_reads_the_generators_risk_score() -> None:
    backend = ASSESSMENT_PACKAGE.parent.parent
    offenders: list[str] = []

    for path in sorted(backend.rglob("*.py")):
        relative = path.relative_to(backend).as_posix()
        if not relative.startswith("app/"):
            continue
        if any(relative.startswith(allowed) for allowed in PERMITTED_TO_NAME_IT):
            continue
        code = _code_without_prose(path)
        for field in GENERATOR_RISK_FIELDS:
            if field in code:
                offenders.append(f"{relative}: {field}")

    assert not offenders, (
        "these modules read the scenario generator's planted risk fields:\n  "
        + "\n  ".join(offenders)
    )
