"""Operational commands that must exist outside the API.

Bootstrapping the first administrator is the obvious one: authentication now
guards every endpoint, so without an out-of-band way to create the first
account, a fresh deployment has nobody who can log in and no way to fix that
through the product.

Run as:  python -m app.cli create-user --username alice --role administrator
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys

from app.database.pg_migrations import run_pg_migrations
from app.database.postgres import close_postgres, connect_postgres, transaction
from app.repositories import user_repo
from app.security.passwords import WeakPassword
from app.security.roles import Role
from app.services import audit


async def _create_user(username: str, display_name: str, role: str, password: str | None) -> int:
    await run_pg_migrations()
    await connect_postgres()
    try:
        # One transaction around the create *and* its audit record. Without it,
        # a failing audit write leaves a user account that no log accounts for —
        # which is exactly what happened the first time this ran, and exactly
        # the gap the audit log exists to close.
        async with transaction() as conn:
            if await user_repo.get_by_username(conn, username) is not None:
                print(f"error: user {username!r} already exists", file=sys.stderr)
                return 1

            # Read from the environment or prompt — never from argv, which is
            # world-readable via /proc and ps for the life of the process.
            secret = password or os.environ.get("ARGUS_NEW_USER_PASSWORD")
            if not secret:
                secret = getpass.getpass("Password: ")
                if secret != getpass.getpass("Confirm password: "):
                    print("error: passwords do not match", file=sys.stderr)
                    return 1

            try:
                user = await user_repo.create_user(conn, username, display_name, secret, Role(role))
            except WeakPassword as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1

            await audit.record(
                audit.AuditEvent(
                    action="user.create",
                    outcome="success",
                    actor_username="cli",
                    resource_type="User",
                    resource_id=str(user.id),
                    after_state={"username": user.username, "role": user.role},
                    detail="created via command line",
                ),
                conn=conn,
            )

        print(f"created {user.username} ({user.role})")
        return 0
    finally:
        await close_postgres()


async def _verify_audit() -> int:
    await connect_postgres()
    try:
        result = await audit.verify_chain()
        print(result.detail)
        if not result.ok:
            print(f"first broken entry: seq {result.first_broken_seq}", file=sys.stderr)
            return 1
        return 0
    finally:
        await close_postgres()


async def _backfill_provenance(labels: list[str] | None, dry_run: bool) -> int:
    """Attribute the existing graph to the source that produced it.

    An operator command rather than a startup step: it writes one row per node,
    and a schema migration that silently rewrites twenty thousand records on
    deploy is the kind of thing that should require somebody to type it.

    Safe to re-run. Observations deduplicate on content hash and risk assertions
    skip subjects that already have one, so a second run adds only what is new —
    which matters, because a backfill that doubled its output would double every
    corroboration count with it.
    """
    from app.database.neo4j import close_neo4j, connect_neo4j
    from app.repositories import provenance_repo
    from app.services import provenance as provenance_service

    await run_pg_migrations()
    await connect_postgres()
    driver = await connect_neo4j()
    try:
        before = await provenance_repo.counts()
        if dry_run:
            print("current provenance store:")
            for key, value in before.items():
                print(f"  {key:24} {value:>8,}")
            print("\n--dry-run: nothing written")
            return 0

        result = await provenance_service.backfill_graph_provenance(driver, labels=labels)
        after = await provenance_repo.counts()

        print("backfill complete")
        for key, value in result.as_dict().items():
            print(f"  {key:24} {value:>8,}")
        print("\nprovenance store:")
        for key, value in after.items():
            print(f"  {key:24} {before[key]:>8,} -> {value:>8,}")
        return 0
    finally:
        await close_neo4j()
        await close_postgres()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="ARGUS operations")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user", help="Create a user account")
    create.add_argument("--username", required=True)
    create.add_argument("--display-name", default=None)
    create.add_argument(
        "--role", required=True, choices=[r.value for r in Role], help="Role to grant"
    )
    # Deliberately no --password flag. Supply ARGUS_NEW_USER_PASSWORD or be
    # prompted; a password on a command line is visible to every local user.

    sub.add_parser("verify-audit", help="Recompute and verify the audit hash chain")

    backfill = sub.add_parser(
        "backfill-provenance",
        help="Attribute existing graph nodes to the source that produced them",
    )
    backfill.add_argument(
        "--label",
        action="append",
        dest="labels",
        help="Restrict to one graph label; repeatable. Omit for every label.",
    )
    backfill.add_argument(
        "--dry-run", action="store_true", help="Report current counts and write nothing"
    )

    args = parser.parse_args()

    if args.command == "create-user":
        return asyncio.run(
            _create_user(args.username, args.display_name or args.username, args.role, None)
        )
    if args.command == "verify-audit":
        return asyncio.run(_verify_audit())
    if args.command == "backfill-provenance":
        return asyncio.run(_backfill_provenance(args.labels, args.dry_run))
    return 1  # pragma: no cover - argparse rejects unknown commands


if __name__ == "__main__":
    sys.exit(main())
