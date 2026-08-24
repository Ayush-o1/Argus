"""Rendering an investigation into something that can leave the system.

Four formats from one snapshot, in one request, so a JSON export, an HTML
export, a Markdown export and a PDF export of the same investigation can
never describe different states of it. json is for a machine; html, markdown
and pdf are three renderings for a person, chosen for the medium they end up
in — a browser tab, a text editor or version-controlled document, and a
printed or emailed report respectively. All four walk the identical
investigation dict; none has a fact the others lack.

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
import io
import json
from datetime import UTC, datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.evidence.classification import classification_by_code

__all__ = ["render_html", "render_json", "render_markdown", "render_pdf"]


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


def _md_escape(value: Any) -> str:
    """Escape the handful of characters Markdown gives special meaning, so a
    finding statement containing `*`, `_`, `#` or `[` renders as the analyst
    typed it rather than as accidental emphasis, a heading, or a broken link."""
    text = "" if value is None else str(value)
    for ch in ("\\", "*", "_", "#", "[", "]", "|"):
        text = text.replace(ch, "\\" + ch)
    return text


def render_markdown(
    investigation: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    requested_by: str,
    purpose: str,
) -> bytes:
    """The version-controllable export: diffable, and readable without a browser."""
    m = _md_escape
    code = investigation.get("classification", "internal")
    level = classification_by_code(code)
    produced = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        f"**{level.label.upper()}** — {m(level.handling)}",
        "",
        f"# {m(investigation.get('title'))}",
        f"`{m(investigation.get('inv_ref'))}` · opened by {m(investigation.get('opened_by'))} "
        f"on {m(investigation.get('opened_at'))}",
        "",
        "## Hypothesis",
        "",
        m(investigation.get("hypothesis")),
        "",
        f"**Confidence:** {m(investigation.get('confidence'))} — {m(investigation.get('confidence_basis'))}",
        "",
        "## Outcome",
        "",
    ]

    if investigation.get("outcome"):
        lines += [
            f"**{m(investigation.get('outcome'))}**",
            "",
            m(investigation.get("outcome_rationale")),
            "",
            f"Closed by {m(investigation.get('closed_by'))} on {m(investigation.get('closed_at'))}",
            "",
        ]
    else:
        lines += ["This investigation has not been concluded. No outcome has been recorded.", ""]

    lines += ["## Findings", ""]
    findings = investigation.get("findings") or []
    if findings:
        for f in findings:
            retired = f.get("withdrawn_at") or f.get("superseded_at")
            prefix = "~~" if retired else ""
            suffix = "~~" if retired else ""
            lines.append(f"- {prefix}{m(f.get('statement'))}{suffix}")
            meta = (
                f"  confidence {m(f.get('confidence'))} · {m(f.get('author_username'))} "
                f"({m(f.get('author_role'))}) · {m(f.get('recorded_at'))}"
            )
            if f.get("withdrawn_at"):
                meta += f" · **withdrawn**: {m(f.get('withdrawal_reason'))}"
            if f.get("superseded_at"):
                meta += " · **superseded**"
            lines.append(meta)
            cites = ", ".join(f.get("cites") or [])
            lines.append(f"  cites: {m(cites)}")
    else:
        lines.append("No findings recorded.")
    lines.append("")

    lines += ["## Evidence", ""]
    entities = investigation.get("entities") or []
    if entities:
        for e in entities:
            entry = f"- {m(e.get('entity_ref'))} ({m(e.get('entity_type'))}) — {m(e.get('reason'))}"
            if e.get("removed_at"):
                entry += f" · **removed** by {m(e.get('removed_by'))}: {m(e.get('removal_reason'))}"
            lines.append(entry)
    else:
        lines.append("No evidence linked.")
    lines.append("")

    assessments = investigation.get("analyst_assessments") or []
    if assessments:
        lines += ["## Analyst assessments", ""]
        for a in assessments:
            entry = (
                f"- {m(a.get('subject_ref'))} — ARGUS assessed **{m(a.get('machine_band') or 'not assessed')}**; "
                f"{m(a.get('author_username'))} assessed **{m(a.get('analyst_band'))}**"
            )
            if a.get("dissents"):
                entry += " _(disagreement)_"
            lines.append(entry)
            if a.get("rationale"):
                lines.append(f"  {m(a.get('rationale'))}")
        lines.append("")

    reviews = investigation.get("reviews") or []
    if reviews:
        lines += ["## Review", ""]
        for r in reviews:
            verb = "concurs with" if r.get("concurs") else "**does not concur with**"
            lines.append(
                f"- {m(r.get('reviewer'))} ({m(r.get('reviewer_role'))}) {verb} {m(r.get('outcome_reviewed'))}"
            )
            if r.get("note"):
                lines.append(f"  {m(r.get('note'))}")
        lines.append("")

    lines += ["## History", "", "| When | Who | What | Value |", "|---|---|---|---|"]
    for ev in events:
        what = ev.get("field") or ev.get("event_type")
        value = json.dumps(ev.get("new_value")) if ev.get("field") else (ev.get("note") or "")
        lines.append(f"| {m(ev.get('occurred_at'))} | {m(ev.get('actor_username'))} | {m(what)} | {m(value)} |")
    lines.append("")

    lines += [
        "---",
        "",
        f"Produced by {m(requested_by)} on {produced} for: {m(purpose)}.",
        "",
        "Source system: ARGUS. This document is derived from a **synthetic dataset** — "
        "nothing in it is a record of a real person, organisation or event.",
        "",
        "_The banner above is a handling instruction, not a forensic mark. It does not "
        "identify a recipient and does not survive retyping._",
    ]

    return ("\n".join(lines) + "\n").encode("utf-8")


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


def _pdf_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ArgusTitle", parent=base["Title"], alignment=0, spaceAfter=2),
        "ref": ParagraphStyle("ArgusRef", parent=base["Normal"], textColor=colors.HexColor("#5a6472"), fontSize=9),
        "h2": ParagraphStyle(
            "ArgusH2",
            parent=base["Heading2"],
            fontSize=11,
            textColor=colors.HexColor("#5a6472"),
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle("ArgusBody", parent=base["Normal"], fontSize=10, leading=14),
        "meta": ParagraphStyle("ArgusMeta", parent=base["Normal"], fontSize=8, textColor=colors.HexColor("#5a6472")),
        "banner": ParagraphStyle(
            "ArgusBanner", parent=base["Normal"], textColor=colors.white, fontSize=11, leading=14
        ),
    }


def _pdf_banner(level: Any, styles: dict[str, ParagraphStyle]) -> Table:
    cell = Paragraph(f"<b>{_e(level.label.upper())}</b><br/>{_e(level.handling)}", styles["banner"])
    table = Table([[cell]], colWidths=[6.5 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#16191d")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def render_pdf(
    investigation: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    requested_by: str,
    purpose: str,
) -> bytes:
    """The printable/emailable export.

    Drawn directly from the investigation dict with reportlab's flowables —
    the same fields render_html turns into markup, laid out for a page rather
    than a browser viewport. No HTML is parsed; nothing here can drift from
    what the other three formats say because none of them is the source the
    others are derived from — the investigation dict is.
    """
    styles = _pdf_styles()
    code = investigation.get("classification", "internal")
    level = classification_by_code(code)
    produced = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    story: list[Any] = [_pdf_banner(level, styles), Spacer(1, 14)]

    story.append(Paragraph(_e(investigation.get("title")), styles["title"]))
    story.append(
        Paragraph(
            f"{_e(investigation.get('inv_ref'))} · opened by {_e(investigation.get('opened_by'))} "
            f"on {_e(investigation.get('opened_at'))}",
            styles["ref"],
        )
    )

    story.append(Paragraph("Hypothesis", styles["h2"]))
    story.append(Paragraph(_e(investigation.get("hypothesis")), styles["body"]))
    story.append(
        Paragraph(
            f"<b>Confidence:</b> {_e(investigation.get('confidence'))} — "
            f"{_e(investigation.get('confidence_basis'))}",
            styles["meta"],
        )
    )

    story.append(Paragraph("Outcome", styles["h2"]))
    if investigation.get("outcome"):
        story.append(Paragraph(f"<b>{_e(investigation.get('outcome'))}</b>", styles["body"]))
        story.append(Paragraph(_e(investigation.get("outcome_rationale")), styles["body"]))
        story.append(
            Paragraph(
                f"Closed by {_e(investigation.get('closed_by'))} on {_e(investigation.get('closed_at'))}",
                styles["meta"],
            )
        )
    else:
        story.append(
            Paragraph("This investigation has not been concluded. No outcome has been recorded.", styles["meta"])
        )

    story.append(Paragraph("Findings", styles["h2"]))
    findings = investigation.get("findings") or []
    if findings:
        items: list[Any] = []
        for f in findings:
            retired = f.get("withdrawn_at") or f.get("superseded_at")
            statement = _e(f.get("statement"))
            if retired:
                statement = f"<strike>{statement}</strike>"
            meta = (
                f"confidence {_e(f.get('confidence'))} · {_e(f.get('author_username'))} "
                f"({_e(f.get('author_role'))}) · {_e(f.get('recorded_at'))}"
            )
            if f.get("withdrawn_at"):
                meta += f" · <b>withdrawn</b>: {_e(f.get('withdrawal_reason'))}"
            if f.get("superseded_at"):
                meta += " · <b>superseded</b>"
            cites = _e(", ".join(f.get("cites") or []))
            items.append(
                ListItem(
                    KeepTogether(
                        [
                            Paragraph(statement, styles["body"]),
                            Paragraph(meta, styles["meta"]),
                            Paragraph(f"cites: {cites}", styles["meta"]),
                        ]
                    )
                )
            )
        story.append(ListFlowable(items, bulletType="bullet"))
    else:
        story.append(Paragraph("No findings recorded.", styles["body"]))

    story.append(Paragraph("Evidence", styles["h2"]))
    entities = investigation.get("entities") or []
    if entities:
        items = []
        for e in entities:
            text = f"{_e(e.get('entity_ref'))} ({_e(e.get('entity_type'))}) — {_e(e.get('reason'))}"
            if e.get("removed_at"):
                text += f" · <b>removed</b> by {_e(e.get('removed_by'))}: {_e(e.get('removal_reason'))}"
            items.append(ListItem(Paragraph(text, styles["body"])))
        story.append(ListFlowable(items, bulletType="bullet"))
    else:
        story.append(Paragraph("No evidence linked.", styles["body"]))

    assessments = investigation.get("analyst_assessments") or []
    if assessments:
        story.append(Paragraph("Analyst assessments", styles["h2"]))
        items = []
        for a in assessments:
            text = (
                f"{_e(a.get('subject_ref'))} — ARGUS assessed "
                f"<b>{_e(a.get('machine_band') or 'not assessed')}</b>; "
                f"{_e(a.get('author_username'))} assessed <b>{_e(a.get('analyst_band'))}</b>"
            )
            if a.get("dissents"):
                text += " <i>(disagreement)</i>"
            body: list[Any] = [Paragraph(text, styles["body"])]
            if a.get("rationale"):
                body.append(Paragraph(_e(a.get("rationale")), styles["meta"]))
            items.append(ListItem(KeepTogether(body)))
        story.append(ListFlowable(items, bulletType="bullet"))

    reviews = investigation.get("reviews") or []
    if reviews:
        story.append(Paragraph("Review", styles["h2"]))
        items = []
        for r in reviews:
            verb = "concurs with" if r.get("concurs") else "<b>does not concur with</b>"
            text = f"{_e(r.get('reviewer'))} ({_e(r.get('reviewer_role'))}) {verb} {_e(r.get('outcome_reviewed'))}"
            body = [Paragraph(text, styles["body"])]
            if r.get("note"):
                body.append(Paragraph(_e(r.get("note")), styles["meta"]))
            items.append(ListItem(KeepTogether(body)))
        story.append(ListFlowable(items, bulletType="bullet"))

    story.append(Paragraph("History", styles["h2"]))
    header = [Paragraph(f"<b>{h}</b>", styles["meta"]) for h in ("When", "Who", "What", "Value")]
    rows = [header]
    for ev in events:
        what = ev.get("field") or ev.get("event_type")
        value = json.dumps(ev.get("new_value")) if ev.get("field") else (ev.get("note") or "")
        rows.append(
            [
                Paragraph(_e(ev.get("occurred_at")), styles["meta"]),
                Paragraph(_e(ev.get("actor_username")), styles["meta"]),
                Paragraph(_e(what), styles["meta"]),
                Paragraph(_e(value), styles["meta"]),
            ]
        )
    history_table = Table(rows, colWidths=[1.3 * inch, 1.1 * inch, 1.3 * inch, 2.8 * inch], repeatRows=1)
    history_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#e4e8ec")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(history_table)

    story.append(Spacer(1, 16))
    story.append(Paragraph(f"Produced by {_e(requested_by)} on {produced} for: {_e(purpose)}.", styles["meta"]))
    story.append(
        Paragraph(
            "Source system: ARGUS. This document is derived from a <b>synthetic dataset</b> — "
            "nothing in it is a record of a real person, organisation or event.",
            styles["meta"],
        )
    )
    story.append(
        Paragraph(
            "The banner above is a handling instruction, not a forensic mark. It does not "
            "identify a recipient and does not survive retyping.",
            styles["meta"],
        )
    )
    story.append(Spacer(1, 10))
    story.append(_pdf_banner(level, styles))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=f"{investigation.get('inv_ref')} — {investigation.get('title')}",
    )
    doc.build(story)
    return buffer.getvalue()
