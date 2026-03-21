from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from intel_platform.api.deps import get_neo4j_driver
from intel_platform.api.routes import health, projects, ingest, entities, graph, llm, collections, query, assess, topics, reports, geo, timeline, notebook
from intel_platform.graph.schema import initialize_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    driver = get_neo4j_driver()
    initialize_schema(driver)
    yield
    driver.close()


app = FastAPI(title="Intelligence Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount MCP server
try:
    from intel_platform.mcp.server import get_mcp_app
    mcp_app = get_mcp_app()
    app.mount("/mcp", mcp_app)
except ImportError:
    pass  # MCP not available

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
