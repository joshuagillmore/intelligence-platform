"""The single-port frontend proxy passes the page's response headers through.

On Railway the browser reaches Next.js only through this proxy, so a header
Next sets — the Content-Security-Policy in particular (contract 19) — exists
for the browser only if the proxy forwards it. Headers were copied through a
dict, which kept only the last of repeated headers such as Set-Cookie, and
hop-by-hop headers (Connection, Keep-Alive, ...) were forwarded although they
describe the proxy's own connection. Upstream is an httpx MockTransport.
"""
from __future__ import annotations

import httpx
import pytest
from starlette.requests import Request

from intel_platform.api import app as app_module

CSP = "default-src 'self'; img-src 'self' data: blob: https://tile.openstreetmap.org; frame-ancestors 'none'"


def _upstream(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers=[
            ("content-type", "text/html; charset=utf-8"),
            ("content-security-policy", CSP),
            ("set-cookie", "a=1; Path=/"),
            ("set-cookie", "b=2; Path=/"),
            ("connection", "keep-alive, x-internal-hop"),
            ("keep-alive", "timeout=5"),
            ("x-internal-hop", "drop-me"),
            ("upgrade", "h2c"),
            ("cache-control", "no-store"),
        ],
        content=b"<html>page</html>",
    )


@pytest.fixture
def upstream(monkeypatch):
    real = httpx.AsyncClient
    seen: dict = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        return _upstream(request)

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: real(transport=httpx.MockTransport(handler)))
    return seen


def _request(path: str, query: str = "") -> Request:
    return Request({
        "type": "http", "method": "GET", "path": f"/{path}", "query_string": query.encode(),
        "headers": [(b"host", b"sentinel.example"), (b"accept-encoding", b"gzip"), (b"cookie", b"a=1")],
    })


async def test_page_headers_reach_the_browser(upstream):
    resp = await app_module._proxy_frontend(_request("network"), "network")
    assert resp.status_code == 200
    assert resp.body == b"<html>page</html>"
    assert resp.headers["content-security-policy"] == CSP
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["content-type"] == "text/html; charset=utf-8"


async def test_repeated_headers_are_all_forwarded(upstream):
    resp = await app_module._proxy_frontend(_request("network"), "network")
    assert resp.headers.getlist("set-cookie") == ["a=1; Path=/", "b=2; Path=/"]


async def test_hop_by_hop_headers_are_not_forwarded(upstream):
    resp = await app_module._proxy_frontend(_request("network"), "network")
    for name in ("connection", "keep-alive", "upgrade", "x-internal-hop"):
        assert name not in resp.headers, name


async def test_the_request_reaches_next_with_its_query(upstream):
    await app_module._proxy_frontend(_request("network", "select=e1"), "network")
    assert upstream["url"] == "http://127.0.0.1:3000/network?select=e1"
    assert upstream["headers"]["host"] == "127.0.0.1:3000"
    assert upstream["headers"]["cookie"] == "a=1"


@pytest.mark.parametrize("path", ["../etc/passwd", "a/../../b", "http://evil.example/"])
async def test_traversal_and_scheme_injection_are_refused(upstream, path):
    resp = await app_module._proxy_frontend(_request("x"), path)
    assert resp.status_code == 400
    assert "url" not in upstream


@pytest.mark.parametrize("path", ["api/projects", "health", "mcp/x", "openapi.json", "docs"])
async def test_backend_paths_are_not_proxied(upstream, path):
    resp = await app_module._proxy_frontend(_request("x"), path)
    assert resp.status_code == 404
    assert "url" not in upstream
