import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intel_platform.api.middleware import RateLimitMiddleware, RequestLoggingMiddleware, SecurityHeadersMiddleware

from intel_platform.api.deps import get_neo4j_driver
from intel_platform.api.routes import health, projects, ingest, entities, graph, llm, collections, query, assess, topics, reports, geo, timeline, notebook, search, export, watchlist, admin_config, personas, documents, snapshots, auth, collection_plans, enrichment, attack, analysis
from intel_platform.config import settings
from intel_platform.graph.schema import initialize_schema

logger = logging.getLogger(__name__)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")


def _insecure_defaults() -> list[str]:
    """List the built-in default secrets still in effect (empty when hardened)."""
    from intel_platform.api.auth import _DEFAULT_API_KEY, _IS_DEFAULT_SECRET
    problems = []
    if _IS_DEFAULT_SECRET:
        problems.append("JWT_SECRET is the built-in default")
    if settings.api_key == _DEFAULT_API_KEY:
        problems.append("API_KEY is the built-in default (it will NOT authenticate)")
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
    """Fail-closed: refuse to start with built-in default secrets when REQUIRE_SECURE_AUTH is set."""
    if not settings.require_secure_auth:
        return
    # Reuse the same detection, but the blank-admin-password case is enforced at
    # seed time in _ensure_default_admin, so only the two hard secrets block boot here.
    from intel_platform.api.auth import _DEFAULT_API_KEY, _IS_DEFAULT_SECRET
    problems = []
    if _IS_DEFAULT_SECRET:
        problems.append("JWT_SECRET is the built-in default")
    if settings.api_key == _DEFAULT_API_KEY:
        problems.append("API_KEY is the built-in default")
    if problems:
        raise RuntimeError(
            "REQUIRE_SECURE_AUTH=true but insecure defaults are in use: "
            + "; ".join(problems)
            + ". Set a strong JWT_SECRET and API_KEY before deploying."
        )


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

# Mount MCP server — OFF by default: its tools include graph writes and it is not
# behind the REST auth. Enable deliberately (behind a trusted gateway) via MCP_ENABLED=true.
if settings.mcp_enabled:
    try:
        from intel_platform.mcp.server import get_mcp_app
        mcp_app = get_mcp_app()
        app.mount("/mcp", mcp_app)
        logger.warning("MCP server mounted at /mcp (unauthenticated — ensure the network is trusted)")
    except Exception as exc:
        logger.warning("MCP server not available: %s", exc)
else:
    logger.info("MCP server disabled (set MCP_ENABLED=true to enable)")

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
app.include_router(enrichment.router, prefix="/api", tags=["enrichment"])
app.include_router(attack.router, prefix="/api", tags=["attack"])

# Reverse proxy to frontend Node.js server (Railway single-port deployment)
from pathlib import Path  # noqa: E402
_frontend_dir = Path("/app/frontend-server")
if _frontend_dir.exists() and (_frontend_dir / "server.js").exists():
    import httpx
    from fastapi import Request
    from fastapi.responses import Response

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def proxy_frontend(request: Request, path: str):
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
                # Strip encoding/transfer headers — content is already decompressed by httpx
                safe_headers = {k: v for k, v in resp.headers.items()
                               if k.lower() not in ('content-encoding', 'transfer-encoding', 'content-length')}
                return Response(
                    content=resp.content,
                    status_code=resp.status_code,
                    headers=safe_headers,
                )
        except Exception:
            return Response(content="Frontend not available", status_code=502)
elif Path("/app/static").exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")
