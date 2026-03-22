import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intel_platform.api.middleware import RateLimitMiddleware, SecurityHeadersMiddleware

from intel_platform.api.deps import get_neo4j_driver
from intel_platform.api.routes import health, projects, ingest, entities, graph, llm, collections, query, assess, topics, reports, geo, timeline, notebook, search, export, watchlist, admin_config, personas, documents, snapshots, auth
from intel_platform.graph.schema import initialize_schema

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")


@asynccontextmanager
async def lifespan(app: FastAPI):
    driver = get_neo4j_driver()
    initialize_schema(driver)
    yield
    driver.close()


app = FastAPI(title="Intelligence Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware, requests_per_minute=120)
app.add_middleware(SecurityHeadersMiddleware)

# Mount MCP server
try:
    from intel_platform.mcp.server import get_mcp_app
    mcp_app = get_mcp_app()
    app.mount("/mcp", mcp_app)
except ImportError:
    pass  # MCP not available

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

# Reverse proxy to frontend Node.js server (Railway single-port deployment)
import os
from pathlib import Path
_frontend_dir = Path("/app/frontend-server")
if _frontend_dir.exists() and (_frontend_dir / "server.js").exists():
    import httpx
    from fastapi import Request
    from fastapi.responses import StreamingResponse, Response

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def proxy_frontend(request: Request, path: str):
        """Proxy non-API requests to the Next.js frontend server."""
        # Don't proxy API, health, or MCP routes
        if path.startswith(("api/", "health", "mcp", "openapi", "docs")):
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
