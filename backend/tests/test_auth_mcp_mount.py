"""The MCP endpoint: authenticated, refused under secure auth, and started.

MCP mounted unauthenticated, with graph-writing and LLM-spending tools, and it
could be enabled under REQUIRE_SECURE_AUTH=true. Its session manager's lifespan
never ran when mounted as a sub-app, so every request would have failed. The
cyber package now provides `build_authenticated_app(settings)` and
`session_lifespan()`; this worktree predates them, so both are monkeypatched
onto `intel_platform.mcp` here.
"""
from __future__ import annotations

import contextlib
import types

import pytest
from fastapi import FastAPI

from intel_platform.api import app as app_module


def _settings(**overrides):
    base = dict(
        mcp_enabled=True, require_secure_auth=False,
        jwt_secret="j" * 32, api_key="k" * 16, encryption_key="", default_admin_password="x" * 12,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


async def _asgi_app(scope, receive, send):  # pragma: no cover - never served here
    raise AssertionError("not called")


@pytest.fixture
def mcp_module(monkeypatch):
    calls: dict = {"built_with": [], "entered": 0, "exited": 0}

    def build_authenticated_app(settings):
        calls["built_with"].append(settings)
        return _asgi_app

    @contextlib.asynccontextmanager
    async def session_lifespan():
        calls["entered"] += 1
        yield
        calls["exited"] += 1

    monkeypatch.setattr("intel_platform.mcp.build_authenticated_app", build_authenticated_app, raising=False)
    monkeypatch.setattr("intel_platform.mcp.session_lifespan", session_lifespan, raising=False)
    return calls


class TestMount:
    def test_disabled_mounts_nothing(self, mcp_module):
        target = FastAPI()
        app_module._mount_mcp(target, _settings(mcp_enabled=False))
        assert mcp_module["built_with"] == []
        assert not [r for r in target.routes if getattr(r, "path", "") == "/mcp"]

    def test_enabled_mounts_the_authenticated_app_at_mcp(self, mcp_module):
        target = FastAPI()
        cfg = _settings()
        app_module._mount_mcp(target, cfg)
        assert mcp_module["built_with"] == [cfg]
        assert [r for r in target.routes if getattr(r, "path", "") == "/mcp"]

    @pytest.mark.parametrize("shape", ["function", "object"])
    def test_the_mcp_app_is_served_as_raw_asgi_whatever_its_shape(self, monkeypatch, shape):
        """Starlette's add_route wraps a plain function as a request/response
        endpoint; an ASGI function returned by the builder must still get
        (scope, receive, send)."""
        from fastapi.testclient import TestClient

        seen = {}

        async def asgi(scope, receive, send):
            seen["path"] = scope["path"]
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"mcp"})

        class AsgiObject:
            async def __call__(self, scope, receive, send):
                await asgi(scope, receive, send)

        built = asgi if shape == "function" else AsgiObject()
        monkeypatch.setattr("intel_platform.mcp.build_authenticated_app", lambda s: built, raising=False)
        target = FastAPI()
        app_module._mount_mcp(target, _settings())
        resp = TestClient(target).post("/mcp", json={})
        assert resp.status_code == 200
        assert resp.content == b"mcp"
        assert seen["path"] == "/mcp"

    def test_secure_auth_refuses_mcp_before_building_it(self, mcp_module):
        with pytest.raises(RuntimeError, match="MCP"):
            app_module._mount_mcp(FastAPI(), _settings(require_secure_auth=True))
        assert mcp_module["built_with"] == []

    def test_a_refusal_from_the_builder_propagates(self, monkeypatch):
        def refuse(settings):
            raise RuntimeError("MCP refused")

        monkeypatch.setattr("intel_platform.mcp.build_authenticated_app", refuse, raising=False)
        with pytest.raises(RuntimeError, match="MCP refused"):
            app_module._mount_mcp(FastAPI(), _settings())


class TestLifespan:
    @pytest.fixture
    def quiet_boot(self, monkeypatch):
        """Everything lifespan touches besides MCP, stubbed."""

        class _Driver:
            closed = False

            def close(self):
                self.closed = True

        class _Engine:
            async def dispose(self):
                pass

        async def init_db():
            pass

        monkeypatch.setattr(app_module, "get_neo4j_driver", lambda: _Driver())
        monkeypatch.setattr(app_module, "initialize_schema", lambda driver: None)
        monkeypatch.setattr("intel_platform.api.auth._ensure_default_admin", lambda: None)
        monkeypatch.setattr("intel_platform.db.engine.init_db", init_db)
        monkeypatch.setattr("intel_platform.db.engine.get_engine", lambda: _Engine())

    async def test_the_mcp_session_manager_runs_for_the_apps_lifetime(self, monkeypatch, mcp_module, quiet_boot):
        monkeypatch.setattr(app_module, "settings", _settings())
        async with app_module.lifespan(FastAPI()):
            assert mcp_module["entered"] == 1
            assert mcp_module["exited"] == 0
        assert mcp_module["exited"] == 1

    async def test_no_session_manager_when_mcp_is_off(self, monkeypatch, mcp_module, quiet_boot):
        monkeypatch.setattr(app_module, "settings", _settings(mcp_enabled=False))
        async with app_module.lifespan(FastAPI()):
            pass
        assert mcp_module["entered"] == 0
