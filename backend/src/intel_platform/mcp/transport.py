"""Authenticated streamable-HTTP transport for the MCP server.

The MCP tools write to the graph and spend LLM calls, so the endpoint takes the
same credential the REST API does: ``api.auth.get_current_user`` — a Bearer JWT
from ``/api/auth/login``, or the configured (non-default) API key. Anything
else is a 401 before the request reaches the MCP session manager.

A mounted sub-application's lifespan never runs, and FastMCP's session manager
refuses every request until its ``run()`` context is active, so the host app
enters :func:`session_lifespan` from its own lifespan. How ``app.py`` wires it:

    from intel_platform.mcp import build_authenticated_app, session_lifespan

    # module level, before the frontend catch-all route
    app.add_route("/mcp", build_authenticated_app(settings))   # endpoint: /mcp

    # inside the FastAPI lifespan, only when MCP is enabled
    async with session_lifespan():
        yield
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.security.utils import get_authorization_scheme_param
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


def _authorization_header(scope) -> str:
    for name, value in scope.get("headers") or []:
        if name.lower() == b"authorization":
            return value.decode("latin-1")
    return ""


def authenticate(scope) -> dict | None:
    """The user an ASGI request's ``Authorization`` header identifies, or None.

    Parses the header as FastAPI's ``HTTPBearer`` does and hands the credentials
    to ``api.auth.get_current_user`` — the REST check itself, called rather than
    copied, so the two cannot drift.
    """
    from intel_platform.api.auth import get_current_user

    scheme, token = get_authorization_scheme_param(_authorization_header(scope))
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        return get_current_user(HTTPAuthorizationCredentials(scheme=scheme, credentials=token))
    except HTTPException:
        return None


class AuthenticatedMCPApp:
    """ASGI app: authenticate the request, then hand it to the MCP session manager.

    A class instance rather than a function so Starlette treats it as a raw ASGI
    endpoint whether it is added as a route (``app.add_route("/mcp", ...)``,
    endpoint ``/mcp``) or mounted (``app.mount("/mcp", ...)``, endpoint
    ``/mcp/``). It serves the streamable-HTTP endpoint at whatever path it is
    attached to — no second ``/mcp`` segment.
    """

    def __init__(self, server) -> None:
        self._server = server

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            return
        if authenticate(scope) is None:
            response = JSONResponse(
                {"detail": "Not authenticated"}, status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
            await response(scope, receive, send)
            return
        await self._server.session_manager.handle_request(scope, receive, send)


def build_authenticated_app(settings) -> AuthenticatedMCPApp:
    """The MCP endpoint behind the REST API's credential check.

    Refuses (``RuntimeError``) when ``settings.require_secure_auth`` is set: a
    deployment that asks for secure auth must not expose MCP at all. ``app.py``
    enforces the same rule at boot; this is the second lock.
    """
    if getattr(settings, "require_secure_auth", False):
        raise RuntimeError(
            "REQUIRE_SECURE_AUTH=true: the MCP server must not be enabled. Set MCP_ENABLED=false."
        )
    from intel_platform.mcp.server import mcp

    mcp.streamable_http_app()  # creates the session manager (idempotent)
    return AuthenticatedMCPApp(mcp)


# The session manager whose run() this module last entered. FastMCP allows one
# run() per manager instance, so a second host lifespan (a new test client, a
# lifespan restart) needs a fresh manager.
_last_run_manager = None


def _session_manager_for_new_run(server):
    global _last_run_manager
    server.streamable_http_app()  # ensure one exists
    if server.session_manager is _last_run_manager and hasattr(server, "_session_manager"):
        server._session_manager = None
        server.streamable_http_app()  # AuthenticatedMCPApp resolves the manager per request
    _last_run_manager = server.session_manager
    return _last_run_manager


@contextlib.asynccontextmanager
async def session_lifespan() -> AsyncIterator[None]:
    """Run the MCP session manager for the life of the host application.

    Enter from the FastAPI lifespan when MCP is enabled. Without it, FastMCP's
    streamable-HTTP transport rejects every request.
    """
    from intel_platform.mcp.server import mcp

    manager = _session_manager_for_new_run(mcp)
    async with manager.run():
        logger.info("MCP session manager running")
        yield
