"""MCP tools apply the REST project-access rules to the caller the transport
stored on the request scope; an analyst JWT must not act on a project it has
no role on, and a viewer must not write."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from intel_platform.api import access
from intel_platform.mcp import server


def _ctx(user):
    scope = {"state": {"user": user}} if user is not None else {"state": {}}
    return SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(scope=scope)))


@pytest.fixture
def grants(monkeypatch):
    table: dict[tuple[str, str], access.Grant] = {}

    async def _grants(user, project_ids):
        return {pid: table.get((user["username"], pid), access.Grant(role=None, access=access.RESTRICTED))
                for pid in project_ids}

    monkeypatch.setattr(access, "grants", _grants)
    return table


async def test_a_non_member_cannot_read_a_restricted_project(grants):
    with pytest.raises(PermissionError, match="No access"):
        await server._require(_ctx({"username": "mallory", "role": "analyst"}), "p1", "viewer")


async def test_a_viewer_can_read_but_not_write(grants):
    grants[("vera", "p1")] = access.Grant(role="viewer", access=access.RESTRICTED)
    await server._require(_ctx({"username": "vera", "role": "analyst"}), "p1", "viewer")
    with pytest.raises(PermissionError):
        await server._require(_ctx({"username": "vera", "role": "analyst"}), "p1", "editor")


async def test_an_editor_can_write(grants):
    grants[("ed", "p1")] = access.Grant(role="editor", access=access.RESTRICTED)
    await server._require(_ctx({"username": "ed", "role": "analyst"}), "p1", "editor")


async def test_an_open_project_admits_everyone(grants):
    grants[("anyone", "open")] = access.Grant(role=None, access=access.OPEN)
    await server._require(_ctx({"username": "anyone", "role": "analyst"}), "open", "editor")


async def test_an_admin_is_never_checked(grants, monkeypatch):
    async def _boom(*a, **k):
        raise AssertionError("grants must not be consulted for an admin")

    monkeypatch.setattr(access, "grants", _boom)
    await server._require(_ctx({"username": "root", "role": "admin"}), "p1", "owner")


async def test_no_caller_is_allowed_only_without_secure_auth(monkeypatch):
    from intel_platform.config import get_settings

    monkeypatch.setattr(get_settings(), "require_secure_auth", False)
    await server._require(_ctx(None), "p1", "viewer")
    await server._require(None, "p1", "viewer")
    monkeypatch.setattr(get_settings(), "require_secure_auth", True)
    with pytest.raises(PermissionError, match="Not authenticated"):
        await server._require(_ctx(None), "p1", "viewer")


async def test_every_tool_takes_the_context(grants):
    """A tool without the `ctx` parameter would silently skip the check."""
    import inspect

    tools = await server.mcp.list_tools()
    for tool in tools:
        fn = server.mcp._tool_manager.get_tool(tool.name).fn
        assert "ctx" in inspect.signature(fn).parameters, tool.name
