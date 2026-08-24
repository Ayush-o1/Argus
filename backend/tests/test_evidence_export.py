"""The four export renderers, against one shared fixture investigation.

json is for a machine and already gets exercised by parsing it back. html,
markdown and pdf are three renderings for a person; there is no framework
that hands back "did this look right" for any of the three, so each is
checked for the structural properties that actually matter: markdown parses
as the sections it claims to have and doesn't leak raw Markdown syntax from
user-authored text, and pdf is bytes reportlab actually produced (a real PDF
header and trailer) rather than a placeholder.
"""

from __future__ import annotations

import json

from app.evidence.export import render_html, render_json, render_markdown, render_pdf

CONCLUDED = {
    "inv_ref": "INV-0000042",
    "title": "Shell network around * flagged account_1",
    "opened_by": "n.iyer",
    "opened_at": "2026-01-05T09:00:00+00:00",
    "classification": "confidential",
    "hypothesis": "Three accounts route funds through a common controller.",
    "confidence": "moderate",
    "confidence_basis": "Two independent transaction clusters, no direct admission.",
    "outcome": "confirmed",
    "outcome_rationale": "Correlation held after the third account was added.",
    "closed_by": "s.rao",
    "closed_at": "2026-02-01T12:00:00+00:00",
    "findings": [
        {
            "statement": "Account_1 and Account_2 share a device fingerprint.",
            "confidence": "high",
            "author_username": "n.iyer",
            "author_role": "investigator",
            "recorded_at": "2026-01-06T10:00:00+00:00",
            "cites": ["ACC-0001", "ACC-0002"],
            "withdrawn_at": None,
            "superseded_at": None,
        },
        {
            "statement": "[withdrawn] # not a heading, a literal finding statement",
            "confidence": "low",
            "author_username": "n.iyer",
            "author_role": "investigator",
            "recorded_at": "2026-01-07T10:00:00+00:00",
            "cites": [],
            "withdrawn_at": "2026-01-08T10:00:00+00:00",
            "withdrawal_reason": "Traced to a shared ISP, not shared control.",
            "superseded_at": None,
        },
    ],
    "entities": [
        {
            "entity_ref": "ACC-0001",
            "entity_type": "Account",
            "reason": "Named in the originating alert.",
            "removed_at": None,
        },
        {
            "entity_ref": "ACC-0003",
            "entity_type": "Account",
            "reason": "Added after correlation.",
            "removed_at": "2026-01-20T10:00:00+00:00",
            "removed_by": "s.rao",
            "removal_reason": "Correlation was coincidental proximity, not control.",
        },
    ],
    "analyst_assessments": [
        {
            "subject_ref": "ACC-0001",
            "machine_band": "elevated",
            "author_username": "n.iyer",
            "analyst_band": "elevated",
            "dissents": False,
            "rationale": "Agrees with the model's evidence coverage.",
        },
        {
            "subject_ref": "ACC-0003",
            "machine_band": "routine",
            "author_username": "s.rao",
            "analyst_band": "elevated",
            "dissents": True,
            "rationale": "Model has no view of the offline ledger entries.",
        },
    ],
    "reviews": [
        {
            "reviewer": "a.mehta",
            "reviewer_role": "supervisor",
            "concurs": True,
            "outcome_reviewed": "confirmed",
            "note": None,
        },
        {
            "reviewer": "k.das",
            "reviewer_role": "auditor",
            "concurs": False,
            "outcome_reviewed": "confirmed",
            "note": "Third account's link is weaker than the writeup implies.",
        },
    ],
}

UNCONCLUDED = {**CONCLUDED, "outcome": None, "outcome_rationale": None, "closed_by": None, "closed_at": None}

EVENTS = [
    {
        "occurred_at": "2026-01-05T09:00:00+00:00",
        "actor_username": "n.iyer",
        "event_type": "opened",
        "field": None,
        "new_value": None,
        "note": "Investigation opened from ALERT-0099.",
    },
    {
        "occurred_at": "2026-01-08T10:00:00+00:00",
        "actor_username": "n.iyer",
        "event_type": "finding_withdrawn",
        "field": "status",
        "new_value": "withdrawn",
        "note": None,
    },
]

KWARGS = {"requested_by": "n.iyer", "purpose": "Hand-off to the fraud desk"}


def test_json_round_trips_every_finding_and_event():
    payload = json.loads(render_json(CONCLUDED, EVENTS, **KWARGS))
    assert payload["investigation"]["inv_ref"] == "INV-0000042"
    assert len(payload["investigation"]["findings"]) == 2
    assert len(payload["history"]) == 2
    assert "synthetic dataset" in payload["export"]["content_note"]


def test_html_includes_the_classification_banner_and_every_section():
    out = render_html(CONCLUDED, EVENTS, **KWARGS).decode()
    assert "CONFIDENTIAL" in out
    assert "Hand-off to the fraud desk" in out
    assert "Account_1 and Account_2 share a device fingerprint" in out
    # The withdrawn finding is still present, marked, not deleted.
    assert "withdrawn" in out
    assert "Traced to a shared ISP" in out
    # The removed entity is still present, marked, not deleted.
    assert "removed</strong> by s.rao" in out
    # Both bands, never one number standing in for two judgements.
    assert "ARGUS assessed" in out and "s.rao assessed" in out


def test_html_states_no_outcome_plainly_rather_than_omitting_the_section():
    out = render_html(UNCONCLUDED, EVENTS, **KWARGS).decode()
    assert "has not been concluded" in out


def test_markdown_has_one_heading_per_section_and_survives_a_naive_parse():
    out = render_markdown(CONCLUDED, EVENTS, **KWARGS).decode()
    for heading in ("# Shell network", "## Hypothesis", "## Outcome", "## Findings", "## Evidence", "## History"):
        assert heading in out

    # A finding statement containing literal Markdown syntax must not be able
    # to inject a heading or break the list structure it's rendered inside.
    assert "\\[withdrawn\\] \\# not a heading" in out
    assert "\n# not a heading" not in out

    # The withdrawn finding is struck through, not deleted, and its reason survives.
    assert "~~" in out
    assert "Traced to a shared ISP" in out

    # History renders as an actual Markdown table: header, separator, one row per event.
    table_lines = [line for line in out.splitlines() if line.startswith("|")]
    assert len(table_lines) == 2 + len(EVENTS)


def test_markdown_states_no_outcome_plainly_rather_than_omitting_the_section():
    out = render_markdown(UNCONCLUDED, EVENTS, **KWARGS).decode()
    assert "has not been concluded" in out


def test_pdf_is_a_real_pdf_reportlab_actually_produced():
    out = render_pdf(CONCLUDED, EVENTS, **KWARGS)
    assert out.startswith(b"%PDF-")
    assert out.rstrip().endswith(b"%%EOF")
    # A meaningful multi-page-worthy document, not an empty shell — the
    # fixture has two findings, two entities, two assessments, two reviews
    # and a two-row history table, all drawn as real flowables.
    assert len(out) > 2000


def test_pdf_does_not_choke_on_an_unconcluded_investigation_or_empty_lists():
    empty = {
        **UNCONCLUDED,
        "findings": [],
        "entities": [],
        "analyst_assessments": [],
        "reviews": [],
    }
    out = render_pdf(empty, [], **KWARGS)
    assert out.startswith(b"%PDF-")


def test_markdown_does_not_choke_on_an_unconcluded_investigation_or_empty_lists():
    empty = {
        **UNCONCLUDED,
        "findings": [],
        "entities": [],
        "analyst_assessments": [],
        "reviews": [],
    }
    out = render_markdown(empty, [], **KWARGS).decode()
    assert "No findings recorded." in out
    assert "No evidence linked." in out
