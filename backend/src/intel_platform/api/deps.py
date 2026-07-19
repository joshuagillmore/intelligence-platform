from __future__ import annotations

from fastapi import Depends
from neo4j import Driver, GraphDatabase

from intel_platform.config import settings
from intel_platform.graph.store import GraphStore
from intel_platform.api.auth import get_current_user, require_admin  # noqa: F401  (re-exported for routes)

_driver: Driver | None = None


def get_neo4j_driver() -> Driver:
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


def get_graph_store(driver: Driver = Depends(get_neo4j_driver)) -> GraphStore:
    return GraphStore(driver)


# Keep verify_api_key as alias for backwards compatibility
verify_api_key = get_current_user
