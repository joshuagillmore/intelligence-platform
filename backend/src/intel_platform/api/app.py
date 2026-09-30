import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intel_platform.api.middleware import RateLimitMiddleware, RequestLoggingMiddleware, SecurityHeadersMiddleware

from intel_platform.api.deps import get_neo4j_driver
from intel_platform.api.routes import health, projects, ingest, entities, graph, llm, collections, query, assess, topics, reports, geo, timeline, notebook, search, export, watchlist, admin_config, personas, documents, snapshots, auth, collection_plans, pirs, enrichment, attack, analysis
from intel_platform.config import settings
from intel_platform.graph.schema import initialize_schema

logger = logging.getLogger(__name__)


def _parse_origins(value: str) -> list[str]:
    return [origin.strip() for origin in value.split(",") if origin.strip()]


CORS_ORIGINS = _parse_origins(settings.cors_origins)


def _secret_problems() -> list[str]:
    """What is wrong with the JWT secret and API key in effect (empty when sound).

    Shared by the boot warning and REQUIRE_SECURE_AUTH so the two can never
    disagree about what counts as insecure.
    """
    from intel_platform.api.auth import api_key_problem, jwt_secret_problem
    from intel_platform.crypto import encryption_problem
    return [
        p for p in (
            jwt_secret_problem(settings.jwt_secret),
            api_key_problem(settings.api_key),
            encryption_problem(settings.encryption_key),
        ) if p
    ]


def _insecure_defaults() -> list[str]:
    """List the insecure secrets still in effect (empty when hardened)."""
    from intel_platform.api.auth import _DEFAULT_API_KEY
    problems = []
    for problem in _secret_problems():
        if settings.api_key == _DEFAULT_API_KEY and problem.startswith("API_KEY"):
            problem += " (it will NOT authenticate)"
        problems.append(problem)
    if not settings.default_admin_password:
        problems.append("DEFAULT_ADMIN_PASSWORD is blank (a default 'admin' user may be seeded)")
    return problems


def _warn_insecure_defaults() -> None:
    """Loud, always-on boot warning when any default secret is still in place.

    Fires regardless of REQUIRE_SECURE_AUTH so a naive deploy is never silent.
    Set strong secrets AND REQUIRE_SECURE_AUTH=true to fail-closed in production.
    """
    problems = _insecure_defaults()
    if problems:
        logger.warning(
            "SECURITY: insecure default(s) in use: %s. Set strong JWT_SECRET / API_KEY / "
            "DEFAULT_ADMIN_PASSWORD and REQUIRE_SECURE_AUTH=true before any real deployment.",
            "; ".join(problems),
        )


def _enforce_secure_auth() -> None:
    """Fail-closed: refuse to start on insecure secrets when REQUIRE_SECURE_AUTH is set."""
    if not settings.require_secure_auth:
        return
    # The admin password is judged against the stored hash in
    # _ensure_default_admin, which needs the database; everything else is here.
    problems = _secret_problems()
    if problems:
        raise RuntimeError(
            "REQUIRE_SECURE_AUTH=true but insecure settings are in use: "
            + "; ".join(problems)
            + ". Set JWT_SECRET to at least 32 random bytes, API_KEY to at least "
            "16 random bytes (or blank, to disable API-key auth) and ENCRYPTION_KEY to a "
            "Fernet key before deploying."
        )


def _mount_mcp(target: FastAPI, cfg) -> None:
    """Mount the authenticated MCP endpoint at /mcp when MCP_ENABLED is set.

    Its tools write to the graph and spend LLM calls, so it is refused outright
    under REQUIRE_SECURE_AUTH, and otherwise served behind the same credentials
    as the REST API by the MCP package's own ASGI wrapper. Registered as a route
    (endpoint /mcp), ahead of the frontend catch-all. Failures propagate: an
    operator who enabled MCP must not get a server that quietly lacks it.
    """
    if not cfg.mcp_enabled:
        logger.info("MCP server disabled (set MCP_ENABLED=true to enable)")
        return
    if cfg.require_secure_auth:
        raise RuntimeError(
            "MCP_ENABLED=true is refused under REQUIRE_SECURE_AUTH=true: its tools write to the "
            "graph and spend LLM calls. Disable MCP on this deployment."
        )
    from intel_platform.mcp import build_authenticated_app
    target.add_route("/mcp", _AsgiEndpoint(build_authenticated_app(cfg)))
    logger.info("MCP server mounted at /mcp (authenticated)")


class _AsgiEndpoint:
    """Serve an ASGI app from a route as raw ASGI, whatever its shape.

    Starlette's `add_route` treats a plain function as a request/response
    endpoint and would call an `async def app(scope, receive, send)` with a
    Request. A class instance is always passed (scope, receive, send).
    """

    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        await self.asgi_app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _warn_insecure_defaults()
    _enforce_secure_auth()
    driver = get_neo4j_driver()
    initialize_schema(driver)
    # Ensure default admin user exists in Neo4j
    from intel_platform.api.auth import _ensure_default_admin
    _ensure_default_admin()
    # Initialize PostgreSQL tables for collection management
    from intel_platform.db.engine import init_db
    await init_db()
    logger.info("PostgreSQL collection management tables initialized")
    async with contextlib.AsyncExitStack() as stack:
        # A mounted MCP app's own lifespan never runs, so its session manager is
        # started here, for the lifetime of this app.
        if settings.mcp_enabled:
            from intel_platform.mcp import session_lifespan
            await stack.enter_async_context(session_lifespan())
        yield
    driver.close()
    # Cleanup async engine
    from intel_platform.db.engine import get_engine
    await get_engine().dispose()


app = FastAPI(title="Intelligence Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_per_minute)
app.add_middleware(SecurityHeadersMiddleware)

# MCP server — OFF by default (MCP_ENABLED=true to enable).
_mount_mcp(app, settings)

app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(health.router, tags=["health"])
app.include_router(projects.router, prefix="/api", tags=["projects"])
app.include_router(ingest.router, prefix="/api", tags=["ingest"])
app.include_router(entities.router, prefix="/api", tags=["entities"])
app.include_router(graph.router, prefix="/api", tags=["graph"])
app.include_router(llm.router, prefix="/api", tags=["llm"])
app.include_router(collections.router, prefix="/api", tags=["collections"])
app.include_router(query.router, prefix="/api", tags=["query"])
app.include_router(assess.router, prefix="/api", tags=["assess"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])
app.include_router(topics.router, prefix="/api", tags=["topics"])
app.include_router(reports.router, prefix="/api", tags=["reports"])
app.include_router(geo.router, prefix="/api", tags=["geo"])
app.include_router(timeline.router, prefix="/api", tags=["timeline"])
app.include_router(notebook.router, prefix="/api", tags=["notebook"])
app.include_router(search.router, prefix="/api", tags=["search"])
app.include_router(export.router, prefix="/api", tags=["export"])
app.include_router(watchlist.router, prefix="/api", tags=["watchlist"])
app.include_router(admin_config.router, prefix="/api", tags=["admin"])
app.include_router(personas.router, prefix="/api", tags=["personas"])
app.include_router(documents.router, prefix="/api", tags=["documents"])
app.include_router(snapshots.router, prefix="/api", tags=["snapshots"])
app.include_router(collection_plans.router, prefix="/api", tags=["collection-plans"])
app.include_router(pirs.router, prefix="/api", tags=["pirs"])
app.include_router(enrichment.router, prefix="/api", tags=["enrichment"])
app.include_router(attack.router, prefix="/api", tags=["attack"])

# Reverse proxy to frontend Node.js server (Railway single-port deployment)
from pathlib import Path  # noqa: E402

import httpx  # noqa: E402
from fastapi import Request  # noqa: E402
from fastapi.responses import Response  # noqa: E402

# Headers that describe one connection, not the resource (RFC 9110 §7.6.1), so a
# proxy must not pass them on; plus any header the Connection header names.
_HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "proxy-connection", "te", "trailer", "trailers", "transfer-encoding", "upgrade",
})
# httpx has already decoded the body, so the upstream encoding and length no
# longer describe what is sent; Starlette sets the length itself.
_REFRAMED = frozenset({"content-encoding", "content-length"})


def _forwardable_response_headers(headers: httpx.Headers) -> list[tuple[str, str]]:
    """Every upstream response header a client should see, repeats included.

    Contract 19: on Railway the browser reaches Next only through this proxy,
    so a header Next sets (the Content-Security-Policy above all) exists for the
    browser only if it is forwarded. Copying through a dict kept one value of a
    repeated header, so only the last Set-Cookie survived.
    """
    named = {token.strip().lower() for value in headers.get_list("connection") for token in value.split(",")}
    drop = _HOP_BY_HOP | _REFRAMED | named
    return [(name, value) for name, value in headers.multi_items() if name.lower() not in drop]


async def _proxy_frontend(request: Request, path: str) -> Response:
    """Proxy non-API requests to the Next.js frontend server."""
    # SECURITY: reject path traversal and protocol injection attempts
    if ".." in path or path.startswith("/") or "://" in path:
        return Response(status_code=400)
    # Don't proxy API, health, or MCP routes
    if path.startswith(("api/", "health", "mcp/", "openapi", "docs")):
        return Response(status_code=404)
    url = f"http://127.0.0.1:3000/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    try:
        # Don't forward Accept-Encoding to upstream — let httpx handle decompression
        fwd_headers = {k: v for k, v in request.headers.items()
                       if k.lower() not in ('host', 'accept-encoding')}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=fwd_headers, timeout=10)
    except Exception:
        return Response(content="Frontend not available", status_code=502)
    response = Response(content=resp.content, status_code=resp.status_code)
    for name, value in _forwardable_response_headers(resp.headers):
        response.headers.append(name, value)
    return response


_frontend_dir = Path("/app/frontend-server")
if _frontend_dir.exists() and (_frontend_dir / "server.js").exists():
    app.add_api_route(
        "/{path:path}", _proxy_frontend, methods=["GET", "HEAD"], include_in_schema=False,
    )
elif Path("/app/static").exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")
