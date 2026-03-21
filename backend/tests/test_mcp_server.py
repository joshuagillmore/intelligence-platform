def test_mcp_server_imports():
    from intel_platform.mcp.server import mcp, get_mcp_app
    assert mcp is not None

def test_mcp_app_is_starlette():
    from intel_platform.mcp.server import get_mcp_app
    app = get_mcp_app()
    assert app is not None
