"""Every project-scoped operation declares `require_project_access` (fail-closed).

Walks `app.openapi()`, the same surface the frontend is generated from. An
operation is project-scoped when a path or query parameter, or a JSON/form body
field, carries one of the field names the access check resolves
(`api.access.FIELDS`: project ids, and the entity, document, report, note,
snapshot, collection, plan, source, catalog and PIR ids that resolve to a
project). Every such operation must declare the dependency, and every operation
that does not is listed below with the reason, so a new route is refused by
the suite until someone has decided which it is.

Nothing here touches a database.
"""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from intel_platform.api.access import FIELDS
from intel_platform.api.app import app
from intel_platform.api.auth import require_admin

SPEC = app.openapi()
COMPONENTS = SPEC.get("components", {}).get("schemas", {})

# Operations without the dependency, and why. Admin routes (/api/admin/*, and
# those marked ADMIN here) must also declare require_admin, which the test checks.
UNGUARDED = {
    "GET /health": "liveness probe; reads no project",
    "POST /api/auth/login": "authentication",
    "POST /api/auth/logout": "authentication",
    "GET /api/auth/me": "the caller's own session",
    "POST /api/auth/change-password": "the caller's own account",
    "POST /api/auth/register": "ADMIN: creates a user",
    "GET /api/projects": "lists only the projects the caller may read; filtered in the handler",
    "POST /api/projects": "creates a new project, whose creator becomes its owner",
    "GET /api/entity-types": "the global entity type hierarchy",
    "GET /api/connector-types": "the global connector catalogue",
    "POST /api/collections/parse-plan": "parses the text it is sent; reads no project",
    "POST /api/llm/query": "a model call over the caller's own messages; reads no project",
    "GET /api/llm/skills": "the global skill catalogue",
    "GET /api/personas": "global analyst personas",
    "GET /api/personas/active": "global analyst personas",
    "POST /api/personas": "ADMIN: global analyst personas",
    "POST /api/personas/{persona_id}/activate": "ADMIN: global analyst personas",
    "DELETE /api/personas/{persona_id}": "ADMIN: global analyst personas",
    "GET /api/enrichment/providers": "the global enrichment provider catalogue",
    "GET /api/attack/status": "the shared ATT&CK catalogue's load state",
    "GET /api/attack/technique/{tid}/d3fend": "shared D3FEND reference data for a technique id",
    "POST /api/attack/ingest": "ADMIN: loads the shared ATT&CK catalogue",
    "POST /api/attack/ingest-vuln-chain": "ADMIN: loads the shared CWE/CAPEC catalogue",
    "POST /api/attack/embed": "ADMIN: embeds the shared ATT&CK catalogue",
}
ADMIN_PREFIX = "/api/admin/"

# Project-scoped operations allowed to go without the dependency. Empty: add an
# entry only with a reason a reviewer would accept.
SCOPED_UNGUARDED: dict[str, str] = {}

# Path parameters on guarded operations that the check does not resolve, and why.
UNRESOLVED_PATH_PARAMETERS = {
    "tid": "an ATT&CK technique id: shared reference data, not a project's",
    "node_id": "a topic node; the project comes from project_id in the same request",
    "username": "a member of the project in the path",
}

# POSTs that only read, so a viewer may call them.
READ_ONLY_POSTS = {
    "POST /api/query": "GraphRAG answer over the project",
    "POST /api/search/semantic": "vector search",
    "POST /api/analysis/gaps": "coverage gaps; writes nothing",
    "POST /api/graph/influence": "influence propagation; writes nothing",
    "POST /api/reports/generate": "drafts a product; saving it is POST /api/reports",
    "POST /api/topics/{entity_id}/summarize": "streams a summary; writes nothing",
}

# The operations that need owner. Claiming is also admin-only (require_admin,
# checked below); for an admin the project check passes unread.
OWNER_OPERATIONS = {
    "DELETE /api/projects/{project_id}",
    "POST /api/projects/batch-delete",
    "PUT /api/projects/{project_id}/members/{username}",
    "DELETE /api/projects/{project_id}/members/{username}",
    "POST /api/projects/{project_id}/claim",
}
ADMIN_GUARDED = {"POST /api/projects/{project_id}/claim"}


def _route(method: str, path: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path_format == path and method.upper() in route.methods:
            return route
    raise AssertionError(f"no route for {method.upper()} {path}")


def _calls(dependant) -> list:
    out = []
    for dep in dependant.dependencies:
        out.append(dep.call)
        out.extend(_calls(dep))
    return out


def _guard_roles(route: APIRoute) -> set[str]:
    return {getattr(c, "project_access_min_role") for c in _calls(route.dependant)
            if hasattr(c, "project_access_min_role")}


def _schema(schema: dict) -> dict:
    ref = schema.get("$ref")
    return COMPONENTS[ref.rsplit("/", 1)[-1]] if ref else schema


def _body_fields(operation: dict) -> set[str]:
    fields: set[str] = set()
    for media in (operation.get("requestBody", {}).get("content") or {}).values():
        fields |= set(_schema(media.get("schema", {})).get("properties", {}))
    return fields


def _scoped_fields(operation: dict) -> set[str]:
    names = {p["name"] for p in operation.get("parameters", []) if p.get("in") in ("path", "query")}
    return (names | _body_fields(operation)) & FIELDS


OPERATIONS = sorted(
    (f"{method.upper()} {path}", method, path, operation)
    for path, item in SPEC["paths"].items()
    for method, operation in item.items()
)
GUARDED = {key: _guard_roles(_route(method, path)) for key, method, path, _ in OPERATIONS}


def test_every_scoped_operation_declares_the_dependency():
    missing = [
        f"{key} ({', '.join(sorted(_scoped_fields(op)))})"
        for key, _, _, op in OPERATIONS
        if _scoped_fields(op) and not GUARDED[key] and key not in SCOPED_UNGUARDED
    ]
    assert not missing, f"project-scoped operations without require_project_access: {missing}"


def test_every_unguarded_operation_is_accounted_for():
    unaccounted = [
        key for key, _, path, _ in OPERATIONS
        if not GUARDED[key] and key not in UNGUARDED and not path.startswith(ADMIN_PREFIX)
    ]
    assert not unaccounted, (
        f"operations with no project check and no entry in UNGUARDED: {unaccounted}. Declare "
        "require_project_access, or list the operation with the reason it needs none."
    )


def test_admin_operations_require_admin():
    admin_only = [
        (key, method, path) for key, method, path, _ in OPERATIONS
        if path.startswith(ADMIN_PREFIX) or UNGUARDED.get(key, "").startswith("ADMIN") or key in ADMIN_GUARDED
    ]
    assert admin_only
    not_admin = [key for key, method, path in admin_only if require_admin not in _calls(_route(method, path).dependant)]
    assert not not_admin, f"listed as admin-only but not behind require_admin: {not_admin}"


def test_the_allowlist_has_no_stale_entries():
    keys = {key for key, *_ in OPERATIONS}
    assert set(UNGUARDED) <= keys, f"no such operation: {sorted(set(UNGUARDED) - keys)}"
    assert set(READ_ONLY_POSTS) <= keys and OWNER_OPERATIONS <= keys and ADMIN_GUARDED <= keys
    guarded_but_listed = sorted(k for k in UNGUARDED if GUARDED[k])
    assert not guarded_but_listed, f"listed as unguarded but guarded: {guarded_but_listed}"


def test_every_path_parameter_of_a_guarded_operation_is_resolved():
    unresolved = sorted(
        f"{key}: {{{p['name']}}}"
        for key, _, _, op in OPERATIONS if GUARDED[key]
        for p in op.get("parameters", [])
        if p.get("in") == "path" and p["name"] not in FIELDS and p["name"] not in UNRESOLVED_PATH_PARAMETERS
    )
    assert not unresolved, (
        f"path parameters the access check does not resolve to a project: {unresolved}. Teach "
        "api/access.py to resolve them, or list them in UNRESOLVED_PATH_PARAMETERS with the reason."
    )


@pytest.mark.parametrize("key", [k for k, *_ in OPERATIONS if GUARDED[k]])
def test_reads_need_viewer_writes_need_editor(key):
    """One role per operation: GET and read-only POSTs viewer; other writes
    editor; deleting projects and managing members owner."""
    roles = GUARDED[key]
    assert len(roles) == 1, f"{key} declares {sorted(roles)}"
    (role,) = roles
    if key in OWNER_OPERATIONS:
        expected = "owner"
    elif key.startswith("GET ") or key in READ_ONLY_POSTS:
        expected = "viewer"
    else:
        expected = "editor"
    assert role == expected, f"{key} requires {role}, expected {expected}"


def test_most_of_the_api_is_guarded():
    """A floor, so a refactor that drops the dependency wholesale cannot pass by
    also emptying what counts as scoped."""
    assert sum(1 for roles in GUARDED.values() if roles) >= 115
