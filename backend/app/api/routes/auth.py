"""Authentication: login, MFA, logout, session introspection."""

from __future__ import annotations

import secrets

import asyncpg
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.api.dependencies import current_user, get_pg
from app.config import get_settings
from app.models.envelope import Envelope
from app.repositories import user_repo
from app.repositories.user_repo import AuthOutcome
from app.security import sessions
from app.security.roles import permissions_for
from app.security.sessions import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    AuthenticatedUser,
)
from app.services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

# One message for every failure mode. Distinguishing "no such user" from "wrong
# password" from "locked" hands an attacker a free account-enumeration oracle;
# the real reason is recorded in the audit log, where it is useful to defenders
# rather than to attackers.
_GENERIC_LOGIN_FAILURE = "Invalid username or password."


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)
    # Supplied on the second call when the account has MFA enrolled.
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_session_cookies(response: Response, token: str, csrf_token: str) -> None:
    settings = get_settings()
    max_age = settings.session_absolute_hours * 3600

    # httpOnly: JavaScript cannot read it, so an XSS flaw cannot exfiltrate the
    # session. This is the property the previous NEXT_PUBLIC token could never
    # have, since it was in the bundle by construction.
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )
    # Readable by same-origin JS on purpose: the SPA echoes it back in a header,
    # which an attacker's origin cannot do.
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="strict",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    for name in (SESSION_COOKIE_NAME, CSRF_COOKIE_NAME):
        response.delete_cookie(name, path="/")


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    conn: asyncpg.Connection = Depends(get_pg),
) -> Envelope[dict]:
    ip = _client_ip(request)
    user_agent = request.headers.get("user-agent")
    request_id = getattr(request.state, "request_id", None)

    outcome, row = await user_repo.authenticate(conn, payload.username, payload.password)

    async def _audit(action: str, result: str, detail: str) -> None:
        await audit.record(
            audit.AuditEvent(
                action=action,
                outcome=result,
                actor_id=row["id"] if row else None,
                actor_username=row["username"] if row else payload.username,
                actor_role=row["role"] if row else None,
                request_id=request_id,
                ip_address=ip,
                user_agent=user_agent,
                detail=detail,
            )
        )

    if outcome is AuthOutcome.MFA_REQUIRED:
        assert row is not None
        if not payload.mfa_code:
            await _audit("auth.login", "denied", "MFA code required")
            # 401 with a machine-readable marker so the client can prompt,
            # without revealing anything to a caller who has not already passed
            # the password check.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="mfa_required",
            )
        if not pyotp.TOTP(row["mfa_secret"]).verify(payload.mfa_code, valid_window=1):
            await user_repo.register_failed_login(conn, row["id"])
            await _audit("auth.login", "denied", "invalid MFA code")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_LOGIN_FAILURE)
        outcome = AuthOutcome.SUCCESS

    if outcome is not AuthOutcome.SUCCESS:
        await _audit("auth.login", "denied", f"login failed: {outcome.value}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_LOGIN_FAILURE)

    assert row is not None
    await user_repo.register_successful_login(conn, row["id"], payload.password, row["password_hash"])
    token, session_id, expires_at = await sessions.create_session(conn, row["id"], ip, user_agent)
    csrf_token = secrets.token_urlsafe(32)
    _set_session_cookies(response, token, csrf_token)

    await audit.record(
        audit.AuditEvent(
            action="auth.login",
            outcome="success",
            actor_id=row["id"],
            actor_username=row["username"],
            actor_role=row["role"],
            resource_type="Session",
            resource_id=str(session_id),
            request_id=request_id,
            ip_address=ip,
            user_agent=user_agent,
        )
    )

    return Envelope(
        data={
            "user": {
                "id": str(row["id"]),
                "username": row["username"],
                "display_name": row["display_name"],
                "role": row["role"],
            },
            "permissions": sorted(p.value for p in permissions_for(row["role"])),
            "expires_at": expires_at.isoformat(),
        }
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    user: AuthenticatedUser = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_pg),
) -> Envelope[dict]:
    await sessions.revoke_session(conn, user.session_id, "user logout")
    _clear_session_cookies(response)

    await audit.record(
        audit.AuditEvent(
            action="auth.logout",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            resource_type="Session",
            resource_id=str(user.session_id),
            request_id=getattr(request.state, "request_id", None),
            ip_address=_client_ip(request),
        )
    )
    return Envelope(data={"logged_out": True})


@router.get("/me")
async def me(user: AuthenticatedUser = Depends(current_user)) -> Envelope[dict]:
    """Who the caller is and what they may do.

    The frontend uses `permissions` to decide which surfaces to show. That is a
    usability affordance, never a control: every permission is enforced again on
    the server, because a hidden button is not a security boundary.
    """
    return Envelope(
        data={
            "user": {
                "id": str(user.id),
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role,
            },
            "permissions": sorted(p.value for p in permissions_for(user.role)),
        }
    )


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: AuthenticatedUser = Depends(current_user),
    conn: asyncpg.Connection = Depends(get_pg),
) -> Envelope[dict]:
    row = await user_repo.get_by_username(conn, user.username)
    if row is None:  # pragma: no cover - the session resolved, so the user exists
        raise HTTPException(status_code=404, detail="User not found")

    from app.security.passwords import WeakPassword, verify_password

    if not verify_password(payload.current_password, row["password_hash"]):
        await audit.record(
            audit.AuditEvent(
                action="auth.change_password",
                outcome="denied",
                actor_id=user.id,
                actor_username=user.username,
                actor_role=user.role,
                detail="current password incorrect",
                request_id=getattr(request.state, "request_id", None),
                ip_address=_client_ip(request),
            )
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Current password is incorrect.")

    try:
        await user_repo.set_password(conn, user.id, payload.new_password)
    except WeakPassword as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    # Every other session is killed: a password change that leaves existing
    # sessions alive has not revoked anything, which is the whole point of
    # changing it after a suspected compromise.
    revoked = await sessions.revoke_all_for_user(conn, user.id, "password changed")
    _clear_session_cookies(response)

    await audit.record(
        audit.AuditEvent(
            action="auth.change_password",
            outcome="success",
            actor_id=user.id,
            actor_username=user.username,
            actor_role=user.role,
            detail=f"revoked {revoked} session(s)",
            request_id=getattr(request.state, "request_id", None),
            ip_address=_client_ip(request),
        )
    )
    return Envelope(data={"changed": True, "sessions_revoked": revoked})
