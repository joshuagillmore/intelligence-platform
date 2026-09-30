"""MCP server surface: tools in ``server``, authenticated transport in ``transport``."""
from intel_platform.mcp.transport import build_authenticated_app, session_lifespan

__all__ = ["build_authenticated_app", "session_lifespan"]
