"""Assigns every request a correlation id and logs its outcome.

Two things were missing before this: a request could not be followed across the
several log lines it produces, and there was no record of request latency at all
(the audit's only observability finding that could be fixed without new
infrastructure).

The id is echoed back as `X-Request-ID` so a user reporting a problem can quote
it, and an inbound `X-Request-ID` is honoured so a future reverse proxy or
frontend can propagate its own.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.observability.logging import request_id_var

logger = logging.getLogger("argus.request")

REQUEST_ID_HEADER = "X-Request-ID"

# Bounded so a client cannot push an arbitrarily long value into every log line.
MAX_INBOUND_REQUEST_ID = 64


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        inbound = request.headers.get(REQUEST_ID_HEADER, "").strip()
        # Only accept an inbound id that looks like one — an unvalidated header
        # would let a caller forge or pollute log correlation.
        request_id = (
            inbound
            if inbound and len(inbound) <= MAX_INBOUND_REQUEST_ID and inbound.isascii() and inbound.isprintable()
            else str(uuid.uuid4())
        )
        token = request_id_var.set(request_id)
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            # Logged here because the exception handler runs after this frame and
            # would otherwise lose the timing and the route context.
            logger.exception(
                "request failed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "outcome": "exception",
                },
            )
            request_id_var.reset(token)
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id

        # Health checks are polled continuously by orchestrators; logging them at
        # INFO drowns everything else.
        level = logging.DEBUG if request.url.path.startswith(("/livez", "/readyz", "/api/health")) else logging.INFO
        logger.log(
            level,
            "%s %s -> %d",
            request.method,
            request.url.path,
            response.status_code,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "outcome": "ok" if response.status_code < 400 else "error",
            },
        )

        request_id_var.reset(token)
        return response
