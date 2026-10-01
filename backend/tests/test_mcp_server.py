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
from tests.ids import tp

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


# --- tools: scoping (contract 2), off-loop store calls (contract 15) ---------

def _on_event_loop() -> bool:
    import asyncio
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class _FakeStore:
    """GraphStore stand-in: records each call's arguments and thread."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.on_loop: list[bool] = []

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))
        self.on_loop.append(_on_event_loop())

    def get_entity(self, entity_id):
        self._record("get_entity", entity_id=entity_id)
        return {"id": entity_id, "project_id": "proj-of-entity"}

    def get_subgraph(self, entity_id, hops=1, project_id=None):
        self._record("get_subgraph", entity_id=entity_id, hops=hops, project_id=project_id)
        return {"nodes": [{"id": entity_id}, {"id": "shared"}], "edges": []}

    def find_shortest_path(self, entity_id_1, entity_id_2, project_id=None):
        self._record("find_shortest_path", project_id=project_id)
        return {"nodes": [], "edges": [], "path_length": 0}

    def search_entities(self, project_id=None, query="", entity_type=None, limit=20):
        self._record("search_entities", project_id=project_id)
        return [{"id": "e1"}]

    def create_entity(self, model):
        self._record("create_entity")
        return {"id": model.id}


class _LegacyStore(_FakeStore):
    """The store before contract 2 lands: no project_id parameter."""

    def get_subgraph(self, entity_id, hops=1):
        self._record("get_subgraph", entity_id=entity_id, hops=hops)
        return {"nodes": [], "edges": []}


@pytest.fixture
def fake_store(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(mcp_server, "_store", lambda: store)
    return store


def _subgraph_calls(store):
    return [kwargs for name, kwargs in store.calls if name == "get_subgraph"]


@pytest.mark.parametrize("requested,expected", [(50, 4), (4, 4), (2, 2), (0, 1), (-3, 1)])
async def test_get_subgraph_clamps_hops(fake_store, requested, expected):
    await mcp_server.get_subgraph("e1", hops=requested, project_id="proj-a")
    assert _subgraph_calls(fake_store)[0]["hops"] == expected


async def test_get_subgraph_is_scoped_to_the_given_project(fake_store):
    await mcp_server.get_subgraph("e1", hops=2, project_id="proj-a")
    assert _subgraph_calls(fake_store)[0]["project_id"] == "proj-a"


async def test_get_subgraph_defaults_to_the_entitys_own_project(fake_store):
    # Unscoped traversal crossed shared ATT&CK nodes into other projects (A-7).
    await mcp_server.get_subgraph("e1")
    assert _subgraph_calls(fake_store)[0]["project_id"] == "proj-of-entity"


async def test_get_subgraph_works_against_a_store_without_project_scoping(monkeypatch):
    store = _LegacyStore()
    monkeypatch.setattr(mcp_server, "_store", lambda: store)
    result = await mcp_server.get_subgraph("e1", hops=9, project_id="proj-a")
    assert result == {"nodes": [], "edges": []}
    assert _subgraph_calls(store) == [{"entity_id": "e1", "hops": 4}]


async def test_find_connections_scopes_both_traversals(fake_store):
    out = await mcp_server.find_connections("e1", "e2", project_id="proj-a")
    calls = _subgraph_calls(fake_store)
    assert [c["project_id"] for c in calls] == ["proj-a", "proj-a"]
    assert all(c["hops"] == 2 for c in calls)
    assert out["count"] >= 1


async def test_find_shortest_path_is_scoped(fake_store):
    await mcp_server.find_shortest_path("e1", "e2")
    assert [k for n, k in fake_store.calls if n == "find_shortest_path"] == [{"project_id": "proj-of-entity"}]


async def test_graph_tools_call_the_store_off_the_event_loop(fake_store):
    await mcp_server.search_entities("proj-a", query="x")
    await mcp_server.get_subgraph("e1", project_id="proj-a")
    await mcp_server.find_connections("e1", "e2", project_id="proj-a")
    await mcp_server.find_shortest_path("e1", "e2", project_id="proj-a")
    assert fake_store.on_loop and not any(fake_store.on_loop)


async def test_query_corpus_returns_the_answer_not_a_coroutine(fake_store, monkeypatch):
    # GraphRAGPipeline.query is async; the sync tool returned it unawaited.
    import intel_platform.services.graph_rag as graph_rag

    class _Pipeline:
        def __init__(self, store):
            pass

        async def query(self, query, project_id):
            return {"answer": f"{query} @ {project_id}"}

    monkeypatch.setattr(graph_rag, "GraphRAGPipeline", _Pipeline)
    assert await mcp_server.query_corpus("proj-a", "who") == {"answer": "who @ proj-a"}


async def test_ingest_document_builds_the_graph_off_the_event_loop(fake_store, monkeypatch):
    import intel_platform.services.graph_builder as graph_builder
    import intel_platform.services.ingestion as ingestion

    build_on_loop: list[bool] = []

    def fake_build(store, entities, rels, project_id, **kwargs):
        build_on_loop.append(_on_event_loop())
        return {"entities_created": len(entities)}

    monkeypatch.setattr(graph_builder, "build_graph_from_extractions", fake_build)
    monkeypatch.setattr(ingestion, "ingest_text", lambda content, *a, **k: [{"content": content}])

    async def fake_extract(text, doc_id, mode):
        return [{"name": "APT29", "type": "ThreatActor"}], []

    monkeypatch.setattr(mcp_server, "_mcp_extract", fake_extract)

    out = await mcp_server.ingest_document(tp("proj"), "APT29 did things", extraction_mode="nlp")
    assert out["entities_created"] == 1
    assert build_on_loop == [False]
    assert fake_store.on_loop == [False]  # create_entity for the Document


async def test_legacy_get_mcp_app_is_authenticated_too():
    # app.py still calls get_mcp_app() until the api-core package switches to
    # build_authenticated_app; it must never hand out the unauthenticated app.
    app = FastAPI()
    app.add_route("/mcp", mcp_server.get_mcp_app())
    async with platform_mcp.session_lifespan():
        resp = await _initialize(app, "/mcp", MCP_HEADERS)
    assert resp.status_code == 401
