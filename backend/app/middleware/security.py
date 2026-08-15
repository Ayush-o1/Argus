"""Security response headers and per-identity rate limiting."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.security.sessions import SESSION_COOKIE_NAME, hash_token

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Headers the browser enforces on our behalf.

    None of these were present before. The CSP is deliberately strict — ARGUS's
    API serves JSON, never HTML, so it has no legitimate need to be framed, to
    load scripts, or to be treated as anything but data. `default-src 'none'`
    means a response somehow coerced into being rendered can still do nothing.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        settings = get_settings()

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"
        )
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        # An API response that a shared cache could store is an API response
        # that could be served to the wrong analyst.
        response.headers.setdefault("Cache-Control", "no-store")

        if settings.session_cookie_secure:
            # Only meaningful over TLS, and actively harmful over plain http in
            # development: it would pin the browser to https for localhost.
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiting, keyed by session where possible.

    Keyed by session-token hash rather than IP when a session cookie is present:
    several analysts behind one office NAT should not share a budget, and an
    attacker with many addresses should not get many budgets. Unauthenticated
    requests fall back to the client address, which is what login attempts are
    limited by.

    In-process and therefore per-instance. That is honest for a single-instance
    deployment and inadequate for several; Redis-backed limiting is Phase 12,
    alongside the rest of the horizontal-scaling work.
    """

    def __init__(self, app, requests_per_minute: int = 300, auth_requests_per_minute: int = 10):
        super().__init__(app)
        self.limit = requests_per_minute
        self.auth_limit = auth_requests_per_minute
        self._windows: dict[tuple[str, int], int] = {}

    def _key(self, request: Request) -> str:
        token = request.cookies.get(SESSION_COOKIE_NAME)
        if token:
            # Hashed so the limiter's own state never holds a usable credential.
            return f"session:{hash_token(token)[:32]}"
        client = request.client.host if request.client else "unknown"
        return f"ip:{client}"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Login and password change get a much tighter budget: they are the
        # endpoints worth brute-forcing, and per-account lockout alone does not
        # stop credential stuffing across many accounts from one source.
        is_auth = request.url.path.startswith("/api/auth/")
        limit = self.auth_limit if is_auth else self.limit

        minute = int(time.time() // 60)
        key = (self._key(request), minute)

        count = self._windows.get(key, 0) + 1
        self._windows[key] = count

        # Drop windows older than the current minute. Cheap because the map only
        # ever holds one or two minutes' worth of keys.
        if len(self._windows) > 10_000:
            self._windows = {k: v for k, v in self._windows.items() if k[1] >= minute - 1}

        if count > limit:
            logger.warning(
                "rate limit exceeded",
                extra={"path": request.url.path, "limit": limit, "observed": count},
            )
            return JSONResponse(
                status_code=429,
                content={"data": None, "error": "Too many requests. Slow down and retry shortly."},
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count))
        return response
