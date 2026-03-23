import logging
import time
from collections import defaultdict

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("intel_platform.requests")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Structured request logging: method, path, status, response time."""

    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        client_ip = request.client.host if request.client else "-"
        logger.info(
            "%s %s %s %d %.1fms",
            client_ip,
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

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()

        # Periodic cleanup of stale IPs (every 5 minutes)
        if now - self._last_cleanup > 300:
            stale = [ip for ip, times in self._requests.items() if not times or now - max(times) > 120]
            for ip in stale:
                del self._requests[ip]
            self._last_cleanup = now

        # Clean old entries for this IP
        self._requests[client_ip] = [t for t in self._requests[client_ip] if now - t < 60]

        if len(self._requests[client_ip]) >= self.rpm:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )

        self._requests[client_ip].append(now)
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
