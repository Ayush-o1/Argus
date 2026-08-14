"""Structured JSON logging with request correlation.

Plain-text logs were unparseable and carried no way to tie lines together: a
single request fans out into several Neo4j queries across several modules, and
nothing linked them. Every record emitted here carries the request id of the
request that caused it, so one request's full path through the system can be
recovered with a single grep.

The context variable is set by RequestContextMiddleware and read here, rather
than threaded through every function signature — logging context is genuinely
ambient, and passing it explicitly would touch every call site to no benefit.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Set per-request by RequestContextMiddleware. Defaults cover logs emitted
# outside a request (startup, shutdown, background jobs).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
actor_id_var: ContextVar[str] = ContextVar("actor_id", default="-")

# LogRecord's own attributes, so `extra=` fields can be separated from them
# without maintaining a fragile allowlist.
_STANDARD_RECORD_FIELDS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys()
) | {"asctime", "message", "taskName"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Anything passed via `extra=` is merged in at the
    top level, so call sites can attach structured fields without a custom
    record type."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }

        actor = actor_id_var.get()
        if actor != "-":
            payload["actor_id"] = actor

        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_FIELDS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # default=str so a stray datetime or UUID in `extra=` degrades to a
        # string rather than taking down the log call that was meant to explain
        # what went wrong.
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable local-development format, with the request id retained so
    correlation still works when reading logs directly."""

    def format(self, record: logging.LogRecord) -> str:
        rid = request_id_var.get()
        suffix = f"  [{rid[:8]}]" if rid != "-" else ""
        base = (
            f"{datetime.fromtimestamp(record.created, tz=UTC).strftime('%Y-%m-%dT%H:%M:%S')}  "
            f"{record.levelname:<8}  {record.name}  {record.getMessage()}{suffix}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Install the root handler. Idempotent — repeated calls replace handlers
    rather than stacking them, which otherwise duplicates every line under
    uvicorn's reloader."""
    formatter: logging.Formatter = JsonFormatter() if json_output else TextFormatter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Uvicorn installs its own handlers; let records propagate to ours instead so
    # access logs share the request-id correlation.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
