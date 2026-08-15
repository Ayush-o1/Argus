"""The connector implementations that ship with ARGUS.

Two, deliberately: a filesystem drop folder and an HTTP JSON poller. Between
them they cover how most real feeds actually arrive, and neither invents a
dependency on a service that does not exist. A third connector is a subclass and
a registry entry; a third *source* using either of these is a database row.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.ingestion.base import (
    Connector,
    ConnectorConfigError,
    ConnectorError,
    FetchResult,
    RawRecord,
    register_connector,
)

logger = logging.getLogger(__name__)

# Every filesystem connector is confined beneath this root. Connector config is
# administrator-supplied and therefore trusted-ish, but "trusted-ish" is not a
# reason to let a config string read /etc or a mounted secret. One env var makes
# the boundary explicit and auditable.
INGEST_ROOT_ENV = "ARGUS_INGEST_ROOT"
_DEFAULT_INGEST_ROOT = "/var/lib/argus/ingest"

MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_RECORDS_PER_BATCH = 5_000


def _ingest_root() -> Path:
    return Path(os.environ.get(INGEST_ROOT_ENV, _DEFAULT_INGEST_ROOT)).resolve()


@register_connector
class FilesystemConnector(Connector):
    """Reads `.json` / `.jsonl` files from a directory.

    The workhorse for anything delivered as a file drop — an export, an SFTP
    landing zone, a partner's nightly dump. Files are read, never moved or
    deleted: the connector's memory is the cursor, so a file re-appearing does
    not re-ingest (content hashing catches it downstream anyway), and ARGUS
    never destroys something it did not create.

    Config:
        `directory` — path, resolved beneath ARGUS_INGEST_ROOT
        `pattern`   — glob, default `*.json*`
    """

    type_name = "filesystem"

    def _directory(self) -> Path:
        raw = self.config.get("directory")
        if not raw:
            raise ConnectorConfigError("filesystem connector requires `directory`")

        root = _ingest_root()
        # Resolve *then* check containment. Checking the unresolved string would
        # miss `..` segments and symlinks, which is the whole attack.
        candidate = (root / str(raw)).resolve() if not str(raw).startswith("/") else Path(str(raw)).resolve()
        if candidate != root and root not in candidate.parents:
            raise ConnectorConfigError(
                f"directory {candidate} is outside the permitted ingest root {root}. "
                f"Set {INGEST_ROOT_ENV} if this location is intended."
            )
        if not candidate.is_dir():
            raise ConnectorConfigError(f"directory {candidate} does not exist or is not a directory")
        return candidate

    async def fetch(self, cursor: str | None) -> FetchResult:
        directory = self._directory()
        pattern = str(self.config.get("pattern", "*.json*"))

        # Blocking file IO off the event loop. A large drop folder on a slow
        # disk would otherwise stall every request the API is serving.
        return await asyncio.to_thread(self._read, directory, pattern, cursor)

    def _read(self, directory: Path, pattern: str, cursor: str | None) -> FetchResult:
        since = float(cursor) if cursor else 0.0
        newest = since
        records: list[RawRecord] = []

        for path in sorted(directory.glob(pattern)):
            if not path.is_file():
                continue
            stat = path.stat()
            if stat.st_mtime <= since:
                continue
            if stat.st_size > MAX_FILE_BYTES:
                raise ConnectorError(
                    f"{path.name} is {stat.st_size} bytes, above the {MAX_FILE_BYTES} limit. "
                    "Split it or raise the limit deliberately."
                )

            for payload in self._parse(path):
                records.append(RawRecord(payload=payload, cursor=str(stat.st_mtime)))
                if len(records) >= MAX_RECORDS_PER_BATCH:
                    # Stop at the ceiling rather than reading an unbounded
                    # folder into memory. The cursor is not advanced past this
                    # file, so the next run resumes here.
                    logger.info(
                        "batch ceiling reached; remaining files deferred to the next run",
                        extra={"connector_id": self.connector_id, "records": len(records)},
                    )
                    return FetchResult(records=records, cursor=str(newest))

            newest = max(newest, stat.st_mtime)

        return FetchResult(
            records=records, cursor=str(newest), unchanged=not records and newest == since
        )

    def _parse(self, path: Path) -> list[dict[str, Any]]:
        text = path.read_text(encoding="utf-8", errors="replace")
        try:
            if path.suffix == ".jsonl" or "\n" in text.strip() and text.lstrip()[:1] != "[":
                out = []
                for line_number, line in enumerate(text.splitlines(), start=1):
                    line = line.strip()
                    if not line:
                        continue
                    parsed = json.loads(line)
                    if not isinstance(parsed, dict):
                        raise ConnectorError(
                            f"{path.name}:{line_number} is a {type(parsed).__name__}, not an object"
                        )
                    out.append(parsed)
                return out

            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConnectorError(f"{path.name} is not valid JSON: {exc}") from exc

        if isinstance(parsed, dict):
            return [parsed]
        if isinstance(parsed, list):
            objects = [item for item in parsed if isinstance(item, dict)]
            if len(objects) != len(parsed):
                raise ConnectorError(f"{path.name} contains non-object entries")
            return objects
        raise ConnectorError(f"{path.name} is a {type(parsed).__name__}, not an object or array")


@register_connector
class HttpJsonConnector(Connector):
    """Polls an HTTP endpoint returning JSON.

    Config:
        `url`            — endpoint
        `records_path`   — dotted path to the array, e.g. `data.items`; omit if
                           the body is already an array
        `cursor_param`   — query parameter to send the cursor as
        `cursor_path`    — dotted path to the next cursor in the response
        `token_env`      — env var holding a bearer token, if the feed needs one
        `timeout`        — seconds, default 30
    """

    type_name = "http_json"

    async def fetch(self, cursor: str | None) -> FetchResult:
        url = str(self.config.get("url") or "")
        if not url:
            raise ConnectorConfigError("http_json connector requires `url`")
        _assert_safe_url(url)

        params: dict[str, str] = dict(self.config.get("params") or {})
        cursor_param = self.config.get("cursor_param")
        if cursor and cursor_param:
            params[str(cursor_param)] = cursor

        headers = {"Accept": "application/json"}
        token = self.secret("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif self.config.get("token"):
            logger.warning(
                "connector config contains a literal `token`; ignored. Use `token_env` — a "
                "credential in the connectors table is a credential in every backup.",
                extra={"connector_id": self.connector_id},
            )

        timeout = float(self.config.get("timeout", 30))
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise ConnectorError(f"request to {url} failed: {exc}") from exc

        if response.status_code == 304:
            return FetchResult(unchanged=True, cursor=cursor)
        if response.status_code >= 400:
            raise ConnectorError(f"{url} returned {response.status_code}")

        try:
            body = response.json()
        except ValueError as exc:
            raise ConnectorError(f"{url} did not return JSON: {exc}") from exc

        raw_items = _dig(body, self.config.get("records_path")) if self.config.get("records_path") else body
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        if not isinstance(raw_items, list):
            raise ConnectorError(
                f"expected an array at records_path={self.config.get('records_path')!r}, "
                f"got {type(raw_items).__name__}"
            )
        if len(raw_items) > MAX_RECORDS_PER_BATCH:
            raise ConnectorError(
                f"{url} returned {len(raw_items)} records, above the {MAX_RECORDS_PER_BATCH} "
                "ceiling. Use pagination via cursor_param/cursor_path."
            )

        next_cursor = (
            str(_dig(body, self.config["cursor_path"]))
            if self.config.get("cursor_path") and _dig(body, self.config["cursor_path"]) is not None
            else cursor
        )
        records = [
            RawRecord(payload=item, cursor=next_cursor)
            for item in raw_items
            if isinstance(item, dict)
        ]
        return FetchResult(records=records, cursor=next_cursor, unchanged=not records)


def _dig(body: Any, path: str | None) -> Any:
    if not path:
        return body
    current = body
    for part in str(path).split("."):
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


# Hosts a feed URL may never point at. An administrator configuring a connector
# is trusted to name an external service, not to reach the cloud metadata
# endpoint or something bound to loopback inside this network — and SSRF through
# a config field is exactly how that happens by accident.
_BLOCKED_HOSTNAMES = frozenset({"localhost", "metadata.google.internal"})


def _assert_safe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ConnectorConfigError(f"unsupported scheme {parsed.scheme!r}; use http or https")

    host = parsed.hostname
    if not host:
        raise ConnectorConfigError("url has no host")
    if host.lower() in _BLOCKED_HOSTNAMES:
        raise ConnectorConfigError(f"host {host!r} is not permitted for a connector")

    if os.environ.get("ARGUS_ALLOW_PRIVATE_INGEST_HOSTS") == "true":
        # Escape hatch for a genuinely internal feed, off by default and named
        # so its presence is obvious in a deployment's environment.
        return

    try:
        resolved = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise ConnectorConfigError(f"could not resolve {host!r}: {exc}") from exc

    for address in resolved:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ConnectorConfigError(
                f"{host} resolves to {ip}, which is private, loopback or link-local. "
                "Set ARGUS_ALLOW_PRIVATE_INGEST_HOSTS=true if that is intended."
            )
