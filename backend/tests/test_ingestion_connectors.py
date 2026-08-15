"""Connector behaviour, with the security controls that matter most.

Connector configuration is administrator-supplied, so it is *trusted-ish*. That
is not a reason to let a config string read `/etc` or reach the cloud metadata
endpoint — an SSRF or a path escape through a config field is exactly the kind
that gets written off as "but only admins can set it" until an admin account is
the thing that was compromised.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.base import ConnectorConfigError, ConnectorError, build_connector
from app.ingestion.connectors import INGEST_ROOT_ENV, FilesystemConnector, _assert_safe_url


@pytest.fixture
def ingest_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "ingest"
    (root / "feed").mkdir(parents=True)
    monkeypatch.setenv(INGEST_ROOT_ENV, str(root))
    return root


# ── Filesystem connector ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reads_json_lines(ingest_root: Path) -> None:
    (ingest_root / "feed" / "a.jsonl").write_text(
        json.dumps({"id": 1}) + "\n" + json.dumps({"id": 2})
    )
    connector = FilesystemConnector("c", {"directory": "feed"})
    result = await connector.fetch(None)
    assert [r.payload["id"] for r in result.records] == [1, 2]
    assert result.cursor is not None


@pytest.mark.asyncio
async def test_reads_a_json_array_and_a_single_object(ingest_root: Path) -> None:
    (ingest_root / "feed" / "arr.json").write_text(json.dumps([{"id": 1}, {"id": 2}]))
    (ingest_root / "feed" / "one.json").write_text(json.dumps({"id": 3}))
    connector = FilesystemConnector("c", {"directory": "feed"})
    result = await connector.fetch(None)
    assert sorted(r.payload["id"] for r in result.records) == [1, 2, 3]


@pytest.mark.asyncio
async def test_the_cursor_stops_a_file_being_read_twice(ingest_root: Path) -> None:
    """Without this, every poll re-reads the whole folder. Content hashing would
    still deduplicate downstream, but only after paying to parse and hash
    everything again on every tick."""
    (ingest_root / "feed" / "a.json").write_text(json.dumps({"id": 1}))
    connector = FilesystemConnector("c", {"directory": "feed"})
    first = await connector.fetch(None)
    assert len(first.records) == 1
    second = await connector.fetch(first.cursor)
    assert second.records == []


@pytest.mark.asyncio
async def test_malformed_json_raises_rather_than_being_skipped(ingest_root: Path) -> None:
    """A file that cannot be parsed is a failure to report, not a file to pass
    over. Skipping it silently is how a broken export becomes an intelligence
    gap nobody knows about."""
    (ingest_root / "feed" / "bad.json").write_text("{not json")
    connector = FilesystemConnector("c", {"directory": "feed"})
    with pytest.raises(ConnectorError, match="not valid JSON"):
        await connector.fetch(None)


@pytest.mark.asyncio
async def test_a_directory_outside_the_ingest_root_is_refused(ingest_root: Path) -> None:
    """The path-escape guard. `..` and absolute paths both resolve before the
    containment check, because checking the raw string would miss exactly the
    inputs that matter."""
    for directory in ("../../etc", "/etc", "feed/../../.."):
        connector = FilesystemConnector("c", {"directory": directory})
        with pytest.raises(ConnectorConfigError, match="outside the permitted ingest root"):
            await connector.fetch(None)


@pytest.mark.asyncio
async def test_a_symlink_out_of_the_root_is_refused(ingest_root: Path, tmp_path: Path) -> None:
    """Resolution happens before the check, so a symlink cannot smuggle a path
    past it."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (ingest_root / "escape").symlink_to(outside)
    connector = FilesystemConnector("c", {"directory": "escape"})
    with pytest.raises(ConnectorConfigError, match="outside the permitted ingest root"):
        await connector.fetch(None)


@pytest.mark.asyncio
async def test_a_missing_directory_is_a_config_error_not_a_retry(ingest_root: Path) -> None:
    """ConnectorConfigError signals "do not retry": no number of attempts
    conjures a directory, and a connector retrying forever is noise that hides
    real failures."""
    connector = FilesystemConnector("c", {"directory": "nope"})
    with pytest.raises(ConnectorConfigError):
        await connector.fetch(None)


@pytest.mark.asyncio
async def test_directory_is_required(ingest_root: Path) -> None:
    with pytest.raises(ConnectorConfigError, match="requires `directory`"):
        await FilesystemConnector("c", {}).fetch(None)


# ── SSRF guard on the HTTP connector ─────────────────────────────────────────


def test_private_and_loopback_hosts_are_refused() -> None:
    """A feed URL pointing at 169.254.169.254 or localhost is server-side
    request forgery with extra steps. Blocked by default; the escape hatch is an
    environment variable, so its presence is visible in a deployment rather than
    buried in a config row."""
    for url in (
        "http://localhost:8000/feed",
        "http://127.0.0.1/feed",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/feed",
        "http://192.168.1.10/feed",
    ):
        with pytest.raises(ConnectorConfigError):
            _assert_safe_url(url)


def test_private_hosts_are_allowed_when_explicitly_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGUS_ALLOW_PRIVATE_INGEST_HOSTS", "true")
    _assert_safe_url("http://10.0.0.5/feed")


def test_non_http_schemes_are_refused() -> None:
    """`file://` would turn a feed URL into an arbitrary file read."""
    for url in ("file:///etc/passwd", "ftp://example.com/x", "gopher://example.com"):
        with pytest.raises(ConnectorConfigError):
            _assert_safe_url(url)


# ── Registry and credentials ─────────────────────────────────────────────────


def test_unknown_connector_type_names_what_is_available() -> None:
    with pytest.raises(ConnectorConfigError, match="Registered:"):
        build_connector("does-not-exist", "c", {})


def test_secrets_are_read_from_the_environment_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """A credential in the connectors table is a credential in every backup and
    replica. Config may *name* an environment variable; it may not carry the
    value."""
    monkeypatch.setenv("TEST_FEED_TOKEN", "s3cret")
    connector = FilesystemConnector("c", {"token_env": "TEST_FEED_TOKEN"})
    assert connector.secret("token") == "s3cret"
    assert FilesystemConnector("c", {"token": "s3cret"}).secret("token") is None


def test_describe_never_echoes_anything_credential_shaped() -> None:
    connector = FilesystemConnector(
        "c", {"directory": "feed", "api_key": "leak", "token_env": "X", "password": "leak"}
    )
    described = connector.describe()
    assert described == {"directory": "feed"}
