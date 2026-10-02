from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import lru_cache

from fastapi import Depends, Request
from neo4j import Driver, GraphDatabase

from intel_platform.config import settings
from intel_platform.graph.store import GraphStore
from intel_platform.api import access
from intel_platform.api.access import ProjectAccess  # noqa: F401  (re-exported for routes)
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


def require_project_access(min_role: str) -> Callable[..., Awaitable[ProjectAccess]]:
    """The dependency every project-scoped route declares.

    ``min_role`` is ``"viewer"`` (reads), ``"editor"`` (writes) or ``"owner"``
    (members, deletion). The dependency finds every project the request
    touches — ``project_id`` in the path, query or JSON/form body, and the
    project owning any entity, document, report, note, snapshot, collection,
    plan, source, catalog entry or PIR id it names — and answers 403 unless the
    caller holds ``min_role`` on each (``api/access.py`` has the rules). An admin
    passes unchecked. It returns a ``ProjectAccess``; declare it as a parameter
    when the handler needs the caller or their grants, otherwise in
    ``dependencies=[...]``.

    The returned callable is the same object for the same role, and carries
    ``project_access_min_role``, which tests/test_project_access_coverage.py
    reads to prove every scoped route declares one.
    """
    if min_role not in access.ROLE_RANK:
        raise ValueError(f"min_role must be one of {sorted(access.ROLE_RANK)}, not {min_role!r}")
    return _project_access_dependency(min_role)


@lru_cache(maxsize=None)
def _project_access_dependency(min_role: str) -> Callable[..., Awaitable[ProjectAccess]]:
    async def project_access(
        request: Request,
        user: dict = Depends(get_current_user),
        driver: Driver = Depends(get_neo4j_driver),
    ) -> ProjectAccess:
        return await access.check(request, user, driver, min_role)

    project_access.project_access_min_role = min_role
    project_access.__name__ = f"require_project_access_{min_role}"
    return project_access


# Keep verify_api_key as alias for backwards compatibility
verify_api_key = get_current_user
