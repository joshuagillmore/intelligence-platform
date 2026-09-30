"""MCP server surface: tools in ``server``, authenticated transport in ``http``."""
from intel_platform.mcp.http import build_authenticated_app, session_lifespan

__all__ = ["build_authenticated_app", "session_lifespan"]
