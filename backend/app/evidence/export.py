"""Rendering an investigation into something that can leave the system.

Two formats from one snapshot, in one request, so a JSON export and an HTML
export of the same investigation can never describe different states of it.

## What "watermarked" means here, and what it does not

The audit asks for watermarked export. What is implemented is a **visible
classification banner** at the head and foot of the human-readable document,
plus a provenance footer naming who produced it, when, and under what purpose.

It is not a steganographic mark and it does not survive retyping, screenshotting
or copy-paste. Saying so matters: a visible banner tells a recipient how to
handle a document, which is what a handling caveat is for. It does not identify
who leaked it, and a system that called this "watermarking" without
qualification would be claiming a forensic property it does not have.

Tracing a leak back to a recipient needs a per-recipient variation embedded in
the content, and that is a different feature with a different threat model. It
is not built, and it is listed as not built.

## What is included, and one thing that is not

Everything an investigation holds: hypothesis, confidence and its basis, every
finding including the withdrawn and superseded ones, evidence links including
the removed ones with who removed them, every review, the outcome, and the full
event history.

**The analyst assessments are included but the machine's bands are labelled as
the machine's.** An export that showed one band per subject without saying which
of the two it was would recreate, on paper, exactly the confusion this system
spent nine phases removing from the screen.
"""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from typing import Any

from app.evidence.classification import classification_by_code

__all__ = ["render_html", "render_json"]


def _scalar(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict | list):
        return value
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return _scalar(obj)


def render_json(
    investigation: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    requested_by: str,
    purpose: str,
) -> bytes:
    """The machine-readable export.

    The provenance block is part of the document rather than a separate
    manifest, so a file that has been moved, renamed or forwarded still carries
    what it is and where it came from.
    """
    payload = {
        "export": {
            "produced_at": datetime.now(UTC).isoformat(),
            "produced_by": requested_by,
            "purpose": purpose,
            "classification": investigation.get("classification"),
            "handling": classification_by_code(investigation.get("classification", "internal")).handling,
            "source_system": "ARGUS",
            "content_note": (
                "Derived from a synthetic dataset. Nothing in this document is a "
                "record of a real person, organisation or event."
            ),
        },
        "investigation": _clean({k: v for k, v in investigation.items() if k != "events"}),
        "history": _clean(events),
    }
    return json.dumps(payload, indent=2, sort_keys=False).encode("utf-8")


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _section(title: str, body: str) -> str:
    return f"<section><h2>{_e(title)}</h2>{body}</section>"


def render_html(
    investigation: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    requested_by: str,
    purpose: str,
) -> bytes:
    """The human-readable export, with its classification stated on the page."""
    code = investigation.get("classification", "internal")
    level = classification_by_code(code)
    produced = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    banner = f'<div class="banner">{_e(level.label.upper())}<span class="handling">{_e(level.handling)}</span></div>'

    findings = (
        "".join(
            f'<li class="{"retired" if (f.get("withdrawn_at") or f.get("superseded_at")) else ""}">'
            f"<p>{_e(f.get('statement'))}</p>"
            f'<p class="meta">confidence {_e(f.get("confidence"))} · '
            f"{_e(f.get('author_username'))} ({_e(f.get('author_role'))}) · "
            f"{_e(f.get('recorded_at'))}"
            + (f" · <strong>withdrawn</strong>: {_e(f.get('withdrawal_reason'))}" if f.get("withdrawn_at") else "")
            + (" · <strong>superseded</strong>" if f.get("superseded_at") else "")
            + f'</p><p class="cites">cites: {_e(", ".join(f.get("cites") or []))}</p></li>'
            for f in investigation.get("findings", [])
        )
        or "<li>No findings recorded.</li>"
    )

    entities = (
        "".join(
            f"<li>{_e(e.get('entity_ref'))} ({_e(e.get('entity_type'))}) — {_e(e.get('reason'))}"
            + (
                f" · <strong>removed</strong> by {_e(e.get('removed_by'))}: {_e(e.get('removal_reason'))}"
                if e.get("removed_at")
                else ""
            )
            + "</li>"
            for e in investigation.get("entities", [])
        )
        or "<li>No evidence linked.</li>"
    )

    # Both bands, always labelled. An export that printed one number per subject
    # would put back on paper the ambiguity the assessment surface removed.
    assessments = "".join(
        f"<li>{_e(a.get('subject_ref'))} — ARGUS assessed "
        f"<strong>{_e(a.get('machine_band') or 'not assessed')}</strong>; "
        f"{_e(a.get('author_username'))} assessed <strong>{_e(a.get('analyst_band'))}</strong>"
        + (" <em>(disagreement)</em>" if a.get("dissents") else "")
        + f'<p class="meta">{_e(a.get("rationale"))}</p></li>'
        for a in investigation.get("analyst_assessments", [])
    )

    reviews = "".join(
        f"<li>{_e(r.get('reviewer'))} ({_e(r.get('reviewer_role'))}) "
        f"{'concurs with' if r.get('concurs') else '<strong>does not concur with</strong>'} "
        f"{_e(r.get('outcome_reviewed'))}"
        + (f'<p class="meta">{_e(r.get("note"))}</p>' if r.get("note") else "")
        + "</li>"
        for r in investigation.get("reviews", [])
    )

    history = "".join(
        f"<tr><td>{_e(ev.get('occurred_at'))}</td><td>{_e(ev.get('actor_username'))}</td>"
        f"<td>{_e(ev.get('field') or ev.get('event_type'))}</td>"
        f"<td>{_e(json.dumps(ev.get('new_value')) if ev.get('field') else (ev.get('note') or ''))}</td></tr>"
        for ev in events
    )

    body = f"""{banner}
<header>
  <h1>{_e(investigation.get("title"))}</h1>
  <p class="ref">{_e(investigation.get("inv_ref"))} · opened by {_e(investigation.get("opened_by"))}
     on {_e(investigation.get("opened_at"))}</p>
</header>
{
        _section(
            "Hypothesis",
            f"<p>{_e(investigation.get('hypothesis'))}</p>"
            f'<p class="meta">Confidence: <strong>{_e(investigation.get("confidence"))}</strong> — '
            f"{_e(investigation.get('confidence_basis'))}</p>",
        )
    }
{
        _section(
            "Outcome",
            (
                f"<p><strong>{_e(investigation.get('outcome'))}</strong></p>"
                f"<p>{_e(investigation.get('outcome_rationale'))}</p>"
                f'<p class="meta">Closed by {_e(investigation.get("closed_by"))} on '
                f"{_e(investigation.get('closed_at'))}</p>"
            )
            if investigation.get("outcome")
            else '<p class="meta">This investigation has not been concluded. No outcome has been recorded.</p>',
        )
    }
{_section("Findings", f"<ul>{findings}</ul>")}
{_section("Evidence", f"<ul>{entities}</ul>")}
{_section("Analyst assessments", f"<ul>{assessments}</ul>") if assessments else ""}
{_section("Review", f"<ul>{reviews}</ul>") if reviews else ""}
{
        _section(
            "History",
            "<table><thead><tr><th>When</th><th>Who</th><th>What</th><th>Value</th></tr></thead>"
            f"<tbody>{history}</tbody></table>",
        )
    }
<footer>
  <p>Produced by {_e(requested_by)} on {_e(produced)} for: {_e(purpose)}.</p>
  <p>Source system: ARGUS. This document is derived from a <strong>synthetic dataset</strong> —
     nothing in it is a record of a real person, organisation or event.</p>
  <p class="meta">The banner above is a handling instruction, not a forensic mark. It does not
     identify a recipient and does not survive retyping.</p>
</footer>
{banner}"""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{_e(investigation.get("inv_ref"))} — {_e(investigation.get("title"))}</title>
<style>
  body {{ font: 14px/1.6 -apple-system, Segoe UI, Roboto, sans-serif; color: #16191d;
         max-width: 880px; margin: 24px auto; padding: 0 20px; }}
  .banner {{ background: #16191d; color: #fff; padding: 10px 14px; border-radius: 4px;
             font-weight: 700; letter-spacing: .08em; margin: 18px 0; }}
  .banner .handling {{ display: block; font-weight: 400; letter-spacing: 0; font-size: 12px;
                       opacity: .85; margin-top: 4px; }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: .05em; color: #5a6472;
        border-bottom: 1px solid #d8dde3; padding-bottom: 4px; margin: 26px 0 10px; }}
  .ref, .meta, .cites {{ color: #5a6472; font-size: 12px; }}
  ul {{ padding-left: 18px; }} li {{ margin-bottom: 10px; }}
  li.retired {{ opacity: .55; }}
  table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
  th, td {{ border-bottom: 1px solid #e4e8ec; text-align: left; padding: 5px 6px;
            vertical-align: top; }}
  footer {{ margin-top: 28px; color: #5a6472; font-size: 12px; }}
</style></head><body>{body}</body></html>""".encode()
