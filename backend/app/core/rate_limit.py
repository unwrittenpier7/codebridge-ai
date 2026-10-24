"""A small in-process, per-client rate limiter for sensitive endpoints.

This is a single-process sliding window. It is enough to stop credential
stuffing and accidental request storms from one client; a multi-replica
deployment should put a shared limiter (e.g. Redis or an API gateway) in front
of it. The limiter is deliberately simple and dependency-free.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

#: Endpoints that get the strict bucket (credential handling).
SENSITIVE_PATHS = ("/api/auth/login", "/api/auth/register")


class SlidingWindowLimiter:
    """Thread-safe sliding-window counter keyed by an arbitrary string."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self._events: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> Tuple[bool, int]:
        """Record an attempt. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - events[0])) + 1)
                return False, retry_after
            events.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


def _client_key(request: Request) -> str:
    """Identify the caller without trusting arbitrary headers.

    `X-Forwarded-For` is only honoured when the deployment says a proxy sets it
    (`TRUST_PROXY_HEADERS`); otherwise a client could rotate the header to bypass
    the limit entirely.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Applies the sensitive bucket to auth routes and a looser one elsewhere."""

    def __init__(self, app):
        super().__init__(app)
        self.sensitive = SlidingWindowLimiter(
            settings.auth_rate_limit_requests, settings.auth_rate_limit_window_seconds
        )
        self.general = SlidingWindowLimiter(
            max(settings.auth_rate_limit_requests * 20, 200),
            settings.auth_rate_limit_window_seconds,
        )

    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled:
            return await call_next(request)

        path = request.url.path
        limiter = self.sensitive if path in SENSITIVE_PATHS else self.general
        allowed, retry_after = limiter.check(f"{path}:{_client_key(request)}")
        if not allowed:
            logger.warning("Rate limit exceeded for %s from %s", path, _client_key(request))
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down and try again shortly.",
                    "error_type": "RateLimitExceeded",
                },
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
