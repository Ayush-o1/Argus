"""User administration and audit-log access.

Two roles reach this router and they see different things, which is the point of
separating them (see app/security/roles.py):

  - **Administrator** manages users. They hold no intelligence-read permission,
    so compromising an admin account grants the ability to disrupt ARGUS but not
    to read what it knows.
  - **Auditor** reads the audit log and can verify its hash chain. They hold no
    write permission at all, so the account that can see what happened cannot
    also change it.
"""

from __future__ import annotations

import uuid

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_pg, require_permission
from app.models.envelope import Envelope, Meta
from app.repositories import user_repo
from app.security import sessions
from app.security.passwords import WeakPassword
from app.security.roles import Permission, Role
from app.security.sessions import AuthenticatedUser
from app.services import audit

router = APIRouter(prefix="/api/admin", tags=["admin"])


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=1024)
    role: Role


class SetActiveRequest(BaseModel):
    is_active: bool


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/users")
async def list_users(
    conn: asyncpg.Connection = Depends(get_pg),
    _: AuthenticatedUser = Depends(require_permission(Permission.USER_MANAGE)),
) -> Envelope[list]:
    users = await user_repo.list_users(conn)
    return Envelope(
        data=[
            {
                "id": str(u.id),
                "username": u.username,
                "display_name": u.display_name,
                "role": u.role,
                "is_active": u.is_active,
                "mfa_enrolled": u.mfa_enrolled,
            }
            for u in users
        ]
    )


@router.post("/users")
async def create_user(
    payload: CreateUserRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_pg),
    actor: AuthenticatedUser = Depends(require_permission(Permission.USER_MANAGE)),
) -> Envelope[dict]:
    existing = await user_repo.get_by_username(conn, payload.username)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    try:
        created = await user_repo.create_user(
            conn, payload.username, payload.display_name, payload.password, payload.role
        )
    except WeakPassword as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await audit.record(
        audit.AuditEvent(
            action="user.create",
            outcome="success",
            actor_id=actor.id,
            actor_username=actor.username,
            actor_role=actor.role,
            resource_type="User",
            resource_id=str(created.id),
            # The password is never recorded, in any form.
            after_state={"username": created.username, "role": created.role},
            request_id=getattr(request.state, "request_id", None),
            ip_address=_ip(request),
        )
    )
    return Envelope(
        data={
            "id": str(created.id),
            "username": created.username,
            "display_name": created.display_name,
            "role": created.role,
        }
    )


@router.put("/users/{user_id}/active")
async def set_user_active(
    user_id: uuid.UUID,
    payload: SetActiveRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_pg),
    actor: AuthenticatedUser = Depends(require_permission(Permission.USER_MANAGE)),
) -> Envelope[dict]:
    target = await user_repo.get_by_id(conn, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user_id == actor.id and not payload.is_active:
        # Not a safety rail against malice — an admin can create another admin
        # — but it prevents the common accident of locking yourself out.
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")

    await user_repo.set_active(conn, user_id, payload.is_active)

    revoked = 0
    if not payload.is_active:
        # Deactivation that leaves live sessions running has not deactivated
        # anything.
        revoked = await sessions.revoke_all_for_user(conn, user_id, "account deactivated")

    await audit.record(
        audit.AuditEvent(
            action="user.set_active",
            outcome="success",
            actor_id=actor.id,
            actor_username=actor.username,
            actor_role=actor.role,
            resource_type="User",
            resource_id=str(user_id),
            before_state={"is_active": target.is_active},
            after_state={"is_active": payload.is_active},
            detail=f"revoked {revoked} session(s)" if revoked else None,
            request_id=getattr(request.state, "request_id", None),
            ip_address=_ip(request),
        )
    )
    return Envelope(data={"updated": True, "sessions_revoked": revoked})


@router.get("/audit")
async def read_audit_log(
    action: str | None = Query(None, max_length=64),
    resource_id: str | None = Query(None, max_length=64),
    actor_username: str | None = Query(None, max_length=64),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    conn: asyncpg.Connection = Depends(get_pg),
    _: AuthenticatedUser = Depends(require_permission(Permission.AUDIT_READ)),
) -> Envelope[list]:
    """Read the audit log. Filters are optional and combine with AND."""
    where: list[str] = []
    params: list[object] = []

    for column, value in (
        ("action", action),
        ("resource_id", resource_id),
        ("actor_username", actor_username),
    ):
        if value:
            params.append(value)
            where.append(f"{column} = ${len(params)}")

    clause = f"WHERE {' AND '.join(where)}" if where else ""

    total = await conn.fetchval(f"SELECT count(*) FROM audit_events {clause}", *params)

    params.extend([page_size, (page - 1) * page_size])
    rows = await conn.fetch(
        f"""
        SELECT seq, id, occurred_at, actor_username, actor_role, action,
               resource_type, resource_id, outcome, before_state, after_state,
               request_id, host(ip_address) AS ip_address, detail, entry_hash
        FROM audit_events {clause}
        ORDER BY seq DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """,
        *params,
    )

    return Envelope(
        data=[dict(r) for r in rows],
        meta=Meta(total=total or 0, page=page, page_size=page_size),
    )


@router.get("/audit/verify")
async def verify_audit_chain(
    _: AuthenticatedUser = Depends(require_permission(Permission.AUDIT_READ)),
) -> Envelope[dict]:
    """Recompute the audit hash chain and report any break.

    This is what makes the log tamper-*evident* rather than only
    tamper-resistant: the database blocks UPDATE and DELETE, but this detects
    alteration by anyone who bypassed those controls.
    """
    result = await audit.verify_chain()
    return Envelope(
        data={
            "ok": result.ok,
            "entries_checked": result.checked,
            "first_broken_seq": result.first_broken_seq,
            "detail": result.detail,
        }
    )
