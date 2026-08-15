"""Request-scoped dependencies: identity, authorization, and datastore handles.

Replaces the previous single static bearer token, which the frontend also
shipped to the browser via NEXT_PUBLIC_ARGUS_API_TOKEN — so the credential
guarding every endpoint was public to anyone who loaded the page, and the
control provided no security property at all (audit B-01).

Authentication is now a server-side session referenced by an httpOnly cookie.
The browser never holds a credential it could leak, and every request resolves
to a named person, which is what makes the audit log meaningful.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from neo4j import AsyncDriver

from app.database.neo4j import get_driver
from app.database.postgres import acquire
from app.observability.logging import actor_id_var
from app.security.roles import Permission, has_permission
from app.security.sessions import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    AuthenticatedUser,
    resolve_session,
)

# Methods that cannot change state, and so do not require a CSRF token.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_db() -> AsyncDriver:
    return get_driver()


async def get_pg() -> asyncpg.Connection:
    async with acquire() as conn:
        yield conn


async def current_user(
    request: Request, conn: asyncpg.Connection = Depends(get_pg)
) -> AuthenticatedUser:
    """Resolve the session cookie to a user, or 401.

    Also enforces CSRF on state-changing methods. Because authentication is now
    a cookie, the browser attaches it automatically to cross-site requests, so a
    double-submit token is required — this was not needed under the bearer-token
    scheme and is a direct consequence of the change.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Cookie"},
        )

    user = await resolve_session(conn, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
            headers={"WWW-Authenticate": "Cookie"},
        )

    if request.method not in _SAFE_METHODS:
        header_token = request.headers.get(CSRF_HEADER_NAME)
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        # Both must be present and equal. The cookie is readable by same-origin
        # JavaScript so the SPA can echo it; an attacker's page can cause the
        # cookie to be *sent* but cannot read it to set the header.
        if not header_token or not cookie_token or header_token != cookie_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing or invalid",
            )

    # Attach to the logging context so every line emitted while handling this
    # request names the person responsible for it.
    actor_id_var.set(str(user.id))
    request.state.user = user
    return user


def require_permission(permission: Permission) -> Callable[..., Awaitable[AuthenticatedUser]]:
    """Dependency factory enforcing a single permission.

    Denials are raised here but *audited* by the caller's route, which knows the
    resource being acted on. A permission check that fails silently would be
    indistinguishable from one that was never applied.
    """

    async def _dependency(user: AuthenticatedUser = Depends(current_user)) -> AuthenticatedUser:
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' lacks permission '{permission.value}'",
            )
        return user

    return _dependency
