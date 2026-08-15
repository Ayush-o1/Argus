"""User records and authentication attempts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

import asyncpg

from app.config import get_settings
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.roles import Role


@dataclass(frozen=True)
class UserRecord:
    id: uuid.UUID
    username: str
    display_name: str
    role: str
    is_active: bool
    mfa_enrolled: bool


class AuthOutcome(StrEnum):
    """Why a login attempt ended as it did.

    Distinguished internally for the audit log; the API deliberately collapses
    them all into one opaque message, so a caller cannot learn whether a
    username exists or whether an account is locked.
    """

    SUCCESS = "success"
    BAD_CREDENTIALS = "bad_credentials"
    LOCKED = "locked"
    INACTIVE = "inactive"
    MFA_REQUIRED = "mfa_required"
    MFA_INVALID = "mfa_invalid"


async def get_by_username(conn: asyncpg.Connection, username: str) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT id, username, display_name, password_hash, role, is_active,
               mfa_secret, mfa_enrolled, failed_logins, locked_until
        FROM users WHERE lower(username) = lower($1)
        """,
        username,
    )


async def get_by_id(conn: asyncpg.Connection, user_id: uuid.UUID) -> UserRecord | None:
    row = await conn.fetchrow(
        "SELECT id, username, display_name, role, is_active, mfa_enrolled FROM users WHERE id = $1",
        user_id,
    )
    return _to_record(row) if row else None


async def list_users(conn: asyncpg.Connection) -> list[UserRecord]:
    rows = await conn.fetch(
        """
        SELECT id, username, display_name, role, is_active, mfa_enrolled
        FROM users ORDER BY username
        """
    )
    return [_to_record(r) for r in rows]


def _to_record(row: asyncpg.Record) -> UserRecord:
    return UserRecord(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        role=row["role"],
        is_active=row["is_active"],
        mfa_enrolled=row["mfa_enrolled"],
    )


async def create_user(
    conn: asyncpg.Connection,
    username: str,
    display_name: str,
    password: str,
    role: Role,
) -> UserRecord:
    user_id = uuid.uuid4()
    await conn.execute(
        """
        INSERT INTO users (id, username, display_name, password_hash, role)
        VALUES ($1, $2, $3, $4, $5)
        """,
        user_id,
        username,
        display_name,
        hash_password(password),
        role.value,
    )
    created = await get_by_id(conn, user_id)
    assert created is not None, "user was just inserted"
    return created


def is_locked(row: asyncpg.Record) -> bool:
    locked_until = row["locked_until"]
    return locked_until is not None and locked_until > datetime.now(UTC)


async def register_failed_login(conn: asyncpg.Connection, user_id: uuid.UUID) -> None:
    """Increment the failure counter and lock the account at the threshold.

    Lockout is per-account rather than per-IP: an attacker distributing attempts
    across addresses would otherwise never trip it. The tradeoff is that an
    attacker can deliberately lock a known account, which is why the window is
    short and self-clearing rather than requiring an administrator.
    """
    settings = get_settings()
    await conn.execute(
        """
        UPDATE users
        SET failed_logins = failed_logins + 1,
            locked_until = CASE
                WHEN failed_logins + 1 >= $2 THEN now() + ($3 || ' minutes')::interval
                ELSE locked_until
            END,
            updated_at = now()
        WHERE id = $1
        """,
        user_id,
        settings.max_failed_logins,
        str(settings.lockout_minutes),
    )


async def register_successful_login(
    conn: asyncpg.Connection, user_id: uuid.UUID, password: str, password_hash: str
) -> None:
    """Clear the failure state, and transparently upgrade a stale password hash."""
    new_hash = hash_password(password) if needs_rehash(password_hash) else None
    if new_hash is not None:
        await conn.execute(
            """
            UPDATE users SET failed_logins = 0, locked_until = NULL,
                             password_hash = $2, password_changed_at = now(), updated_at = now()
            WHERE id = $1
            """,
            user_id,
            new_hash,
        )
    else:
        await conn.execute(
            "UPDATE users SET failed_logins = 0, locked_until = NULL, updated_at = now() WHERE id = $1",
            user_id,
        )


async def set_password(conn: asyncpg.Connection, user_id: uuid.UUID, password: str) -> None:
    await conn.execute(
        """
        UPDATE users SET password_hash = $2, password_changed_at = now(),
                         failed_logins = 0, locked_until = NULL, updated_at = now()
        WHERE id = $1
        """,
        user_id,
        hash_password(password),
    )


async def set_active(conn: asyncpg.Connection, user_id: uuid.UUID, active: bool) -> None:
    await conn.execute(
        "UPDATE users SET is_active = $2, updated_at = now() WHERE id = $1", user_id, active
    )


async def authenticate(
    conn: asyncpg.Connection, username: str, password: str
) -> tuple[AuthOutcome, asyncpg.Record | None]:
    """Verify a username and password.

    Always performs a password verification — even when the user does not exist
    — so response timing does not reveal whether an account is present.
    """
    row = await get_by_username(conn, username)

    if row is None:
        verify_password(password, None)
        return AuthOutcome.BAD_CREDENTIALS, None

    if is_locked(row):
        # Still verify, so a locked account is not distinguishable by timing.
        verify_password(password, row["password_hash"])
        return AuthOutcome.LOCKED, row

    if not verify_password(password, row["password_hash"]):
        await register_failed_login(conn, row["id"])
        return AuthOutcome.BAD_CREDENTIALS, row

    if not row["is_active"]:
        return AuthOutcome.INACTIVE, row

    if row["mfa_enrolled"]:
        return AuthOutcome.MFA_REQUIRED, row

    return AuthOutcome.SUCCESS, row
