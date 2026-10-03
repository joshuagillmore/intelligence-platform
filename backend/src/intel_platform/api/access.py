"""Per-project access control: what a request touches, and whether the caller
may touch it.

The dependency routes declare is ``api.deps.require_project_access(min_role)``;
this module holds the rules it applies, so they can be read in one place.

Roles, weakest first: ``viewer`` (read), ``editor`` (read and write project
data), ``owner`` (also manage members and delete the project).

- **Admin** (``role == "admin"`` on the session, which includes the API key)
  is an implicit owner of every project and is never checked. An admin is
  listed as a member only of the projects they created or claimed, as their
  owner, so those are restricted like any other.
- **Open project**: one with no members, which is every project created before
  membership existed (and before admins owned what they create). Every
  authenticated user has full use of it, as before. The first member added
  must be an owner, which closes it; an admin can claim it outright
  (``POST /projects/{id}/claim``).
- **Restricted project**: one with members. A member needs a role at least
  ``min_role``; anyone else is refused 403 ``"No access to this project"``.

**What a request touches** is read from its path parameters, query string and
JSON or form body, by field name (``FIELDS``): a project id directly, or the id
of something a project owns — a graph node (entity, document, report, note,
snapshot, legacy collection), a collection plan, source or catalog entry, or a
PIR — which is resolved to its project first. Every project touched is checked,
so naming an accessible project does not open another project's entity. An id
that resolves to nothing touches no project; the route answers it (usually 404).

The body is the one FastAPI has already read for the route: Starlette caches
``request.json()`` and ``request.form()`` on the request, and FastAPI parses
the body before it solves dependencies, so nothing is read twice and the
handler receives its parsed body as usual.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}
OWNER = "owner"
OPEN = "open"
RESTRICTED = "restricted"

NO_ACCESS = "No access to this project"
ACCESS_UNAVAILABLE = "Project access could not be checked"

# Field names that say which project a request touches, by what they name.
PROJECT_FIELDS = frozenset({"project_id", "project_ids"})
# Graph nodes: entities, documents, reports and notebook notes (Report nodes),
# snapshots and legacy collections (`task_id`).
NODE_FIELDS = frozenset({
    "entity_id", "entity_id_1", "entity_id_2", "primary_id", "doc_id", "note_id", "report_id",
    "snapshot_id", "task_id",
    "entity_ids", "merge_ids", "seed_ids", "document_ids",
})
PLAN_FIELDS = frozenset({"plan_id"})
SOURCE_FIELDS = frozenset({"source_id"})
CATALOG_FIELDS = frozenset({"catalog_id"})
PIR_FIELDS = frozenset({"pir_id"})

FIELDS = PROJECT_FIELDS | NODE_FIELDS | PLAN_FIELDS | SOURCE_FIELDS | CATALOG_FIELDS | PIR_FIELDS


@dataclass(frozen=True)
class Grant:
    """The caller's standing on one project."""
    role: str | None   # membership role; "owner" for an admin; None when not a member
    access: str        # OPEN | RESTRICTED

    def allows(self, min_role: str) -> bool:
        # An open project is fully usable by everyone; an admin's role is owner.
        effective = OWNER if self.access == OPEN else self.role
        return effective is not None and ROLE_RANK[effective] >= ROLE_RANK[min_role]


@dataclass(frozen=True)
class ProjectAccess:
    """What ``require_project_access`` returns to a handler that asks for it."""
    user: dict
    min_role: str
    # Every project the request touches, with the caller's grant on it. Empty
    # for an admin: an admin is not checked, so nothing is resolved.
    grants: dict[str, Grant] = field(default_factory=dict)

    @property
    def username(self) -> str:
        return str(self.user.get("username") or "")

    @property
    def is_admin(self) -> bool:
        return is_admin(self.user)


def is_admin(user: dict) -> bool:
    return user.get("role") == "admin"


# ---------------------------------------------------------------------------
# Grants
# ---------------------------------------------------------------------------

# Above this many ids, membership is read for every project and filtered here,
# rather than sent as one bind parameter per id.
_IN_LIMIT = 500


async def grants(user: dict, project_ids: Iterable[str]) -> dict[str, Grant]:
    """The caller's grant on each of ``project_ids``.

    Reads Postgres (not at all for an empty list); database errors propagate.
    """
    from intel_platform.db import members

    ids = {p for p in project_ids if p}
    if not ids:
        return {}
    rows = await members.memberships(ids if len(ids) <= _IN_LIMIT else None, str(user.get("username") or ""))
    admin = is_admin(user)
    out = {}
    for pid in ids:
        row = rows.get(pid)
        access = RESTRICTED if row and row.members else OPEN
        out[pid] = Grant(role=OWNER if admin else (row.role if row else None), access=access)
    return out


async def load_grants(user: dict, project_ids: Iterable[str]) -> dict[str, Grant]:
    """``grants`` for a handler: a database outage is a 503, never a guess."""
    try:
        return await grants(user, project_ids)
    except Exception:
        logger.exception("Reading project membership failed")
        raise HTTPException(status_code=503, detail=ACCESS_UNAVAILABLE) from None


async def grant_on(access: ProjectAccess, project_id: str) -> Grant:
    """The caller's grant on one project: the one the dependency checked, or,
    for an admin (who is not checked), read now."""
    found = access.grants.get(project_id)
    if found is None:
        found = (await load_grants(access.user, [project_id]))[project_id]
    return found


async def visible_projects(user: dict, project_ids: Iterable[str]) -> set[str]:
    """The ids among ``project_ids`` the caller may read (for list routes that
    span projects)."""
    ids = {p for p in project_ids if p}
    if is_admin(user):
        return ids
    return {pid for pid, g in (await load_grants(user, ids)).items() if g.allows("viewer")}


# ---------------------------------------------------------------------------
# What a request touches
# ---------------------------------------------------------------------------

def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [v for v in value if isinstance(v, str)]
    return []


async def _body_fields(request: Request) -> dict[str, list[str]]:
    """The scoped fields of a JSON object or form body (cached on the request)."""
    content_type = request.headers.get("content-type", "").lower()
    out: dict[str, list[str]] = {}
    if content_type.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        form = await request.form()
        for name in FIELDS:
            values = [v for v in form.getlist(name) if isinstance(v, str)]
            if values:
                out[name] = values
        return out
    if "json" not in content_type:
        return out
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        # FastAPI answers a malformed body with a 422 of its own.
        return out
    if isinstance(body, dict):
        for name in FIELDS:
            values = _strings(body.get(name))
            if values:
                out[name] = values
    return out


async def request_fields(request: Request) -> dict[str, set[str]]:
    """Every scoped field the request carries, from the path, query and body."""
    found: dict[str, set[str]] = {}

    def add(name: str, values: Iterable[str]) -> None:
        values = {v for v in values if v}
        if values:
            found.setdefault(name, set()).update(values)

    for name, value in request.path_params.items():
        if name in FIELDS:
            add(name, _strings(value))
    for name in FIELDS:
        add(name, request.query_params.getlist(name))
    for name, values in (await _body_fields(request)).items():
        add(name, values)
    return found


_NODE_OWNERS = """
MATCH (n:Entity) WHERE n.id IN $ids
RETURN CASE WHEN n:Project THEN n.id ELSE n.project_id END AS pid
UNION
MATCH (n:Project) WHERE n.id IN $ids RETURN n.id AS pid
UNION
MATCH (n:Snapshot) WHERE n.id IN $ids RETURN n.project_id AS pid
UNION
MATCH (n:Collection) WHERE n.id IN $ids RETURN n.project_id AS pid
"""


def _node_owners(driver, node_ids: set[str]) -> set[str]:
    """The projects these graph nodes belong to.

    Every node the routes address by id is labelled Entity (initialize_schema
    labels older ones at startup), except snapshots and legacy collections,
    which are matched by their own labels, and Project nodes written without
    Entity. Shared reference nodes (ATT&CK, CWE) have no project and add none.
    """
    with driver.session() as session:
        return {r["pid"] for r in session.run(_NODE_OWNERS, ids=sorted(node_ids)) if r["pid"]}


async def touched_projects(request: Request, driver) -> set[str]:
    """Every project the request touches, directly or through what it names."""
    fields = await request_fields(request)

    def collect(names: frozenset[str]) -> set[str]:
        return set().union(*(fields.get(n, set()) for n in names))

    projects = collect(PROJECT_FIELDS)
    node_ids = collect(NODE_FIELDS)
    if node_ids:
        projects |= await asyncio.to_thread(_node_owners, driver, node_ids)
    plan_ids, source_ids = collect(PLAN_FIELDS), collect(SOURCE_FIELDS)
    catalog_ids, pir_ids = collect(CATALOG_FIELDS), collect(PIR_FIELDS)
    if plan_ids or source_ids or catalog_ids or pir_ids:
        from intel_platform.db import members

        projects |= await members.owning_projects(
            plan_ids=plan_ids, source_ids=source_ids, catalog_ids=catalog_ids, pir_ids=pir_ids,
        )
    return projects


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------

def refusal(grant: Grant, min_role: str) -> str:
    """The 403 detail for a grant that does not reach ``min_role``."""
    if grant.role is None:
        return NO_ACCESS
    return f"This needs the {min_role} role on this project; yours is {grant.role}"


async def check(request: Request, user: dict, driver, min_role: str) -> ProjectAccess:
    """Refuse the request (403) unless the caller holds ``min_role`` on every
    project it touches. A database outage while checking is a 503, never a pass."""
    if is_admin(user):
        return ProjectAccess(user=user, min_role=min_role)
    try:
        projects = await touched_projects(request, driver)
        granted = await grants(user, projects)
    except HTTPException:
        raise
    except Exception as exc:
        # Neo4j's own outage errors reach the app's 503 handler unchanged.
        from neo4j.exceptions import ServiceUnavailable, SessionExpired

        if isinstance(exc, (ServiceUnavailable, SessionExpired)):
            raise
        logger.exception("Project access check failed for %s %s", request.method, request.url.path)
        raise HTTPException(status_code=503, detail=ACCESS_UNAVAILABLE) from None
    for pid in sorted(granted):
        if not granted[pid].allows(min_role):
            raise HTTPException(status_code=403, detail=refusal(granted[pid], min_role))
    return ProjectAccess(user=user, min_role=min_role, grants=granted)
