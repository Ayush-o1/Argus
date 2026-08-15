"""Ingestion API — source health, connector control, and the dead-letter queue.

The health surface answers a question ARGUS could not previously ask at all:
**is a source still producing?** A feed that stops looks exactly like a world in
which nothing is happening, and an analyst cannot tell those apart without being
told. Everything here exists to make that difference visible.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.dependencies import require_all_permissions, require_permission
from app.ingestion import registered_types
from app.models.envelope import Envelope
from app.repositories import ingest_repo
from app.security.roles import Permission
from app.security.sessions import AuthenticatedUser
from app.services import audit, ingest, queue

router = APIRouter(
    prefix="/api/ingest",
    tags=["ingest"],
    dependencies=[Depends(require_permission(Permission.INGEST_READ))],
)

MAX_ID = 64
MAX_REASON = 1_000


class UpsertConnectorRequest(BaseModel):
    connector_id: str = Field(min_length=1, max_length=MAX_ID, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    source_id: str = Field(min_length=1, max_length=MAX_ID)
    connector_type: str = Field(min_length=1, max_length=MAX_ID)
    display_name: str = Field(min_length=1, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)
    mapping: dict[str, Any]
    poll_interval_seconds: int = Field(default=300, ge=10, le=86_400)
    enabled: bool = True


class QuarantineRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=MAX_REASON)


class ResolveFailureRequest(BaseModel):
    resolution: str = Field(min_length=1, max_length=MAX_REASON)


@router.get("/health")
async def get_health() -> Envelope[dict]:
    """Per-source freshness, volume, error rate and dead-letter depth."""
    rows = await ingest_repo.health_rows()
    stale = await ingest_repo.open_failure_count()
    return Envelope(
        data={
            "connectors": rows,
            "stale": await ingest.stale_sources(),
            "open_failures": stale,
            "queue": await queue.stats(),
            "connector_types": registered_types(),
        }
    )


@router.get("/connectors")
async def list_connectors() -> Envelope[list[dict]]:
    rows = await ingest_repo.list_connectors()
    return Envelope(
        data=[
            {
                "connector_id": row.connector_id,
                "source_id": row.source_id,
                "connector_type": row.connector_type,
                "display_name": row.display_name,
                # `config` is echoed only after the connector's own redaction,
                # so a value that looks like a credential never leaves the
                # process even though storing one is already refused.
                "config": _redact(row.config),
                "mapping": row.mapping,
                "enabled": row.enabled,
                "poll_interval_seconds": row.poll_interval_seconds,
                "quarantined_at": row.quarantined_at,
                "quarantine_reason": row.quarantine_reason,
                "last_run_at": row.last_run_at,
                "last_success_at": row.last_success_at,
            }
            for row in rows
        ]
    )


@router.get("/connectors/{connector_id}/batches")
async def get_batches(
    connector_id: str, limit: int = Query(20, ge=1, le=200)
) -> Envelope[list[dict]]:
    if await ingest_repo.get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    return Envelope(data=await ingest_repo.recent_batches(connector_id, limit))


@router.get("/connectors/{connector_id}/fields")
async def get_fields(connector_id: str) -> Envelope[list[dict]]:
    """Every field this source has ever sent, with when it was first and last
    seen. A field that stops arriving is a schema change nothing else reports."""
    if await ingest_repo.get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    return Envelope(data=await ingest_repo.known_fields(connector_id))


@router.put("/connectors")
async def upsert_connector(
    payload: UpsertConnectorRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INGEST_MANAGE)),
) -> Envelope[dict]:
    """Register or update a connector.

    This endpoint is the acceptance criterion "a source can be added without
    code changes to the core": `connector_type` names a registered
    implementation and everything else is data.
    """
    if payload.connector_type not in registered_types():
        raise HTTPException(
            status_code=400,
            detail=f"Unknown connector type. Registered: {', '.join(registered_types())}",
        )
    if any(_looks_like_secret(key) for key in payload.config):
        raise HTTPException(
            status_code=400,
            detail=(
                "Connector config must not contain a credential. Name an environment "
                "variable instead — e.g. `token_env: ACME_TOKEN` — so the secret is not "
                "stored in a table, a backup, or a replica."
            ),
        )

    from app.ingestion.mapping import InvalidMapping, RecordMapping

    try:
        RecordMapping.from_config(payload.mapping)
    except InvalidMapping as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await ingest_repo.upsert_connector(
        connector_id=payload.connector_id,
        source_id=payload.source_id,
        connector_type=payload.connector_type,
        display_name=payload.display_name,
        config=payload.config,
        mapping=payload.mapping,
        poll_interval_seconds=payload.poll_interval_seconds,
        enabled=payload.enabled,
    )
    await _audit(request, user, "ingest.connector_upsert", payload.connector_id,
                 after={"type": payload.connector_type, "source_id": payload.source_id})
    return Envelope(data={"connector_id": payload.connector_id})


@router.post("/connectors/{connector_id}/run")
async def run_now(
    connector_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INGEST_MANAGE)),
) -> Envelope[dict]:
    """Queue an immediate run. Returns the job id, not the result.

    Queued rather than executed inline on purpose: the work must survive a
    restart, and an HTTP request is the least durable place to hold it.
    """
    if await ingest_repo.get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    job_id = await queue.enqueue(
        ingest.INGEST_JOB_KIND, {"connector_id": connector_id}, priority=10
    )
    await _audit(request, user, "ingest.run_requested", connector_id)
    return Envelope(data={"job_id": job_id, "queued": job_id is not None})


@router.post("/connectors/{connector_id}/quarantine")
async def quarantine(
    connector_id: str,
    payload: QuarantineRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INGEST_MANAGE)),
) -> Envelope[dict]:
    if await ingest_repo.get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    await ingest_repo.set_quarantine(connector_id, payload.reason)
    await _audit(request, user, "ingest.quarantine", connector_id,
                 after={"reason": payload.reason})
    return Envelope(data={"quarantined": True})


@router.post("/connectors/{connector_id}/release")
async def release_quarantine(
    connector_id: str,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INGEST_MANAGE)),
) -> Envelope[dict]:
    if await ingest_repo.get_connector(connector_id) is None:
        raise HTTPException(status_code=404, detail="Connector not found")
    await ingest_repo.set_quarantine(connector_id, None)
    await _audit(request, user, "ingest.quarantine_released", connector_id)
    return Envelope(data={"quarantined": False})


@router.get("/failures")
async def list_failures(
    connector_id: str | None = None,
    include_resolved: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> Envelope[list[dict]]:
    """The dead-letter queue — metadata only.

    Deliberately excludes the rejected payload. Reading that is a disclosure of
    source content, so it has its own endpoint with its own permission.
    """
    return Envelope(
        data=await ingest_repo.list_failures(
            connector_id=connector_id, include_resolved=include_resolved, limit=limit
        )
    )


@router.get("/failures/{failure_id}/payload")
async def get_failure_payload(
    failure_id: int,
    _: AuthenticatedUser = Depends(
        require_all_permissions(Permission.INGEST_READ, Permission.ENTITY_READ)
    ),
) -> Envelope[dict]:
    """The rejected record itself.

    Requires `entity:read` on top of `ingest:read`, so an administrator — who
    operates the pipeline but deliberately cannot read intelligence — is refused
    here while still being able to see that the failure exists and why.
    """
    failure = await ingest_repo.get_failure(failure_id)
    if failure is None:
        raise HTTPException(status_code=404, detail="Failure not found")
    if failure["raw_id"] is None:
        raise HTTPException(
            status_code=404, detail="This failure occurred before any payload was stored"
        )
    raw = await ingest_repo.get_raw(failure["raw_id"])
    if raw is None:  # pragma: no cover - foreign key guarantees this
        raise HTTPException(status_code=404, detail="Stored payload is missing")
    return Envelope(data={"failure": failure, "raw": raw})


@router.post("/failures/{failure_id}/replay")
async def replay(
    failure_id: int,
    request: Request,
    user: AuthenticatedUser = Depends(
        require_all_permissions(Permission.INGEST_MANAGE, Permission.ENTITY_READ)
    ),
) -> Envelope[dict]:
    """Re-run a dead-lettered record after fixing its cause.

    Requires intelligence-read as well as ingest-manage: a replay writes source
    content into the observation store, which is an intelligence act rather than
    an operational one.
    """
    try:
        result = await ingest.replay_failure(failure_id, actor=f"user:{user.id}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _audit(request, user, "ingest.replay", str(failure_id), after=result)
    return Envelope(data=result)


@router.post("/failures/{failure_id}/resolve")
async def resolve(
    failure_id: int,
    payload: ResolveFailureRequest,
    request: Request,
    user: AuthenticatedUser = Depends(require_permission(Permission.INGEST_MANAGE)),
) -> Envelope[dict]:
    """Close a dead-letter entry without replaying it — the record was junk, or
    superseded. The entry stays; only its resolution is recorded."""
    changed = await ingest_repo.resolve_failure(
        failure_id, resolved_by=f"user:{user.id}", resolution=payload.resolution, replayed=False
    )
    if not changed:
        raise HTTPException(status_code=409, detail="Already resolved, or no such failure")
    await _audit(request, user, "ingest.failure_resolved", str(failure_id),
                 after={"resolution": payload.resolution})
    return Envelope(data={"resolved": True})


def _looks_like_secret(key: str) -> bool:
    lowered = key.lower()
    if lowered.endswith("_env"):
        return False
    return any(marker in lowered for marker in ("token", "secret", "password", "apikey", "api_key"))


def _redact(config: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in config.items() if not _looks_like_secret(k)}


async def _audit(
    request: Request,
    user: AuthenticatedUser,
    action: str,
    resource_id: str,
    after: dict[str, Any] | None = None,
) -> None:
    await audit.record(
        audit.AuditEvent(
            action=action,
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Connector",
            resource_id=resource_id,
            after_state=after,
            request_id=getattr(request.state, "request_id", None),
            ip_address=request.client.host if request.client else None,
        )
    )
