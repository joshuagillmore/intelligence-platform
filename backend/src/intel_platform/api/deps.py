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


def project_exists(store: GraphStore, project_id: str) -> bool:
    """Whether a `project_id` refers to anything at all.

    Every project-scoped read returns a well-formed empty result for an id that
    was never created — `{"events": [], "count": 0}`, `{"nodes": 0, "edges": 0}`
    — which is indistinguishable from a project that exists and holds nothing.
    A stale deep link or a deleted project therefore reads to the analyst as
    "the collection produced nothing", which is the most misleading form that
    answer can take. Endpoints report this alongside the (still empty) payload
    so a caller can tell the two apart without the response shape changing.

    An id holding data counts even without a `Project` node: `/api/ingest`
    creates entities under any `project_id` without requiring the project to be
    created first, and that ingest-first flow is real — there are such ids in
    this database today.
    """
    if store.get_project(project_id):
        return True
    return bool(store.search_entities(project_id=project_id, limit=1))


# Keep verify_api_key as alias for backwards compatibility
verify_api_key = get_current_user
