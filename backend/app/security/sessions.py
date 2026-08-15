"""Session issuance, validation and revocation.

The session token is a 256-bit random value sent to the browser in an httpOnly
cookie and stored server-side only as a SHA-256 hash. A database read — via
backup, replica, or a SQL flaw elsewhere — therefore yields no usable
credential, the same reasoning that applies to passwords.

Plain SHA-256 rather than Argon2 here, deliberately: the token is already 256
bits of entropy from a CSPRNG, so there is no dictionary to attack and the
slow-hash property buys nothing, while costing an Argon2 verification on every
single request.

Two independent expiries are enforced, and the shorter always wins:
  - **absolute** — a session cannot outlive this no matter how active it is,
    which bounds the damage from a stolen cookie.
  - **idle** — an unattended session dies even while inside the absolute window.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg

from app.config import get_settings

SESSION_COOKIE_NAME = "argus_session"
CSRF_COOKIE_NAME = "argus_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"

_TOKEN_BYTES = 32  # 256 bits


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    username: str
    display_name: str
    role: str
    session_id: uuid.UUID


def generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def create_session(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[str, uuid.UUID, datetime]:
    """Issue a session. Returns (raw_token, session_id, expires_at).

    The raw token is returned once, to be set as a cookie, and never stored.
    """
    settings = get_settings()
    token = generate_token()
    session_id = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(hours=settings.session_absolute_hours)

    await conn.execute(
        """
        INSERT INTO sessions (id, user_id, token_hash, expires_at, ip_address, user_agent)
        VALUES ($1, $2, $3, $4, $5::inet, $6)
        """,
        session_id,
        user_id,
        hash_token(token),
        expires_at,
        ip_address,
        user_agent,
    )
    return token, session_id, expires_at


async def resolve_session(conn: asyncpg.Connection, token: str) -> AuthenticatedUser | None:
    """Validate a token and return its user, or None.

    Every expiry and status condition is evaluated in SQL so a stale session can
    never be resolved by a code path that forgot one of them.
    """
    settings = get_settings()
    idle_cutoff = datetime.now(UTC) - timedelta(minutes=settings.session_idle_minutes)

    row = await conn.fetchrow(
        """
        SELECT s.id AS session_id, u.id AS user_id, u.username, u.display_name, u.role
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = $1
          AND s.revoked_at IS NULL
          AND s.expires_at > now()
          AND s.last_seen_at > $2
          AND u.is_active
        """,
        hash_token(token),
        idle_cutoff,
    )
    if row is None:
        return None

    # Sliding idle window. Only written when it has moved by more than a minute,
    # so a burst of requests does not turn every read into a write.
    await conn.execute(
        """
        UPDATE sessions SET last_seen_at = now()
        WHERE id = $1 AND last_seen_at < now() - interval '1 minute'
        """,
        row["session_id"],
    )

    return AuthenticatedUser(
        id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"],
        role=row["role"],
        session_id=row["session_id"],
    )


async def revoke_session(conn: asyncpg.Connection, session_id: uuid.UUID, reason: str) -> None:
    await conn.execute(
        """
        UPDATE sessions SET revoked_at = now(), revoked_reason = $2
        WHERE id = $1 AND revoked_at IS NULL
        """,
        session_id,
        reason,
    )


async def revoke_all_for_user(conn: asyncpg.Connection, user_id: uuid.UUID, reason: str) -> int:
    """Revoke every live session for a user.

    Used on password change and on deactivation: a credential change that leaves
    existing sessions alive has not actually revoked anything.
    """
    result = await conn.execute(
        """
        UPDATE sessions SET revoked_at = now(), revoked_reason = $2
        WHERE user_id = $1 AND revoked_at IS NULL
        """,
        user_id,
        reason,
    )
    return int(result.split()[-1]) if result.startswith("UPDATE") else 0


async def purge_expired(conn: asyncpg.Connection, older_than_days: int = 30) -> int:
    """Delete long-dead session rows. Housekeeping only — expiry is enforced by
    `resolve_session`, not by the presence or absence of a row."""
    result = await conn.execute(
        "DELETE FROM sessions WHERE expires_at < now() - ($1 || ' days')::interval",
        str(older_than_days),
    )
    return int(result.split()[-1]) if result.startswith("DELETE") else 0
