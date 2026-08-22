"""Export with custody, and the calibration that the outcomes make possible.

Two route groups in one module because they are two halves of the same idea:
what leaves the system carrying a conclusion, and whether the conclusions were
any good.

Every read of an artifact writes an access row — including refused ones. That is
the half of "chain of custody" systems usually skip, and it is the half that
answers the question actually asked after an incident, which is not "was this
altered" but "who has seen it".
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.alerting.rules import DEFAULT_PARAMS, RuleParams
from app.api.dependencies import require_permission
from app.calibration.drift import compare_runs
from app.calibration.estimates import INFORMATIVE_WIDTH, estimate
from app.calibration.rules import calibrate_rules, summarise
from app.calibration.simulation import simulate
from app.evidence.artifacts import digest, verify
from app.evidence.classification import (
    CLASSIFICATIONS,
    DEFAULT_CLASSIFICATION,
    classification_by_code,
    may_access,
)
from app.evidence.export import render_html, render_json
from app.models.envelope import Envelope, Meta
from app.repositories import (
    alert_findings_repo,
    calibration_repo,
    export_repo,
    investigation_repo,
)
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import audit

router = APIRouter(
    prefix="/api/exports",
    tags=["evidence"],
    dependencies=[Depends(require_permission(Permission.EXPORT_READ))],
)

calibration_router = APIRouter(
    prefix="/api/calibration",
    tags=["calibration"],
    dependencies=[Depends(require_permission(Permission.CALIBRATION_READ))],
)

MAX_PURPOSE = 500


class ExportFormat(StrEnum):
    JSON = "json"
    HTML = "html"


class ExportRequest(BaseModel):
    investigation_ref: str = Field(min_length=1, max_length=64)
    format: ExportFormat = ExportFormat.HTML
    # Required. An export is the one operation that moves intelligence beyond
    # this system's controls, and an unexplained one is indistinguishable from
    # exfiltration when somebody reviews the register a year later.
    purpose: str = Field(min_length=1, max_length=MAX_PURPOSE)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


# ─────────────────────────────────────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/classifications")
async def get_classifications(
    _: AuthenticatedUser = Depends(require_permission(Permission.EXPORT_READ)),
) -> Envelope[dict]:
    return Envelope(
        data={
            "levels": [
                {
                    "code": c.code,
                    "label": c.label,
                    "rank": c.rank,
                    "means": c.means,
                    "handling": c.handling,
                    "export_retention_days": c.export_retention_days,
                }
                for c in CLASSIFICATIONS
            ],
            "default": DEFAULT_CLASSIFICATION,
            "scheme_note": (
                "These are not the markings of any national scheme, deliberately. This "
                "system has not been accredited to hold material under one, and a marking "
                "that looks official while meaning nothing is more dangerous than a neutral "
                "one that means what it says. Mapping to a real scheme is a deployment "
                "decision that needs an accreditation behind it."
            ),
            "retention_note": (
                "Retention applies to exports only. The audit log, the provenance records "
                "and investigation history are never disposed of — a system that expires "
                "its own accountability trail has implemented forgetting, not retention."
            ),
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Producing an export
# ─────────────────────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_export(
    payload: ExportRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.EXPORT_CREATE)),
) -> Envelope[dict]:
    """Render an investigation, hash it, and record who took it and why.

    The clearance check happens here and the refusal is logged. An export that
    was attempted and denied is a more interesting entry in the register than
    one that succeeded, so it is not allowed to fail silently.
    """
    found = await investigation_repo.get_investigation(payload.investigation_ref)
    if found is None:
        raise HTTPException(status_code=404, detail="Investigation not found")

    classification = found.get("classification") or DEFAULT_CLASSIFICATION
    clearance = getattr(user, "clearance", None) or "internal"

    if not may_access(clearance, classification):
        level = classification_by_code(classification)
        await audit.record(
            audit.AuditEvent(
                action="export.denied",
                outcome="failure",
                actor_id=user.id,
                actor_username=user.username,
                actor_role=user.role,
                resource_type="Investigation",
                resource_id=found["inv_ref"],
                request_id=getattr(request.state, "request_id", None),
                ip_address=_ip(request),
                detail=f"clearance {clearance} below classification {classification}",
            )
        )
        raise HTTPException(
            status_code=403,
            detail=(
                f"This investigation is classified {level.label} and your clearance is "
                f"{classification_by_code(clearance).label}. An export cannot exceed the "
                f"clearance of the person requesting it."
            ),
        )

    events = await investigation_repo.fetch_events(found["investigation_id"])
    render = render_json if payload.format is ExportFormat.JSON else render_html
    content = render(found, events, requested_by=user.username, purpose=payload.purpose)
    artifact = digest(content)

    record = await export_repo.create_export(
        investigation_id=found["investigation_id"],
        format_=payload.format.value,
        classification=classification,
        content=artifact.content,
        sha256=artifact.sha256,
        requested_by=user.username,
        requester_role=user.role,
        requester_clearance=clearance,
        purpose=payload.purpose,
        request_ip=_ip(request),
    )

    await audit.record(
        audit.AuditEvent(
            action="export.create",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Export",
            resource_id=str(record["export_id"]),
            after_state={
                "investigation": found["inv_ref"],
                "format": payload.format.value,
                "classification": classification,
                "sha256": artifact.sha256,
                "bytes": artifact.byte_size,
            },
            request_id=getattr(request.state, "request_id", None),
            ip_address=_ip(request),
            detail=payload.purpose,
        )
    )
    return Envelope(data={**record, "investigation_ref": found["inv_ref"]})


@router.get("")
async def list_exports(
    investigation_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    _: AuthenticatedUser = Depends(require_permission(Permission.EXPORT_READ)),
) -> Envelope[list]:
    rows = await export_repo.list_exports(
        investigation_id=investigation_id, limit=page_size, offset=(page - 1) * page_size
    )
    total = await export_repo.count_exports()
    return Envelope(data=rows, meta=Meta(total=total, page=page, page_size=page_size))


@router.get("/{export_id}")
async def get_export(
    export_id: str,
    _: AuthenticatedUser = Depends(require_permission(Permission.EXPORT_READ)),
) -> Envelope[dict]:
    row = await export_repo.fetch_export(export_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Export not found")
    access = await export_repo.list_access(export_id)
    level = classification_by_code(row["classification"])
    return Envelope(
        data={
            **row,
            "handling": level.handling,
            "access": access,
            "disposed": row["disposed_at"] is not None,
        }
    )


@router.get("/{export_id}/content")
async def download_export(
    export_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.EXPORT_READ)),
) -> Response:
    """Hand over the bytes, and record that it happened.

    The clearance check is re-applied on every download rather than only at
    creation. Classification is a property of the material, not of the moment it
    was produced, and someone whose clearance was reduced must stop being able
    to pull a copy they could have pulled last week.
    """
    row = await export_repo.fetch_export(export_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Export not found")

    clearance = getattr(user, "clearance", None) or "internal"
    if not may_access(clearance, row["classification"]):
        await export_repo.log_access(
            export_id=export_id,
            action="downloaded",
            actor_username=user.username,
            actor_role=user.role,
            actor_clearance=clearance,
            ip_address=_ip(request),
            outcome="denied",
            detail=f"clearance {clearance} below {row['classification']}",
        )
        raise HTTPException(
            status_code=403,
            detail=(
                f"This artifact is classified {row['classification']} and your clearance "
                f"is {clearance}. The refusal has been recorded against the artifact."
            ),
        )

    content = await export_repo.fetch_export_content(export_id)
    if content is None or content["disposed_at"] is not None:
        await export_repo.log_access(
            export_id=export_id,
            action="downloaded",
            actor_username=user.username,
            actor_role=user.role,
            actor_clearance=clearance,
            ip_address=_ip(request),
            outcome="denied",
            detail="content disposed of on schedule",
        )
        raise HTTPException(
            status_code=410,
            detail=(
                "This export's content was destroyed when its retention period elapsed. "
                "The record of who produced it, when and why is retained."
            ),
        )

    await export_repo.log_access(
        export_id=export_id,
        action="downloaded",
        actor_username=user.username,
        actor_role=user.role,
        actor_clearance=clearance,
        ip_address=_ip(request),
    )
    media = "application/json" if row["format"] == "json" else "text/html; charset=utf-8"
    return Response(
        content=bytes(content["content"]),
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="{export_id}.{row["format"]}"',
            # Echoed so a recipient can check the file they received against the
            # register without a second request.
            "X-Content-SHA256": row["content_sha256"],
        },
    )


@router.post("/{export_id}/verify")
async def verify_export(
    export_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.EXPORT_READ)),
) -> Envelope[dict]:
    """Re-hash the stored bytes and compare to the hash recorded at export."""
    row = await export_repo.fetch_export(export_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Export not found")
    content = await export_repo.fetch_export_content(export_id)
    stored = bytes(content["content"]) if content and content["content"] is not None else None
    ok, explanation = verify(stored, row["content_sha256"])

    clearance = getattr(user, "clearance", None) or "internal"
    await export_repo.log_access(
        export_id=export_id,
        action="verified",
        actor_username=user.username,
        actor_role=user.role,
        actor_clearance=clearance,
        ip_address=_ip(request),
        outcome="success" if ok else "denied",
        detail=explanation,
    )
    return Envelope(
        data={
            "export_id": export_id,
            "intact": ok,
            "recorded_sha256": row["content_sha256"],
            "explains": explanation,
            "disposed": row["disposed_at"] is not None,
        }
    )


# ─────────────────────────────────────────────────────────────────────────────
# Calibration
# ─────────────────────────────────────────────────────────────────────────────


class SimulationRequest(BaseModel):
    """A candidate rule configuration. Every field defaults to what runs today,
    so a request naming one parameter changes exactly that one."""

    elevated_band: str | None = None
    established_tier: str | None = None
    convergence_min_assessed: int | None = Field(default=None, ge=1, le=50)
    convergence_bands: list[str] | None = None
    escalation_bands: list[str] | None = None

    def to_params(self) -> RuleParams:
        return RuleParams(
            elevated_band=self.elevated_band or DEFAULT_PARAMS.elevated_band,
            established_tier=self.established_tier or DEFAULT_PARAMS.established_tier,
            convergence_min_assessed=(
                self.convergence_min_assessed
                if self.convergence_min_assessed is not None
                else DEFAULT_PARAMS.convergence_min_assessed
            ),
            convergence_bands=(
                frozenset(self.convergence_bands)
                if self.convergence_bands is not None
                else DEFAULT_PARAMS.convergence_bands
            ),
            escalation_bands=(
                frozenset(self.escalation_bands)
                if self.escalation_bands is not None
                else DEFAULT_PARAMS.escalation_bands
            ),
        )


@calibration_router.get("")
async def get_calibration(
    _: AuthenticatedUser = Depends(require_permission(Permission.CALIBRATION_READ)),
) -> Envelope[dict]:
    """What the feedback says about each rule — as counts, with intervals.

    Three measurements per rule, kept apart because they answer different
    questions over different denominators: what analysts dismissed, what
    investigations concluded, and (from Phase 7) what the planted labels say.
    Combining them into one score would produce a number that means nothing.
    """
    disposition = await calibration_repo.fetch_disposition()
    dismissals = await calibration_repo.fetch_dismissals()
    outcomes = await calibration_repo.fetch_outcomes()

    records = calibrate_rules(disposition, dismissals, outcomes)
    return Envelope(
        data={
            "rules": [r.as_dict() for r in records],
            "summary": summarise(records),
            "informative_width": INFORMATIVE_WIDTH,
            "method_note": (
                "Every proportion is published with its counts and an exact "
                "(Clopper-Pearson) 95% interval, and is marked uninformative when the "
                f"interval is wider than {INFORMATIVE_WIDTH:.0%}. One confirmed "
                "investigation out of one gives a precision of 100% and an interval of "
                "3%–100%; printing the first without the second would be the false "
                "authority this system exists to avoid."
            ),
        }
    )


@calibration_router.get("/false-negatives")
async def get_false_negatives(
    _: AuthenticatedUser = Depends(require_permission(Permission.CALIBRATION_READ)),
) -> Envelope[dict]:
    """Investigations opened with no alert behind them.

    A lower bound on what detection missed, and the only estimate available: it
    counts the misses somebody happened to notice. It is deliberately not
    expressed as a recall figure, because the denominator recall needs — what
    ARGUS *should* have found — does not exist.
    """
    rows = await calibration_repo.fetch_unalerted_investigations()
    confirmed = [r for r in rows if r["outcome"] == "confirmed"]
    return Envelope(
        data={
            "investigations": rows,
            "total": len(rows),
            "confirmed": len(confirmed),
            "is_a_lower_bound": True,
            "note": (
                "Each of these is a case an analyst opened without ARGUS having raised "
                "anything. Those that closed as `confirmed` are the strongest evidence "
                "available that detection missed something real. This is a floor, not a "
                "false-negative rate: it counts only the misses a person noticed, and "
                "there is no denominator for the ones nobody did."
            ),
        }
    )


@calibration_router.get("/drift")
async def get_drift(
    _: AuthenticatedUser = Depends(require_permission(Permission.CALIBRATION_READ)),
) -> Envelope[dict]:
    """Whether the assessor's band distribution has shifted between runs."""
    runs = await calibration_repo.fetch_assessment_runs()
    comparisons = [compare_runs(runs[i], runs[i + 1]).as_dict() for i in range(len(runs) - 1)]
    return Envelope(
        data={
            "runs": runs,
            "comparisons": comparisons,
            "evaluable": len(runs) >= 2,
            "note": (
                "Two consecutive completed runs are needed for a comparison. A shift "
                "across different model fingerprints is expected and is not drift; the "
                "case worth attention is a shift between two runs of the same model."
            ),
        }
    )


@calibration_router.post("/simulate")
async def simulate_thresholds(
    payload: SimulationRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.ALERT_RUN)),
) -> Envelope[dict]:
    """Replay the rules under a candidate configuration. Writes nothing.

    Requires `alert:run` rather than `calibration:read` — a simulation is the
    first step of changing what every analyst's queue contains, and reading how
    well the current rules perform is a different-sized decision from proposing
    to change them.

    Nothing here activates anything. There is no endpoint that does; changing a
    threshold means changing `DEFAULT_PARAMS` and shipping it, which leaves the
    change in version control where a reviewer can see it. An API that could
    retune detection at runtime would make the rules fingerprint — the thing
    every measured precision figure is keyed to — meaningless.
    """
    candidate = payload.to_params()
    bands = await alert_findings_repo.fetch_alerting_evidence(
        tuple(sorted(candidate.convergence_bands | {candidate.elevated_band}))
    )
    current_keys = await calibration_repo.fetch_alert_keys()
    dismissals = await calibration_repo.fetch_dismissal_by_key()
    confirmed = await calibration_repo.fetch_confirmed_alert_keys()

    result = simulate(
        bands,
        candidate,
        current_alert_keys=current_keys,
        dismissal_by_key=dismissals,
        confirmed_keys=confirmed,
    )

    await audit.record(
        audit.AuditEvent(
            action="calibration.simulate",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="RuleSet",
            resource_id="simulation",
            after_state={"changes": result.changes, "added": len(result.added), "removed": len(result.removed_keys)},
            request_id=getattr(request.state, "request_id", None),
            ip_address=_ip(request),
        )
    )
    return Envelope(
        data={
            **result.as_dict(),
            "activation_note": (
                "This changed nothing. There is no endpoint that activates a rule "
                "configuration: a threshold change is a code change, so it goes through "
                "review and version control and stays attached to the rules fingerprint "
                "every measured figure is keyed to."
            ),
        }
    )


@calibration_router.get("/example")
async def calibration_example(
    successes: int = Query(..., ge=0),
    trials: int = Query(..., ge=0),
    _: AuthenticatedUser = Depends(require_permission(Permission.CALIBRATION_READ)),
) -> Envelope[dict]:
    """The estimator itself, so a reader can see what it does to their numbers.

    Exposed because the central claim of this phase — that a proportion without
    its interval is not a measurement — is easier to accept after watching 1/1
    return an interval from 3% to 100%.
    """
    if successes > trials:
        raise HTTPException(status_code=400, detail=f"{successes} successes out of {trials} trials is not a proportion")
    return Envelope(data=estimate(successes, trials).as_dict())
