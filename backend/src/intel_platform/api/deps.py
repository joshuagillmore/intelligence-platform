from __future__ import annotations

from fastapi import Depends, HTTPException, Query
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


def known_project(
    project_id: str = Query(...),
    store: GraphStore = Depends(get_graph_store),
) -> str:
    """Resolve a `project_id` query parameter, 404-ing when it is not a project.

    Every project-scoped read returns a well-formed empty result for an id that
    was never created — `{"events": [], "count": 0}`, `{"nodes": 0, "edges": 0}`
    — which is indistinguishable from a project that exists and holds nothing.
    A stale deep link or a deleted project therefore reads to the analyst as
    "the collection produced nothing", which is the most misleading form that
    answer can take.

    Accepts an id that holds data even without a `Project` node: `/api/ingest`
    creates entities under any `project_id` without requiring the project to be
    created first, and that ingest-first flow is a real one. The 404 is
    therefore reserved for an id under which nothing exists at all — which is
    precisely the case that is meaningless rather than merely empty.
    """
    if store.get_project(project_id):
        return project_id
    if store.search_entities(project_id=project_id, limit=1):
        return project_id
    raise HTTPException(404, f"No project or data found for project_id: {project_id}")


# Keep verify_api_key as alias for backwards compatibility
verify_api_key = get_current_user
