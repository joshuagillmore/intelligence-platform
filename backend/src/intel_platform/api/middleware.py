import logging
import time
from collections import defaultdict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("intel_platform.requests")


def client_ip(request: Request) -> str:
    """Best-effort client IP for rate limiting / logging.

    Honors the LEFTMOST X-Forwarded-For entry ONLY when TRUST_PROXY_HEADERS is
    set (behind a trusted reverse proxy such as Railway). Without that, the
    header is attacker-controlled and would let anyone evade per-IP limits by
    sharing/spoofing it, so we fall back to the socket peer address.
    """
    from intel_platform.config import settings

    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    return request.client.host if request.client else "unknown"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured request logging: method, path, status, response time."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "%s %s %s %d %.1fms",
            client_ip(request),
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware. Set high for single-user workbench; tighten for production."""

    def __init__(self, app, requests_per_minute: int = 3000):
        super().__init__(app)
        self.rpm = requests_per_minute
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health, docs, OPTIONS, and static assets
        path = request.url.path
        if path in ("/health", "/openapi.json", "/docs") or request.method == "OPTIONS":
            return await call_next(request)

        ip = client_ip(request)
        now = time.time()

        # Periodic cleanup of stale IPs (every 5 minutes)
        if now - self._last_cleanup > 300:
            stale = [ip for ip, times in self._requests.items() if not times or now - max(times) > 120]
            for ip in stale:
                del self._requests[ip]
            self._last_cleanup = now

        # Clean old entries for this IP
        self._requests[ip] = [t for t in self._requests[ip] if now - t < 60]

        if len(self._requests[ip]) >= self.rpm:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )

        self._requests[ip].append(now)
        response = await call_next(request)
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
