"""The boundary between links the generator planted and links ARGUS discovered.

Phase 5 had to keep a *score* away from the scorer. Correlation has the harder
version of the same problem: this graph is full of edges that join exactly the
entities a storyline created together.

  * `INVOLVES` joins an `Incident` to every entity its storyline named.
  * `LINKED_TO` does the same from the `Case` side, and the generator's case
    seeder builds cases directly from storylines.
  * `CONTROLS` (24 edges in the live graph) and `SHARES_DEVICE` (2) have no
    baseline population whatsoever.

A dimension reading any of those would post a near-perfect precision figure and
would have discovered nothing at all — it would be the answer key, traversed.

These tests assert the separation by inspecting code rather than by trusting a
reading of it, and they are deliberately blunt: they read source text and fail
on a substring. A subtler test would be easier to satisfy by accident, and this
is the one property of the phase that must not be satisfiable by accident.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from app.correlation import candidates, clustering, dimensions, linking, measures, model
from app.correlation import evidence as evidence_module
from app.correlation.dimensions import DIMENSIONS
from app.correlation.evidence import ADMISSIBLE_INPUTS
from app.correlation.projection import SPECS
from app.integrity import ALL_INADMISSIBLE_TOKENS
from app.repositories import correlation_graph_repo

CORRELATION_PACKAGE = Path(inspect.getfile(evidence_module)).parent

# The functions on the correlation path. Ground truth is fetched by a separate
# function, listed nowhere here, and called only by the evaluation service.
CORRELATION_PATH = (
    correlation_graph_repo.fetch_correlation_evidence,
    correlation_graph_repo.project_clusters,
    correlation_graph_repo.clear_cluster_projection,
)


def _code_without_prose(path: Path) -> str:
    """The module's executable content, with comments and docstrings removed.

    Prose has to be excluded because the prohibition is *explained* in prose all
    over this package — the docstrings name the forbidden edges in order to say
    why they are forbidden. What must not appear is a reference: an identifier,
    an attribute, or a string that could reach the database.
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


def _function_code(function) -> str:
    """One function's body with its docstring removed.

    Needed because several of these functions explain in prose exactly which
    forbidden thing they used to read, and a substring search over the raw
    source would match the explanation and fail.
    """
    tree = ast.parse(inspect.getsource(function).lstrip())
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list):
            continue
        node.body = [  # type: ignore[attr-defined]
            statement
            for statement in body
            if not (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            )
        ] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree))


# A bare substring search cannot tell a *reference* from an *explanation*. Both
# of these appear in this codebase and only one is a violation:
#
#     WHERE any(r IN rels WHERE r.flagged = true)      <- reads the answer key
#     "...two flagged shipments sharing one corridor"  <- explains a dimension
#
# The published rationales and projection caveats are prose that must be free to
# name what it forbids — a caveat saying "CONTROLS is excluded because every
# instance was planted" is the system being honest, and a scanner that failed
# the build for it would be pressure to delete the explanation.
#
# So the scan matches the forms in which a token can actually reach the
# database, and nothing else:
#
#     .TOKEN     a property read, in Cypher or Python
#     :TOKEN     a node label or relationship type in a Cypher pattern
#     "TOKEN"    the token exactly, as a string — a dict key or a parameter
#
# This is narrower than the substring search it replaces, and it is *not* a
# relaxation: every true positive the substring version caught is still caught,
# including the `r.flagged` filter that made this test necessary. What it stops
# doing is failing on `flagged_members`, `CaseStatus` and `'Case not found'` —
# ARGUS's own identifiers that merely contain the letters.
def _planted_references(code: str, tokens: tuple[str, ...]) -> list[str]:
    found: list[str] = []
    for token in tokens:
        pattern = re.compile(
            rf"""(?:
                    [.:]{re.escape(token)}\b     # property read, label, or rel type
                  | ["']{re.escape(token)}["']   # the token exactly, as a string
                )""",
            re.VERBOSE,
        )
        if pattern.search(code):
            found.append(token)
    return found


# ─────────────────────────────────────────────────────────────────────────────
# The scanner itself
#
# `_planted_references` is narrower than the substring search it replaced, so it
# needs its own evidence that nothing real slipped through the gap. These cases
# are the actual code that existed in this repository — the violations are
# quoted from the defect this phase fixed, and the false positives are quoted
# from the identifiers that made the substring version unusable.
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "snippet",
    [
        "WHERE any(r IN rels WHERE r.flagged = true)",       # the defect, verbatim
        "MATCH (s:Storyline) RETURN s.entity_ids",
        "MATCH (p:Person)-[:CONTROLS]->(o:Organization)",
        "MATCH (a)-[:SHARES_DEVICE]-(b)",
        "MATCH (i:Incident)-[:INVOLVES]->(n)",
        "RETURN n.risk_score AS score",
        "t.storyline_id AS storyline",
        "s.route_anomaly AS anomaly",
        "relationships = {'CONTROLS': {}}",
    ],
)
def test_the_scanner_catches_a_real_reference(snippet: str) -> None:
    assert _planted_references(snippet, ALL_INADMISSIBLE_TOKENS), (
        f"the scanner missed a genuine reference: {snippet!r}"
    )


@pytest.mark.parametrize(
    "snippet",
    [
        "flagged = [m for m in assessed if m['account_band'] == 'elevated']",
        "summary.sort(key=lambda c: c['flagged_members'])",
        "row['flagged_routes'] = flagged.get(row['region'], 0)",
        "class CaseStatus(StrEnum):",
        "priority: CasePriority = CasePriority.MEDIUM",
        "raise HTTPException(status_code=404, detail='Case not found')",
        "s.argus_band IN ['elevated', 'notable']",
    ],
)
def test_the_scanner_does_not_fire_on_argus_own_identifiers(snippet: str) -> None:
    """These are ARGUS's own names, computed from ARGUS's own assessments. A
    scanner that failed the build for them would be pressure to rename honest
    code, which is how a guard stops being taken seriously."""
    assert not _planted_references(snippet, ALL_INADMISSIBLE_TOKENS), (
        f"the scanner fired on ARGUS's own identifier: {snippet!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Declared inputs
# ─────────────────────────────────────────────────────────────────────────────


def test_every_dimension_declares_only_admissible_inputs() -> None:
    for definition in DIMENSIONS:
        undeclared = set(definition.reads) - ADMISSIBLE_INPUTS
        assert not undeclared, (
            f"dimension {definition.dimension_id!r} reads {sorted(undeclared)}, which is not "
            f"on the admissibility whitelist in correlation/evidence.py"
        )


def test_every_dimension_declares_something() -> None:
    """A dimension with no declared inputs would pass the check above
    vacuously."""
    for definition in DIMENSIONS:
        assert definition.reads, f"dimension {definition.dimension_id!r} declares no inputs"


def test_the_whitelist_names_no_planted_structure() -> None:
    for entry in ADMISSIBLE_INPUTS:
        for token in ALL_INADMISSIBLE_TOKENS:
            assert token not in entry, f"admissible input {entry!r} names {token!r}"


# ─────────────────────────────────────────────────────────────────────────────
# The queries
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("function", CORRELATION_PATH, ids=lambda f: f.__name__)
def test_no_correlation_query_mentions_a_planted_link(function) -> None:
    found = _planted_references(_function_code(function), ALL_INADMISSIBLE_TOKENS)
    assert not found, (
        f"{function.__name__} references {found}. Even reading one in order to filter it "
        f"out is forbidden: the guarantee is that no code path exists, not that one is "
        f"guarded."
    )


def test_the_correlation_package_never_names_a_planted_link() -> None:
    """Applies to the whole package, including modules added later.

    `evaluation.py` is excluded and checked separately below — what makes ground
    truth acceptable there is that it measures and cannot score.
    """
    for path in sorted(CORRELATION_PACKAGE.glob("*.py")):
        if path.name == "evaluation.py":
            continue
        found = _planted_references(_code_without_prose(path), ALL_INADMISSIBLE_TOKENS)
        assert not found, f"{path.name} references planted structure {found}"


def test_only_evaluation_may_speak_of_storylines() -> None:
    """The one module permitted to know ground truth exists.

    Checked rather than exempted: it must measure, and it must be structurally
    incapable of producing a link.
    """
    text = (CORRELATION_PACKAGE / "evaluation.py").read_text()
    assert "storyline" in text.lower(), "evaluation.py is expected to reference ground truth"
    for forbidden in ("def link_pair", "def build_context", "CorrelationContext"):
        assert forbidden not in text, (
            f"evaluation.py contains {forbidden!r} — the module that reads labels must not "
            f"also be able to produce a link"
        )


def test_the_evidence_types_have_nowhere_to_carry_a_planted_link() -> None:
    """Structural, not procedural: even a careless future edit to a query could
    not smuggle a planted edge through, because no evidence type has a field
    that would hold one."""
    from dataclasses import fields

    from app.correlation.evidence import (
        Affiliation,
        Anchor,
        Attendance,
        CorrelationEvidence,
        DeviceContact,
        Place,
        Transfer,
    )

    for kind in (
        Transfer,
        DeviceContact,
        Attendance,
        Affiliation,
        Place,
        Anchor,
        CorrelationEvidence,
    ):
        names = {f.name for f in fields(kind)}
        for token in ALL_INADMISSIBLE_TOKENS:
            assert not any(token.lower() in name for name in names), (
                f"{kind.__name__} has a field that could carry {token!r}"
            )


def test_the_affiliation_type_cannot_express_control() -> None:
    """`CONTROLS` is the tie the shell-company storyline invents. `Affiliation`
    carries a `kind`, so the guarantee is about the values that reach it — and
    the only two writers of that field are named here."""
    source = _code_without_prose(Path(inspect.getfile(correlation_graph_repo)))
    assert "'DIRECTS', 'EMPLOYED_BY'" in source, (
        "the only two relationship types written into an Affiliation must be visible here"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Projections
# ─────────────────────────────────────────────────────────────────────────────


def test_no_projection_includes_a_planted_relationship() -> None:
    """A centrality score computed over `CONTROLS` would be ranking the answer
    key, and it would look like the best result the system had ever produced."""
    for spec in SPECS.values():
        for relationship in spec.relationships:
            assert relationship.rel_type not in ALL_INADMISSIBLE_TOKENS, (
                f"projection {spec.name!r} includes {relationship.rel_type!r}"
            )
        for label in spec.node_labels:
            assert label not in ALL_INADMISSIBLE_TOKENS


def test_every_projection_states_what_it_cannot_answer() -> None:
    """The most misleading thing about a graph metric is usually the part of the
    world the graph left out."""
    for spec in SPECS.values():
        assert spec.caveats, f"projection {spec.name!r} publishes no caveats"
        assert spec.description


def test_a_projection_fingerprint_changes_when_its_weights_do() -> None:
    from dataclasses import replace

    from app.correlation.projection import ENTITY

    original = ENTITY.fingerprint()
    heavier = replace(
        ENTITY,
        relationships=tuple(
            replace(r, weight=r.weight * 2) for r in ENTITY.relationships
        ),
    )
    assert heavier.fingerprint() != original


# ─────────────────────────────────────────────────────────────────────────────
# Imports
# ─────────────────────────────────────────────────────────────────────────────


def _imported_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_correlator_does_not_import_the_evaluation_module() -> None:
    """An import is a path. There must not be one from the correlator to the
    labels.

    Checked against the import graph rather than the file text, because
    "evaluation" appears throughout the package in its ordinary sense: a
    dimension is *evaluated* for a pair, which has nothing to do with measuring
    the model.
    """
    for module in (dimensions, linking, candidates, clustering, measures, model):
        imports = _imported_modules(Path(inspect.getfile(module)))
        offending = {name for name in imports if "correlation.evaluation" in name}
        assert not offending, f"{module.__name__} imports {sorted(offending)}"


def test_the_model_fingerprint_covers_the_dimension_registry() -> None:
    """Adding or removing a dimension changes what a strength of 0.7 means just
    as surely as moving a threshold does. A fingerprint that missed it would
    certify two different models as the same one."""
    from dataclasses import replace

    from app.correlation.model import default_model

    baseline = default_model()
    moved = replace(baseline, min_strength=baseline.min_strength + 0.01)
    assert moved.fingerprint() != baseline.fingerprint()


# ─────────────────────────────────────────────────────────────────────────────
# The application-wide boundary
# ─────────────────────────────────────────────────────────────────────────────

# Modules permitted to name the generator's planted structure, and why.
#
# Every entry is a debt with an owner, not an exemption. The rule is that a
# surface may *display* a generator claim clearly labelled as the source's own —
# the pattern Phase 2 established and Phase 5 applied to `risk_score` — but no
# derived-intelligence path may consult one.
#
#   integrity, assessment, correlation
#       the isolation machinery, which must name what it forbids.
#   provenance
#       records generator claims as claims, rated F6. Preserving and labelling
#       them is the entire point.
#   resolution
#       the matcher's own exclusion list, from Phase 4.
#   alert_repo, alerts route, dashboard_repo
#       `Incident` is still the alert source. Phase 7 replaces it with a real
#       Alert entity; until then these read the generator's incidents because
#       there is nothing else to read, and the roadmap records it.
#   case_repo, cases route, entity_labels
#       `Case` and `Storyline` are browsable entity types in their own right,
#       and the cases route names `Case` as an audit resource type. Displaying
#       or auditing a storyline-seeded record is not the same as scoring from
#       one — what matters is that no intelligence path consults it.
#   entity_repo, timeline_repo
#       surface `flagged` on transactions and communications as a
#       source-reported attribute. Phase 8 owns relabelling these as claims.
#   migrations/runner
#       names node labels in order to create constraints on them.
PERMITTED_TO_NAME_PLANTED_STRUCTURE = (
    "app/integrity.py",
    "app/assessment/",
    "app/correlation/",
    "app/services/provenance.py",
    "app/repositories/provenance_repo.py",
    "app/api/routes/provenance.py",
    "app/resolution/",
    "app/repositories/assessment_graph_repo.py",
    "app/repositories/correlation_graph_repo.py",
    "app/repositories/resolution_graph_repo.py",
    "app/repositories/alert_repo.py",
    "app/api/routes/alerts.py",
    "app/repositories/dashboard_repo.py",
    "app/repositories/case_repo.py",
    "app/api/routes/cases.py",
    "app/repositories/entity_labels.py",
    "app/repositories/entity_repo.py",
    "app/repositories/timeline_repo.py",
    "app/database/migrations/runner.py",
)


def test_no_unlisted_module_reads_planted_structure() -> None:
    """The allowlist above is the whole of the debt, and it must not grow silently.

    This is the check that would have caught the defect this phase fixed:
    `analytics_repo.run_cycle_detection` began `WHERE any(r IN rels WHERE
    r.flagged = true)`, so it was not finding laundering rings — it was
    filtering the graph down to the rings the generator had already labelled and
    reporting them as a discovery.
    """
    backend = CORRELATION_PACKAGE.parent.parent
    offenders: list[str] = []

    for path in sorted(backend.rglob("*.py")):
        relative = path.relative_to(backend).as_posix()
        if not relative.startswith("app/"):
            continue
        if any(relative.startswith(allowed) for allowed in PERMITTED_TO_NAME_PLANTED_STRUCTURE):
            continue
        for token in _planted_references(_code_without_prose(path), ALL_INADMISSIBLE_TOKENS):
            offenders.append(f"{relative}: {token}")

    assert not offenders, (
        "these modules reference the scenario generator's planted structure without being "
        "listed as permitted to:\n  " + "\n  ".join(offenders)
    )


def test_the_allowlist_contains_no_dead_entries() -> None:
    """An allowlist that outlives the debt it documents stops being a record and
    becomes cover. Each entry must still correspond to something real."""
    backend = CORRELATION_PACKAGE.parent.parent
    missing = [
        entry
        for entry in PERMITTED_TO_NAME_PLANTED_STRUCTURE
        if not (backend / entry).exists()
    ]
    assert not missing, f"allowlist names paths that no longer exist: {missing}"


def test_the_analytics_cycle_detector_no_longer_filters_on_the_answer_key() -> None:
    """Named explicitly, because this was a real defect rather than a
    hypothetical one, and a regression here would be invisible: the query would
    keep returning cycles, and every one of them would still be a planted one."""
    from app.repositories import analytics_repo

    source = _function_code(analytics_repo.run_cycle_detection)
    assert not _planted_references(source, ALL_INADMISSIBLE_TOKENS)
    assert "min_retention" in source, (
        "the detector must select cycles on value preservation, which is the property "
        "that distinguishes a laundering ring from an accounting coincidence"
    )


# ─────────────────────────────────────────────────────────────────────────────
# How a projection is built
# ─────────────────────────────────────────────────────────────────────────────


def test_a_projection_includes_nodes_with_no_relationships() -> None:
    """Otherwise the graph would silently exclude one node in seven of the
    entity projection — 1,321 of 8,750 on the live data, mostly people with no
    account, device or employer. A centrality of zero and an absence from the
    graph are different statements, and only one of them is true of those
    subjects."""
    from app.correlation.projection import ENTITY, MONEY, _projection_query

    for spec in (MONEY, ENTITY):
        query = _projection_query(spec)
        assert "null AS target" in query, (
            f"projection {spec.name!r} emits no isolated nodes"
        )
        assert "NOT (n)-[:" in query


def test_an_undirected_relationship_is_projected_both_ways() -> None:
    from app.correlation.projection import ENTITY, MONEY, _projection_query

    entity = _projection_query(ENTITY)
    assert entity.count("'OWNS_ACCOUNT' AS relType") == 2, "undirected must emit both directions"

    # Direction is kept where it carries meaning: who paid whom is the asymmetry
    # that makes a layering chain visible.
    money = _projection_query(MONEY)
    assert money.count("'TRANSACTED_WITH' AS relType") == 1


def test_a_flat_weight_is_computed_rather_than_read_from_the_graph() -> None:
    """GDS rejects a `defaultValue` for a property that exists nowhere —
    `Relationship properties not found: 'argus_weight'` — so the weight has to
    be produced by the query. Writing it onto 60,000 relationships instead would
    make the correlator's own configuration part of the world it reads from."""
    from app.correlation.projection import ENTITY, _projection_query

    query = _projection_query(ENTITY)
    assert "3.0 AS weight" in query
    assert "r.argus_weight" not in query


def test_the_money_projection_still_weights_by_amount() -> None:
    from app.correlation.projection import MONEY, _projection_query

    assert "r.amount AS weight" in _projection_query(MONEY)


def test_a_projection_query_is_built_only_from_the_frozen_registry() -> None:
    """Relationship types and labels cannot be Cypher parameters, so they are
    interpolated. This asserts the only source of those strings is the registry
    in this module, and that `spec_for` refuses anything else."""
    import pytest as _pytest

    from app.correlation.projection import SPECS, spec_for

    for name, spec in SPECS.items():
        assert spec_for(name) is spec
    with _pytest.raises(ValueError, match="unknown projection"):
        spec_for("'; CALL db.labels() //")
