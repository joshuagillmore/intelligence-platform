"""Rate limiting and response headers (Low -> A)."""
from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.requests import Request

from intel_platform.api.middleware import RateLimitMiddleware, SecurityHeadersMiddleware


def _request(ip: str, path: str = "/api/projects") -> Request:
    return Request({"type": "http", "method": "GET", "path": path, "headers": [], "client": (ip, 5555)})


async def _ok(request):
    return JSONResponse({"ok": True})


async def test_the_cleanup_tick_still_limits_the_client_making_the_request():
    """The cleanup loop reused the name `ip`, so on the request that triggered a
    cleanup, the limit was checked and counted against the last stale address."""
    mw = RateLimitMiddleware(FastAPI(), requests_per_minute=2)
    now = time.time()
    mw._requests["203.0.113.7"] = [now - 1, now - 1]  # at the limit
    mw._requests["198.51.100.9"] = [now - 500]  # stale
    mw._last_cleanup = now - 400  # a cleanup is due

    resp = await mw.dispatch(_request("203.0.113.7"), _ok)
    assert resp.status_code == 429
    assert "198.51.100.9" not in mw._requests


async def test_a_client_under_the_limit_is_counted_under_its_own_address():
    mw = RateLimitMiddleware(FastAPI(), requests_per_minute=2)
    now = time.time()
    mw._requests["198.51.100.9"] = [now - 500]
    mw._last_cleanup = now - 400
    resp = await mw.dispatch(_request("203.0.113.7"), _ok)
    assert resp.status_code == 200
    assert len(mw._requests["203.0.113.7"]) == 1


def _app_with_headers():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/api/thing")
    def thing():
        return {"x": 1}

    @app.get("/api/own-policy")
    def own_policy():
        return JSONResponse({"x": 1}, headers={"Content-Security-Policy": "default-src 'self'"})

    @app.get("/network")
    def page():
        return JSONResponse({"page": True})

    return TestClient(app)


def test_api_responses_forbid_being_rendered_or_framed():
    resp = _app_with_headers().get("/api/thing")
    assert resp.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"


def test_a_policy_already_set_is_not_replaced():
    resp = _app_with_headers().get("/api/own-policy")
    assert resp.headers["content-security-policy"] == "default-src 'self'"


def test_frontend_pages_keep_the_frontends_own_policy():
    """Pages come from Next through the proxy with the policy Next sets."""
    resp = _app_with_headers().get("/network")
    assert "content-security-policy" not in resp.headers
