"""MCP server: authentication (E-9) and the session lifespan (Low → E).

The MCP surface used to mount unauthenticated with graph-writing and
LLM-spending tools, and its streamable-HTTP session manager was never started
(a mounted sub-app's lifespan does not run), so every request failed. These
tests drive a real MCP ``initialize`` through the authenticated app the way
``app.py`` mounts it. No network: httpx talks to the ASGI app in-process.
"""
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

import intel_platform.mcp as platform_mcp
from intel_platform.mcp import server as mcp_server

INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _settings(**overrides):
    return SimpleNamespace(**{"require_secure_auth": False, **overrides})


def _bearer(token: str) -> dict:
    return {**MCP_HEADERS, "Authorization": f"Bearer {token}"}


def _jwt() -> str:
    from intel_platform.api.auth import create_access_token
    return create_access_token("analyst-1", "analyst")


def _host(style: str) -> tuple[FastAPI, str]:
    """A FastAPI app that mounts MCP exactly as the report tells app.py to."""
    app = FastAPI()
    mcp_app = platform_mcp.build_authenticated_app(_settings())
    if style == "route":
        app.add_route("/mcp", mcp_app)
        return app, "/mcp"
    app.mount("/mcp", mcp_app)
    return app, "/mcp/"


async def _initialize(app: FastAPI, path: str, headers: dict) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.post(path, json=INITIALIZE, headers=headers)


def test_mcp_server_imports():
    from intel_platform.mcp.server import mcp
    assert mcp is not None


@pytest.mark.parametrize("style", ["route", "mount"])
@pytest.mark.parametrize("headers", [
    pytest.param(MCP_HEADERS, id="no-header"),
    pytest.param({**MCP_HEADERS, "Authorization": "Bearer not-a-jwt"}, id="garbage-token"),
    pytest.param({**MCP_HEADERS, "Authorization": "Bearer dev-api-key-change-in-production"}, id="default-api-key"),
    pytest.param({**MCP_HEADERS, "Authorization": "Basic YWRtaW46YWRtaW4="}, id="basic-scheme"),
])
async def test_unauthenticated_requests_are_refused(style, headers):
    app, path = _host(style)
    async with platform_mcp.session_lifespan():
        resp = await _initialize(app, path, headers)
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Not authenticated"}
    assert resp.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("style", ["route", "mount"])
async def test_a_valid_jwt_reaches_the_mcp_server(style):
    app, path = _host(style)
    async with platform_mcp.session_lifespan():
        resp = await _initialize(app, path, _bearer(_jwt()))
    assert resp.status_code == 200, resp.text
    assert "Intelligence Platform" in resp.text  # serverInfo.name in the initialize result


async def test_a_configured_api_key_reaches_the_mcp_server(monkeypatch):
    from intel_platform.config import settings

    monkeypatch.setattr(settings, "api_key", "a-real-service-key-0123456789abcdef")
    app, path = _host("route")
    async with platform_mcp.session_lifespan():
        resp = await _initialize(app, path, _bearer("a-real-service-key-0123456789abcdef"))
    assert resp.status_code == 200, resp.text


async def test_session_lifespan_can_be_entered_again():
    # The session manager can run once per instance; a second app lifespan
    # (a test client, a reload) must still get a working one.
    app, path = _host("route")
    for _ in range(2):
        async with platform_mcp.session_lifespan():
            resp = await _initialize(app, path, _bearer(_jwt()))
        assert resp.status_code == 200, resp.text


def test_refuses_to_build_under_require_secure_auth():
    with pytest.raises(RuntimeError, match="REQUIRE_SECURE_AUTH"):
        platform_mcp.build_authenticated_app(_settings(require_secure_auth=True))


async def test_legacy_get_mcp_app_is_authenticated_too():
    # app.py still calls get_mcp_app() until the api-core package switches to
    # build_authenticated_app; it must never hand out the unauthenticated app.
    app = FastAPI()
    app.add_route("/mcp", mcp_server.get_mcp_app())
    async with platform_mcp.session_lifespan():
        resp = await _initialize(app, "/mcp", MCP_HEADERS)
    assert resp.status_code == 401
