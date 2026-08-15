"""Append-only, hash-chained audit log.

Before this, ARGUS could not answer "who changed this alert's status, and when?"
— not because logging was missing, but because there were no identities to
attribute an action to. That made it a structural gap rather than a feature gap
(audit G-04).

Two properties, layered:

  1. **Append-only, enforced by the database.** The application role holds INSERT
     and SELECT on `audit_events` and nothing else, and triggers reject UPDATE,
     DELETE and TRUNCATE for every role. Erasing a record requires
     superuser access *and* explicitly disabling a trigger.
  2. **Hash-chained.** Each row carries the hash of its predecessor. Removing or
     altering a row breaks the chain from that point on, and the break is
     detectable by recomputation — so even an attacker who defeats (1) leaves
     evidence.

Audit writes share the caller's transaction wherever a transaction exists, so a
mutation and its audit record commit or roll back together. An action that
succeeded while its record was lost is precisely the gap the log exists to close.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

from app.database.postgres import acquire

logger = logging.getLogger(__name__)

# The chain's fixed starting point. The first row's prev_hash is this value.
GENESIS_HASH = "0" * 64

# Arbitrary but fixed key identifying the audit-chain advisory lock. Any writer
# taking this lock serialises against every other, which is what keeps the chain
# linear.
_AUDIT_CHAIN_LOCK_KEY = 0x41524755  # "ARGU"


class AuditWriteFailed(RuntimeError):
    """Raised when an audit record cannot be written.

    Callers must let this propagate and fail the request. Completing a mutation
    whose audit record failed would leave an unattributable change, which is
    worse than the request failing.
    """


@dataclass(frozen=True)
class AuditEvent:
    action: str
    outcome: str  # 'success' | 'denied' | 'failure'
    actor_id: uuid.UUID | None = None
    actor_username: str | None = None
    actor_role: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    request_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    detail: str | None = None


def compute_entry_hash(
    *,
    prev_hash: str,
    event_id: uuid.UUID,
    occurred_at: datetime,
    action: str,
    outcome: str,
    actor_id: uuid.UUID | None,
    resource_type: str | None,
    resource_id: str | None,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
) -> str:
    """Hash over the fields that carry the meaning of the event.

    Field order and separators are fixed, and payloads are serialised with
    sorted keys, so the hash is reproducible by an independent verifier rather
    than dependent on Python's dict ordering at write time.
    """
    payload = "|".join(
        [
            prev_hash,
            str(event_id),
            occurred_at.isoformat(),
            action,
            outcome,
            str(actor_id) if actor_id else "",
            resource_type or "",
            resource_id or "",
            json.dumps(before_state, sort_keys=True, default=str) if before_state else "",
            json.dumps(after_state, sort_keys=True, default=str) if after_state else "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _latest_hash(conn: asyncpg.Connection) -> str:
    row = await conn.fetchrow("SELECT entry_hash FROM audit_events ORDER BY seq DESC LIMIT 1")
    return row["entry_hash"] if row else GENESIS_HASH


async def record(event: AuditEvent, conn: asyncpg.Connection | None = None) -> uuid.UUID:
    """Write one audit event. Returns its id.

    Pass `conn` to enlist in an existing transaction; omit it and the write gets
    its own connection.
    """
    if conn is not None:
        return await _record_on(conn, event)
    async with acquire() as own_conn:
        return await _record_on(own_conn, event)


async def _record_on(conn: asyncpg.Connection, event: AuditEvent) -> uuid.UUID:
    event_id = uuid.uuid4()
    try:
        # The chain read and the insert must be atomic together, or two writers
        # could read the same predecessor and the chain would fork. When the
        # caller already has a transaction — the mutation-and-audit-together
        # case — asyncpg nests this as a savepoint, so the audit write still
        # commits or rolls back with the change it describes.
        async with conn.transaction():
            return await _insert_chained(conn, event, event_id)
    except Exception as exc:
        logger.critical(
            "AUDIT WRITE FAILED — request must not be allowed to succeed",
            exc_info=exc,
            extra={"action": event.action, "resource_id": event.resource_id},
        )
        raise AuditWriteFailed(f"Could not record audit event {event.action!r}") from exc


async def _insert_chained(
    conn: asyncpg.Connection, event: AuditEvent, event_id: uuid.UUID
) -> uuid.UUID:
    # A transaction-scoped advisory lock, not LOCK TABLE.
    #
    # LOCK TABLE in any mode above ACCESS SHARE requires UPDATE, DELETE or
    # TRUNCATE privilege — which the application role deliberately does not
    # have, and must not be given just to serialise writers. An advisory lock
    # needs no table privileges at all, serialises equally well, and releases
    # automatically when the transaction ends, so a crashed writer cannot wedge
    # the log.
    await conn.execute("SELECT pg_advisory_xact_lock($1)", _AUDIT_CHAIN_LOCK_KEY)

    prev_hash = await _latest_hash(conn)
    occurred_at = await conn.fetchval("SELECT now()")
    entry_hash = compute_entry_hash(
        prev_hash=prev_hash,
        event_id=event_id,
        occurred_at=occurred_at,
        action=event.action,
        outcome=event.outcome,
        actor_id=event.actor_id,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        before_state=event.before_state,
        after_state=event.after_state,
    )

    await conn.execute(
        """
        INSERT INTO audit_events (
            id, occurred_at, actor_id, actor_username, actor_role,
            action, resource_type, resource_id, outcome,
            before_state, after_state,
            request_id, ip_address, user_agent, detail,
            prev_hash, entry_hash
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9,
            $10::jsonb, $11::jsonb, $12, $13::inet, $14, $15, $16, $17
        )
        """,
        event_id,
        occurred_at,
        event.actor_id,
        event.actor_username,
        event.actor_role,
        event.action,
        event.resource_type,
        event.resource_id,
        event.outcome,
        json.dumps(event.before_state, default=str) if event.before_state else None,
        json.dumps(event.after_state, default=str) if event.after_state else None,
        event.request_id,
        event.ip_address,
        event.user_agent,
        event.detail,
        prev_hash,
        entry_hash,
    )
    return event_id


@dataclass(frozen=True)
class ChainVerification:
    ok: bool
    checked: int
    first_broken_seq: int | None
    detail: str


async def verify_chain(limit: int | None = None) -> ChainVerification:
    """Recompute the chain and report the first break.

    This is what makes the log tamper-*evident* rather than merely
    tamper-resistant: it detects alteration performed by someone who bypassed
    the triggers entirely.
    """
    query = """
        SELECT seq, id, occurred_at, action, outcome, actor_id,
               resource_type, resource_id, before_state, after_state,
               prev_hash, entry_hash
        FROM audit_events ORDER BY seq ASC
    """
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    async with acquire() as conn:
        rows = await conn.fetch(query)

    expected_prev = GENESIS_HASH
    for row in rows:
        if row["prev_hash"] != expected_prev:
            return ChainVerification(
                ok=False,
                checked=len(rows),
                first_broken_seq=row["seq"],
                detail=(
                    f"Row {row['seq']} expects predecessor {expected_prev[:12]}… "
                    f"but records {row['prev_hash'][:12]}… — a row was removed or reordered."
                ),
            )

        recomputed = compute_entry_hash(
            prev_hash=row["prev_hash"],
            event_id=row["id"],
            occurred_at=row["occurred_at"],
            action=row["action"],
            outcome=row["outcome"],
            actor_id=row["actor_id"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            before_state=json.loads(row["before_state"]) if row["before_state"] else None,
            after_state=json.loads(row["after_state"]) if row["after_state"] else None,
        )
        if recomputed != row["entry_hash"]:
            return ChainVerification(
                ok=False,
                checked=len(rows),
                first_broken_seq=row["seq"],
                detail=f"Row {row['seq']} contents do not match its recorded hash — it was altered.",
            )
        expected_prev = row["entry_hash"]

    return ChainVerification(
        ok=True, checked=len(rows), first_broken_seq=None, detail=f"{len(rows)} entries verified."
    )
