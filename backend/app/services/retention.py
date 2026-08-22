"""Automated disposal of exports whose retention period has elapsed.

## What is disposed of, and what is never

Only the **content** of an export, and only after the schedule its
classification set at the moment it was produced. The row survives: who
requested it, when, why, what its hash was, and every access to it.

Nothing else in ARGUS is on a retention schedule, and that is a decision rather
than an omission:

  - the **audit log** records what people did, and a system that expires its own
    accountability trail has implemented forgetting;
  - **provenance** records where every value came from, and disposing of it would
    leave conclusions standing with no traceable basis;
  - **investigation history** is the record a review reads, and it is append-only
    for the reasons Phase 9 gives.

A retention policy that quietly ate any of those would look like compliance and
function as evidence destruction.

## Why this is safe to run in every instance

The disposal statement is guarded on `disposed_at IS NULL` and the trigger in
migration 010 refuses a second disposal outright, so two instances ticking at
the same moment produce one disposal and one no-op. The same argument the ingest
scheduler makes: a database guarantee rather than leader election.
"""

from __future__ import annotations

import logging

from app.repositories import export_repo

logger = logging.getLogger(__name__)

__all__ = ["dispose_due_exports"]


async def dispose_due_exports(limit: int = 500) -> int:
    """Destroy the content of every export past its retention date.

    Returns how many were disposed of. Bounded per tick so a large backlog is
    worked through over several ticks rather than in one long transaction that
    holds locks on a table analysts are reading.
    """
    disposed = await export_repo.dispose_expired(limit=limit)
    for row in disposed:
        # Logged individually. A disposal is the destruction of evidence by
        # design, and "5 exports disposed" in a log is not something anybody can
        # reconcile against a register six months later.
        logger.info(
            "export content disposed",
            extra={
                "export_id": str(row["export_id"]),
                "classification": row["classification"],
                "requested_by": row["requested_by"],
                "content_sha256": row["content_sha256"],
            },
        )
    return len(disposed)
