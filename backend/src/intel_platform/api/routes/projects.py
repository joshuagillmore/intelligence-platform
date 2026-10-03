import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from intel_platform.api import access as project_access
from intel_platform.api.access import OPEN, OWNER, RESTRICTED, Grant, is_admin
from intel_platform.api.deps import (
    ProjectAccess,
    get_current_user,
    get_graph_store,
    project_exists,
    require_admin,
    require_project_access,
    verify_api_key,
)
from intel_platform.graph.store import GraphStore
from intel_platform.models.requests import CreateProjectRequest
from intel_platform.models.responses import (
    ProjectActivityResponse,
    ProjectBatchDeleteResponse,
    ProjectDeleteResponse,
    ProjectMemberItem,
    ProjectMembersResponse,
    ProjectResponse,
    ProjectRole,
    StatusResponse,
)
from intel_platform.services.text_utils import normalize_datetime as _normalize_datetime

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])


class BatchDeleteRequest(BaseModel):
    project_ids: list[str]


class SetMemberRequest(BaseModel):
    role: ProjectRole


# Counts for every project at once, keyed by project_id. Each is a single pass
# the planner can serve from a label or property index.
#
# One statement per count reads worse than the one query this replaced, and is
# 28x faster on a real graph (5.44s -> 0.19s for 178 projects). The old query
# was already de-N+1'd in Cypher, but `OPTIONAL MATCH (n {project_id: p.id})`
# is unlabeled, so there is no index to use and Neo4j scanned every node once
# per project — the N+1 moved into the planner instead of going away. Cost grew
# with projects x graph size, and this is the landing page: every session paid
# it before seeing anything.
_COUNT_QUERIES = {
    "entity_count": """
        MATCH (n) WHERE n.project_id IS NOT NULL AND NOT n:Project
        RETURN n.project_id AS pid, count(*) AS c
    """,
    "document_count": """
        MATCH (d:Document) WHERE d.project_id IS NOT NULL
        RETURN d.project_id AS pid, count(*) AS c
    """,
    # Both endpoints in the same project, so a cross-project edge counts for
    # neither — as before.
    "relationship_count": """
        MATCH (a)-[r]->(b)
        WHERE a.project_id IS NOT NULL AND a.project_id = b.project_id
          AND NOT (type(r) = 'MENTIONS' AND a:Document)
        RETURN a.project_id AS pid, count(r) AS c
    """,
    "collection_count": """
        MATCH (c:Collection) WHERE c.project_id IS NOT NULL
        RETURN c.project_id AS pid, count(*) AS c
    """,
}


def _project_rows(store: GraphStore) -> list[dict]:
    """Every Project node with its counts, newest first."""
    with store._driver.session() as session:
        counts = {
            field: {r["pid"]: r["c"] for r in session.run(query)}
            for field, query in _COUNT_QUERIES.items()
        }
        result = session.run(
            "MATCH (p:Project) RETURN properties(p) AS props ORDER BY p.created_at DESC"
        )
        projects = []
        for record in result:
            p = record["props"]
            pid = p.get("id", "")
            created_at = _normalize_datetime(p.get("created_at", ""))
            updated_at = _normalize_datetime(p.get("updated_at", "")) or created_at

            projects.append({
                "id": pid,
                "name": p.get("name", ""),
                "description": p.get("description", ""),
                "classification_level": p.get("classification_level", "UNCLASSIFIED"),
                "priority": p.get("priority", "medium"),
                "status": p.get("status", "active"),
                "created_at": created_at or "",
                "updated_at": updated_at or "",
                # A project with nothing in it is absent from the count maps,
                # which is a zero, not a missing value.
                "collection_count": counts["collection_count"].get(pid, 0),
                "entity_count": counts["entity_count"].get(pid, 0),
                "document_count": counts["document_count"].get(pid, 0),
                "relationship_count": counts["relationship_count"].get(pid, 0),
            })
    return projects


def _project_response(project: dict, stats: dict, grant: Grant, collection_count: int | None = None) -> ProjectResponse:
    extra = {} if collection_count is None else {"collection_count": collection_count}
    return ProjectResponse(
        id=project["id"], name=project["name"], description=project["description"],
        classification_level=project["classification_level"], priority=project["priority"],
        status=project["status"],
        created_at=_normalize_datetime(project.get("created_at", "")),
        updated_at=_normalize_datetime(project.get("updated_at", "")),
        my_role=grant.role, access=grant.access,
        **extra,
        **stats,
    )


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(store: GraphStore = Depends(get_graph_store), user: dict = Depends(get_current_user)):
    """The projects the caller may read, newest first, each with their role on it.

    Filtered here, not in the client: an admin sees every project; anyone else
    sees the open ones (no members) and those they are a member of.
    """
    rows = await asyncio.to_thread(_project_rows, store)
    granted = await project_access.load_grants(user, (r["id"] for r in rows))
    admin = is_admin(user)
    visible = []
    for row in rows:
        # A Project node without an id holds no members.
        grant = granted.get(row["id"]) or Grant(role=OWNER if admin else None, access=OPEN)
        if admin or grant.allows("viewer"):
            visible.append({**row, "my_role": grant.role, "access": grant.access})
    return visible


def _delete_project_node(store: GraphStore, project_id: str) -> None:
    with store._driver.session() as session:
        session.run("MATCH (p:Project {id: $id}) DETACH DELETE p", id=project_id)


@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    req: CreateProjectRequest,
    store: GraphStore = Depends(get_graph_store),
    user: dict = Depends(get_current_user),
):
    """Create a project. Its creator becomes its owner, which makes it restricted.

    That includes an admin. An admin is an implicit owner of every project
    anyway, but a project with no members is open to every signed-in user, so
    an admin's project is given its owner row like anyone else's (the API key's
    identity, ``api_key_user``, when it is the creator).
    """
    from intel_platform.db import members

    project = await asyncio.to_thread(
        store.create_project,
        name=req.name, description=req.description,
        classification_level=req.classification_level, priority=req.priority,
    )
    try:
        await members.add_owner(project["id"], user["username"])
    except Exception:
        # Without its owner row the project would be open to everyone, so it
        # is not kept.
        logger.exception("Recording the owner of new project %s failed; removing it", project["id"])
        await asyncio.to_thread(_delete_project_node, store, project["id"])
        raise HTTPException(status_code=503, detail="The project could not be created. Try again.")
    grant = Grant(role=OWNER, access=RESTRICTED)
    stats = await asyncio.to_thread(store.get_project_stats, project["id"])
    return _project_response(project, stats, grant)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    store: GraphStore = Depends(get_graph_store),
    access: ProjectAccess = Depends(require_project_access("viewer")),
):
    project = await asyncio.to_thread(store.get_project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    stats = await asyncio.to_thread(store.get_project_stats, project_id)
    try:
        from intel_platform.api.routes.collections import _get_collection_count
        coll_count = await asyncio.to_thread(_get_collection_count, store, project_id)
    except Exception:
        coll_count = 0
    grant = await project_access.grant_on(access, project_id)
    return _project_response(project, stats, grant, collection_count=coll_count)


@router.put("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    req: CreateProjectRequest,
    store: GraphStore = Depends(get_graph_store),
    access: ProjectAccess = Depends(require_project_access("editor")),
):
    project = await asyncio.to_thread(store.get_project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    def update() -> tuple[dict, dict]:
        store.update_project(project_id, name=req.name, description=req.description,
                             classification_level=req.classification_level, priority=req.priority)
        return store.get_project(project_id), store.get_project_stats(project_id)

    updated, stats = await asyncio.to_thread(update)
    grant = await project_access.grant_on(access, project_id)
    return _project_response(updated, stats, grant)


async def _delete_relational_rows(project_ids: list[str]) -> dict[str, int]:
    """Delete every Postgres row belonging to these projects, in one transaction.

    Children go before parents, explicitly: the plan tables declare ON DELETE
    CASCADE, but a table created before a constraint existed would not have it,
    and a delete that half-works is the failure this replaces.

    Membership is not among them: it goes last (``_delete_memberships``), once
    the graph is gone, so a delete that fails half way leaves the project
    restricted rather than open.
    """
    from sqlalchemy import delete, select

    from intel_platform.db.engine import get_session_factory
    from intel_platform.db.models import (
        AcquisitionLog, ChunkEmbedding, CollectionActivity, CollectionPlan, CollectionSource,
        DataCatalog, Pir, PirRequirement, TopicEdit,
    )

    plan_ids = select(CollectionPlan.id).where(CollectionPlan.project_id.in_(project_ids))
    statements = [
        delete(AcquisitionLog).where(AcquisitionLog.plan_id.in_(plan_ids)),
        delete(CollectionActivity).where(CollectionActivity.plan_id.in_(plan_ids)),
        delete(DataCatalog).where(DataCatalog.plan_id.in_(plan_ids)),
        delete(CollectionSource).where(CollectionSource.plan_id.in_(plan_ids)),
        delete(CollectionPlan).where(CollectionPlan.project_id.in_(project_ids)),
        delete(PirRequirement).where(PirRequirement.project_id.in_(project_ids)),
        delete(Pir).where(Pir.project_id.in_(project_ids)),
        delete(ChunkEmbedding).where(ChunkEmbedding.project_id.in_(project_ids)),
        delete(TopicEdit).where(TopicEdit.project_id.in_(project_ids)),
    ]
    removed: dict[str, int] = {}
    async with get_session_factory()() as session:
        for statement in statements:
            result = await session.execute(statement)
            removed[statement.table.name] = result.rowcount or 0
        await session.commit()
    return removed


async def _delete_memberships(project_ids: list[str]) -> dict[str, int]:
    """Remove the deleted projects' member rows; ``{}`` when that fails.

    A row left behind is harmless: it names a project that no longer exists,
    and keeps any data later written under that id restricted to its old
    members rather than open.
    """
    from sqlalchemy import delete

    from intel_platform.db.engine import get_session_factory
    from intel_platform.db.models import ProjectMember

    statement = delete(ProjectMember).where(ProjectMember.project_id.in_(project_ids))
    try:
        async with get_session_factory()() as session:
            result = await session.execute(statement)
            await session.commit()
    except Exception:
        logger.exception("Project delete: member rows for %s were not removed", project_ids)
        return {}
    return {statement.table.name: result.rowcount or 0}


async def _delete_projects(store: GraphStore, project_ids: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Delete projects from Postgres, then Neo4j. Postgres first: if it cannot be
    cleared, nothing has been deleted and the request can simply be retried.

    Returns (Neo4j nodes removed per project, Postgres rows removed per table).
    Raises 503 when Postgres fails; the detail carries no internal error text.
    """
    try:
        rows = await _delete_relational_rows(project_ids)
    except Exception:
        logger.exception("Project delete: Postgres cleanup failed for %s; nothing deleted", project_ids)
        raise HTTPException(
            status_code=503,
            detail="The project's stored documents and plans could not be removed; nothing was deleted. Try again.",
        )

    def delete_graph() -> dict[str, int]:
        nodes: dict[str, int] = {}
        with store._driver.session() as session:
            for pid in project_ids:
                record = session.run(
                    "MATCH (n {project_id: $pid}) DETACH DELETE n RETURN count(n) AS deleted", pid=pid,
                ).single()
                # A Project node written without its own project_id property.
                extra = session.run(
                    "MATCH (p:Project {id: $pid}) DETACH DELETE p RETURN count(p) AS deleted", pid=pid,
                ).single()
                nodes[pid] = (record["deleted"] if record else 0) + (extra["deleted"] if extra else 0)
        return nodes

    nodes = await asyncio.to_thread(delete_graph)
    from intel_platform.services.graph_cache import graph_cache
    for pid in project_ids:
        graph_cache.invalidate(pid)
    rows.update(await _delete_memberships(project_ids))
    return nodes, rows


@router.post(
    "/projects/batch-delete", response_model=ProjectBatchDeleteResponse,
    dependencies=[Depends(require_project_access("owner"))],
)
async def batch_delete_projects(req: BatchDeleteRequest, store: GraphStore = Depends(get_graph_store)):
    project_ids = list(dict.fromkeys(req.project_ids))
    nodes, rows = await _delete_projects(store, project_ids)
    # Only ids that held anything count; an id that never existed was not deleted.
    return {"deleted": sum(1 for n in nodes.values() if n), "relational_rows_removed": rows}


@router.delete(
    "/projects/{project_id}", response_model=ProjectDeleteResponse,
    dependencies=[Depends(require_project_access("owner"))],
)
async def delete_project(project_id: str, store: GraphStore = Depends(get_graph_store)):
    nodes, rows = await _delete_projects(store, [project_id])
    return {"status": "deleted", "entities_removed": nodes[project_id], "relational_rows_removed": rows}


@router.get(
    "/projects/{project_id}/activity", response_model=ProjectActivityResponse,
    dependencies=[Depends(require_project_access("viewer"))],
)
def get_project_activity(
    project_id: str, limit: int = Query(20, ge=1, le=500), store: GraphStore = Depends(get_graph_store),
):
    """Get recent activity for a project."""
    entities = store.search_entities(project_id=project_id, limit=limit)

    activity = []
    for e in entities:
        created = _normalize_datetime(e.get("created_at", ""))

        etype = e.get("entity_type", "")
        if etype == "Document":
            action = "Document ingested"
        elif etype == "Report":
            action = "Report generated"
        elif etype == "Assessment":
            action = "Assessment created"
        else:
            action = f"{etype} extracted"

        activity.append({
            "id": e.get("id", ""),
            "action": action,
            "entity_name": e.get("name", ""),
            "entity_type": etype,
            "timestamp": created,
        })

    activity.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return {"activity": activity[:limit], "count": len(activity)}


# ---------------------------------------------------------------------------
# Members (contract 3). The rules are in api/access.py and db/members.py.
# ---------------------------------------------------------------------------

async def _require_project(store: GraphStore, project_id: str) -> None:
    if not await asyncio.to_thread(project_exists, store, project_id):
        raise HTTPException(status_code=404, detail="Project not found")


def _user_exists(store: GraphStore, username: str) -> bool:
    with store._driver.session() as session:
        return session.run("MATCH (u:User {username: $u}) RETURN count(u) AS n", u=username).single()["n"] > 0


def _member_item(row) -> dict:
    return {
        "username": row.username,
        "role": row.role,
        "added_by": row.added_by or "",
        "added_at": row.added_at.isoformat() if row.added_at else "",
    }


def _membership_unavailable() -> HTTPException:
    logger.exception("Project membership could not be read or written")
    return HTTPException(status_code=503, detail=project_access.ACCESS_UNAVAILABLE)


@router.get("/projects/{project_id}/members", response_model=ProjectMembersResponse)
async def list_project_members(
    project_id: str,
    store: GraphStore = Depends(get_graph_store),
    access: ProjectAccess = Depends(require_project_access("viewer")),
):
    """The project's members (owners first), whether it is open, and the caller's role."""
    from intel_platform.db import members

    await _require_project(store, project_id)
    try:
        rows = await members.list_members(project_id)
    except Exception:
        raise _membership_unavailable() from None
    grant = await project_access.grant_on(access, project_id)
    return {
        "members": [_member_item(r) for r in rows],
        "access": RESTRICTED if rows else OPEN,
        "my_role": grant.role,
    }


@router.put("/projects/{project_id}/members/{username}", response_model=ProjectMemberItem)
async def put_project_member(
    project_id: str,
    username: str,
    req: SetMemberRequest,
    store: GraphStore = Depends(get_graph_store),
    access: ProjectAccess = Depends(require_project_access("owner")),
):
    """Add a member or change their role (owners only; anyone on an open project).

    409 when the project has no members and the role is not owner (the first
    member closes the project, so it must be someone who can manage it), or when
    the change would leave the project without an owner.
    """
    from intel_platform.db import members

    await _require_project(store, project_id)
    if not await asyncio.to_thread(_user_exists, store, username):
        raise HTTPException(status_code=404, detail="No such user")
    try:
        row = await members.put_member(project_id, username, req.role, added_by=access.username)
    except members.MembershipRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception:
        raise _membership_unavailable() from None
    return _member_item(row)


@router.post(
    "/projects/{project_id}/claim", response_model=ProjectMemberItem,
    dependencies=[Depends(require_admin)],
)
async def claim_project(
    project_id: str,
    store: GraphStore = Depends(get_graph_store),
    access: ProjectAccess = Depends(require_project_access("owner")),
):
    """Make the calling admin the owner of an open project, which restricts it (admins only).

    For projects still open: those made before membership existed, and those
    an admin made before admins became the owners of what they create. 404 for
    an unknown project; 409 when it already has members (add yourself through
    the members route instead). Checking that it is open and adding the owner
    are one transaction, so two admins cannot both claim it.
    """
    from intel_platform.db import members

    await _require_project(store, project_id)
    try:
        row = await members.claim_open_project(project_id, access.username)
    except members.MembershipRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception:
        raise _membership_unavailable() from None
    return _member_item(row)


@router.delete(
    "/projects/{project_id}/members/{username}", response_model=StatusResponse,
    dependencies=[Depends(require_project_access("owner"))],
)
async def remove_project_member(project_id: str, username: str, store: GraphStore = Depends(get_graph_store)):
    """Remove a member (owners only). 409 for the project's last owner."""
    from intel_platform.db import members

    await _require_project(store, project_id)
    try:
        await members.remove_member(project_id, username)
    except members.NotAMemberError:
        raise HTTPException(status_code=404, detail="Not a member of this project") from None
    except members.MembershipRuleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception:
        raise _membership_unavailable() from None
    return {"status": "removed"}
