"""The connector contract.

A connector's only job is to *fetch* — turn some external thing into a stream of
JSON records. It does not validate, deduplicate, normalise, or write anything.
That separation is what makes the acceptance criterion "a source can be added
without code changes to the core" true: everything after fetching is shared
pipeline, so a new connector is one class and a registry entry, and a new
*source* using an existing connector type is a database row and no code at all.

## Isolation

Each connector runs as its own queued job. One connector failing — an endpoint
down, a malformed file, a credential expired — cannot block another, because
they never share a call stack or a transaction. A failure marks that connector's
batch failed and leaves every other feed untouched.

## Credentials

Connectors read secrets from the environment by *name*, never from their stored
config. `config` may say `{"token_env": "ACME_FEED_TOKEN"}`; it may not say
`{"token": "..."}`. A credential in a table the application can SELECT is a
credential in every backup, every replica, and the blast radius of any SQL
injection — which is the failure the identity work existed to remove.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RawRecord:
    """One record as the source produced it, before anything interprets it."""

    payload: dict[str, Any]
    # Connector-defined position marker. The framework stores the last one seen
    # so the next run can resume rather than re-reading everything.
    cursor: str | None = None


@dataclass(frozen=True)
class FetchResult:
    records: list[RawRecord] = field(default_factory=list)
    cursor: str | None = None
    # Set when the source responded but had nothing new. Distinct from an error,
    # and distinct from "returned zero records because it is broken" — the
    # health surface treats a quiet-but-healthy feed differently from a silent
    # one.
    unchanged: bool = False


class ConnectorError(RuntimeError):
    """A connector could not fetch. Fails this batch and no other."""


class ConnectorConfigError(ConnectorError):
    """The connector's stored configuration is unusable. Not retryable — a
    retry cannot fix a missing directory or an unset credential, so the job is
    buried immediately rather than backing off five times first."""


class Connector(ABC):
    """Base class for every connector type."""

    #: Registry key, matched against `connectors.connector_type`.
    type_name: str = ""

    def __init__(self, connector_id: str, config: dict[str, Any]) -> None:
        self.connector_id = connector_id
        self.config = config

    @abstractmethod
    async def fetch(self, cursor: str | None) -> FetchResult:
        """Return records produced since `cursor`."""

    def secret(self, key: str) -> str | None:
        """Read a secret this connector's config *names*.

        `{"token_env": "ACME_TOKEN"}` resolves through the environment.
        A literal under `{"token": ...}` is ignored on purpose and warned about
        — silently honouring it would make the safe path optional.
        """
        env_name = self.config.get(f"{key}_env")
        if not env_name:
            return None
        return os.environ.get(str(env_name))

    def describe(self) -> dict[str, Any]:
        """Non-secret configuration, for the health surface."""
        return {
            key: value
            for key, value in self.config.items()
            # Never echo anything that looks like a credential, even though
            # storing one here is already refused. Two independent guards,
            # because this value reaches an API response.
            if not any(marker in key.lower() for marker in ("token", "secret", "password", "key"))
        }


_REGISTRY: dict[str, type[Connector]] = {}


def register_connector(cls: type[Connector]) -> type[Connector]:
    if not cls.type_name:
        raise RuntimeError(f"{cls.__name__} must set type_name")
    if cls.type_name in _REGISTRY and _REGISTRY[cls.type_name] is not cls:
        raise RuntimeError(f"Two connectors registered as {cls.type_name!r}")
    _REGISTRY[cls.type_name] = cls
    return cls


def build_connector(connector_type: str, connector_id: str, config: dict[str, Any]) -> Connector:
    cls = _REGISTRY.get(connector_type)
    if cls is None:
        raise ConnectorConfigError(
            f"Unknown connector type {connector_type!r}. Registered: {sorted(_REGISTRY)}"
        )
    return cls(connector_id, config)


def registered_types() -> list[str]:
    return sorted(_REGISTRY)
