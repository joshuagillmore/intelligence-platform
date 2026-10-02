"""Per-project access control (contract 2) and the member routes (contract 3).

Analysts sign in with real JWTs (`create_access_token`); the API key is an
admin. Neo4j holds the projects, users, entities and documents (all under this
run's prefix, `tests/ids.py`); Postgres holds membership, plans and PIRs, so
the module skips without an exported POSTGRES_URL, as `tests/pg.py` does.

The world:
- RESTRICTED: owner alice, editor bob, viewer carol; dave is no member. It
  holds an entity, a document, a PIR, a plan and a file-upload source.
- OPEN: no members, so every analyst may use it.
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from intel_platform.api.app import app
from intel_platform.api.auth import create_access_token
from intel_platform.config import settings
from tests import pg
from tests.ids import TEST_RUN, tp

pytestmark = pg.requires_postgres

client = TestClient(app)
ADMIN = {"Authorization": f"Bearer {settings.api_key}"}

RESTRICTED = tp("access-restricted")
OPEN_PROJECT = tp("access-open")
MISSING = tp("access-never-created")
NO_ACCESS = "No access to this project"


def _user(name: str) -> str:
    return tp(f"user-{name}")


def headers(name: str) -> dict:
    return {"Authorization": f"Bearer {create_access_token(_user(name), role='analyst')}"}


async def _create_schema(engine) -> None:
    from intel_platform.db import jobs  # noqa: F401  (registers collection_jobs)
    from intel_platform.db.models import Base

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_postgres(w: SimpleNamespace) -> None:
    from intel_platform.db import members
    from intel_platform.db.engine import get_session_factory
    from intel_platform.db.models import CollectionPlan, CollectionSource, Pir

    await members.put_member(RESTRICTED, _user("alice"), "owner", added_by="seed")
    await members.put_member(RESTRICTED, _user("bob"), "editor", added_by="seed")
    await members.put_member(RESTRICTED, _user("carol"), "viewer", added_by="seed")
    async with get_session_factory()() as db:
        pir = Pir(project_id=RESTRICTED, text="Who funds the cell?", eeis=["Which bank?"])
        plan = CollectionPlan(project_id=RESTRICTED, name="Restricted plan")
        open_plan = CollectionPlan(project_id=OPEN_PROJECT, name="Open plan")
        db.add_all([pir, plan, open_plan])
        await db.flush()
        source = CollectionSource(plan_id=plan.id, name="Uploads", source_type="file_upload", config={})
        db.add(source)
        await db.commit()
        w.pir_id, w.plan_id, w.open_plan_id, w.source_id = str(pir.id), str(plan.id), str(open_plan.id), str(source.id)


async def _remove_postgres() -> None:
    from intel_platform.db.engine import get_session_factory
    from intel_platform.db.models import ChunkEmbedding, CollectionPlan, CollectionSource, Pir, ProjectMember

    like = TEST_RUN + "%"
    async with get_session_factory()() as db:
        plans = (await db.execute(text("SELECT id FROM collection_plans WHERE project_id LIKE :p"), {"p": like}))
        plan_ids = plans.scalars().all()
        if plan_ids:
            await db.execute(delete(CollectionSource).where(CollectionSource.plan_id.in_(plan_ids)))
        await db.execute(delete(ChunkEmbedding).where(ChunkEmbedding.project_id.like(like)))
        await db.execute(delete(CollectionPlan).where(CollectionPlan.project_id.like(like)))
        await db.execute(delete(Pir).where(Pir.project_id.like(like)))
        await db.execute(delete(ProjectMember).where(ProjectMember.project_id.like(like)))
        await db.execute(delete(ProjectMember).where(ProjectMember.username.like(like)))
        await db.commit()


def _seed_graph(store, w: SimpleNamespace) -> None:
    from intel_platform.models.entities import Document, Person

    with store._driver.session() as session:
        for pid, name in ((RESTRICTED, "Restricted"), (OPEN_PROJECT, "Open")):
            session.run(
                "CREATE (p:Project:Entity {id: $id, project_id: $id, name: $name, description: '', "
                "classification_level: 'UNCLASSIFIED', priority: 'medium', status: 'active', "
                "created_at: '2026-10-01T00:00:00+00:00', updated_at: '2026-10-01T00:00:00+00:00', "
                "entity_type: 'Project'})",
                id=pid, name=name,
            )
        for name in ("alice", "bob", "carol", "dave", "erin"):
            session.run("CREATE (u:User {username: $u, role: 'analyst'})", u=_user(name))
    person = Person(name="Restricted Person", project_id=RESTRICTED)
    open_person = Person(name="Open Person", project_id=OPEN_PROJECT)
    doc = Document(name="Restricted memo", content="Restricted Person met a courier.", project_id=RESTRICTED)
    for entity in (person, open_person, doc):
        store.create_entity(entity)
    w.entity_id, w.open_entity_id, w.doc_id = person.id, open_person.id, doc.id


@pytest.fixture(scope="module")
def world():
    from intel_platform.db import engine as engine_module
    from intel_platform.graph.store import GraphStore

    saved = (engine_module._engine, engine_module._session_factory)
    engine = create_async_engine(pg._engine_url(), poolclass=NullPool)
    engine_module._engine = engine
    engine_module._session_factory = async_sessionmaker(engine, expire_on_commit=False)
    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    w = SimpleNamespace(created=[])
    try:
        asyncio.run(_create_schema(engine))
        asyncio.run(_remove_postgres())
        _seed_graph(GraphStore(driver), w)
        asyncio.run(_seed_postgres(w))
        yield w
    finally:
        with driver.session() as session:
            session.run("MATCH (n) WHERE n.project_id STARTS WITH $p OR n.id STARTS WITH $p DETACH DELETE n",
                        p=TEST_RUN)
            session.run("MATCH (u:User) WHERE u.username STARTS WITH $p DETACH DELETE u", p=TEST_RUN)
            for pid in w.created:
                session.run("MATCH (n) WHERE n.id = $p OR n.project_id = $p DETACH DELETE n", p=pid)
        driver.close()
        asyncio.run(_remove_postgres())
        if w.created:
            asyncio.run(_remove_members(w.created))
        asyncio.run(engine.dispose())
        engine_module._engine, engine_module._session_factory = saved


async def _remove_members(project_ids: list[str]) -> None:
    from intel_platform.db.engine import get_session_factory
    from intel_platform.db.models import ProjectMember

    async with get_session_factory()() as db:
        await db.execute(delete(ProjectMember).where(ProjectMember.project_id.in_(project_ids)))
        await db.commit()


def _members(project_id: str, who: dict = ADMIN) -> dict:
    resp = client.get(f"/api/projects/{project_id}/members", headers=who)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# The rules
# ---------------------------------------------------------------------------

class TestRoles:
    def test_admin_bypasses_membership(self, world):
        """The API key is an admin: not a member, still an owner everywhere."""
        resp = client.get(f"/api/projects/{RESTRICTED}", headers=ADMIN)
        assert resp.status_code == 200
        assert resp.json()["my_role"] == "owner" and resp.json()["access"] == "restricted"
        assert client.get(f"/api/entities/{world.entity_id}", headers=ADMIN).status_code == 200

    def test_an_admin_jwt_bypasses_too(self, world):
        token = create_access_token(_user("root"), role="admin")
        resp = client.get(f"/api/projects/{RESTRICTED}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200 and resp.json()["my_role"] == "owner"

    def test_an_open_project_is_usable_by_any_analyst(self, world):
        resp = client.get(f"/api/projects/{OPEN_PROJECT}", headers=headers("dave"))
        assert resp.status_code == 200
        assert resp.json()["access"] == "open" and resp.json()["my_role"] is None
        written = client.put(
            f"/api/entities/{world.open_entity_id}/type", json={"entity_type": "Person"}, headers=headers("dave"),
        )
        assert written.status_code == 200, written.text

    def test_a_non_member_is_refused_403_not_404(self, world):
        resp = client.get(f"/api/projects/{RESTRICTED}", headers=headers("dave"))
        assert resp.status_code == 403
        assert resp.json()["detail"] == NO_ACCESS

    def test_a_missing_project_is_404(self, world):
        assert client.get(f"/api/projects/{MISSING}", headers=headers("dave")).status_code == 404
        assert client.get(f"/api/projects/{MISSING}/members", headers=headers("dave")).status_code == 404

    def test_a_viewer_reads_but_is_refused_a_write(self, world):
        assert client.get(f"/api/entities/{world.entity_id}", headers=headers("carol")).status_code == 200
        resp = client.put(
            f"/api/entities/{world.entity_id}/type", json={"entity_type": "Person"}, headers=headers("carol"),
        )
        assert resp.status_code == 403
        assert "editor" in resp.json()["detail"]

    def test_an_editor_may_write(self, world):
        resp = client.put(
            f"/api/entities/{world.entity_id}/type", json={"entity_type": "Person"}, headers=headers("bob"),
        )
        assert resp.status_code == 200, resp.text

    def test_an_editor_may_not_delete_the_project(self, world):
        assert client.delete(f"/api/projects/{RESTRICTED}", headers=headers("bob")).status_code == 403

    def test_my_role_is_the_membership(self, world):
        for name, role in (("alice", "owner"), ("bob", "editor"), ("carol", "viewer")):
            body = client.get(f"/api/projects/{RESTRICTED}", headers=headers(name)).json()
            assert (body["my_role"], body["access"]) == (role, "restricted")


class TestResolution:
    """A request naming something a project owns is checked against that project."""

    def test_through_an_entity_id(self, world):
        assert client.get(f"/api/entities/{world.entity_id}", headers=headers("dave")).status_code == 403

    def test_through_a_document_id(self, world):
        assert client.get(f"/api/documents/{world.doc_id}", headers=headers("dave")).status_code == 403
        assert client.get(f"/api/documents/{world.doc_id}", headers=headers("carol")).status_code == 200

    def test_through_a_plan_id(self, world):
        assert client.get(f"/api/collection-plans/{world.plan_id}", headers=headers("dave")).status_code == 403
        assert client.get(f"/api/collection-plans/{world.plan_id}", headers=headers("carol")).status_code == 200

    def test_through_a_pir_id(self, world):
        assert client.get(f"/api/pirs/{world.pir_id}", headers=headers("dave")).status_code == 403
        assert client.get(f"/api/pirs/{world.pir_id}", headers=headers("carol")).status_code == 200

    def test_through_a_source_id_under_someone_elses_plan(self, world):
        """The plan in the path is open; the source in it belongs to the restricted one."""
        url = f"/api/collection-plans/{world.open_plan_id}/sources/{world.source_id}/acquisitions"
        assert client.get(url, headers=headers("dave")).status_code == 403

    def test_naming_an_open_project_does_not_open_another_projects_entity(self, world):
        resp = client.get(
            f"/api/graph/ego-network/{world.entity_id}", params={"project_id": OPEN_PROJECT}, headers=headers("dave"),
        )
        assert resp.status_code == 403

    def test_ids_in_a_json_body(self, world):
        resp = client.post("/api/entities/merge", headers=headers("dave"), json={
            "project_id": OPEN_PROJECT, "primary_id": world.open_entity_id, "merge_ids": [world.entity_id],
        })
        assert resp.status_code == 403
        # Untouched: the restricted entity still exists.
        assert client.get(f"/api/entities/{world.entity_id}", headers=ADMIN).status_code == 200

    def test_project_id_in_the_ingest_form_body(self, world):
        form = {"project_id": RESTRICTED, "content": "A courier met a banker in Vienna.", "source_name": "form"}
        assert client.post("/api/ingest", data=form, headers=headers("dave")).status_code == 403
        assert client.post("/api/ingest", data=form, headers=headers("carol")).status_code == 403
        resp = client.post("/api/ingest", data=form, headers=headers("bob"))
        assert resp.status_code == 200, resp.text
        assert resp.json()["document_id"]

    def test_project_id_in_a_multipart_upload(self, world):
        files = {"files": ("memo.txt", b"A courier met a banker.", "text/plain")}
        resp = client.post("/api/ingest/batch", data={"project_id": RESTRICTED}, files=files, headers=headers("dave"))
        assert resp.status_code == 403

    def test_project_ids_in_a_batch_delete(self, world):
        resp = client.post(
            "/api/projects/batch-delete", json={"project_ids": [OPEN_PROJECT, RESTRICTED]}, headers=headers("bob"),
        )
        assert resp.status_code == 403
        assert client.get(f"/api/projects/{OPEN_PROJECT}", headers=ADMIN).status_code == 200

    def test_an_unknown_id_touches_no_project(self, world):
        resp = client.get(f"/api/entities/{tp('no-such-entity')}", headers=headers("dave"))
        assert resp.status_code == 404


class TestLists:
    def test_the_project_list_is_filtered_server_side(self, world):
        def ids(who):
            resp = client.get("/api/projects", headers=who)
            assert resp.status_code == 200
            return {p["id"]: p for p in resp.json()}

        dave = ids(headers("dave"))
        assert RESTRICTED not in dave
        assert dave[OPEN_PROJECT]["access"] == "open" and dave[OPEN_PROJECT]["my_role"] is None
        assert ids(headers("carol"))[RESTRICTED]["my_role"] == "viewer"
        admin = ids(ADMIN)
        assert admin[RESTRICTED]["my_role"] == "owner" and admin[RESTRICTED]["access"] == "restricted"

    def test_plans_listed_without_a_project_are_filtered(self, world):
        ids = {p["id"] for p in client.get("/api/collection-plans", headers=headers("dave")).json()}
        assert world.open_plan_id in ids and world.plan_id not in ids
        ids = {p["id"] for p in client.get("/api/collection-plans", headers=headers("carol")).json()}
        assert world.plan_id in ids

    def test_legacy_collections_listed_without_a_project_are_filtered(self, world):
        mine = client.post("/api/collections", headers=headers("bob"), json={"project_id": RESTRICTED, "pir": "x"})
        assert mine.status_code == 200, mine.text
        listed = {c["id"] for c in client.get("/api/collections", headers=headers("dave")).json()}
        assert mine.json()["id"] not in listed
        assert client.get(f"/api/collections/{mine.json()['id']}", headers=headers("dave")).status_code == 403


class TestFailClosed:
    def test_a_membership_outage_is_503_not_a_pass(self, world, monkeypatch):
        from intel_platform.db import members

        async def down(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(members, "memberships", down)
        resp = client.get(f"/api/entities/{world.entity_id}", headers=headers("alice"))
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Project access could not be checked"
        # An admin needs no membership read.
        assert client.get(f"/api/entities/{world.entity_id}", headers=ADMIN).status_code == 200


# ---------------------------------------------------------------------------
# Member routes and project creation
# ---------------------------------------------------------------------------

class TestMembers:
    def test_the_member_list(self, world):
        body = _members(RESTRICTED, headers("carol"))
        assert body["access"] == "restricted" and body["my_role"] == "viewer"
        assert [(m["username"], m["role"]) for m in body["members"]] == [
            (_user("alice"), "owner"), (_user("bob"), "editor"), (_user("carol"), "viewer"),
        ]
        assert all(m["added_by"] == "seed" and m["added_at"] for m in body["members"])
        assert client.get(f"/api/projects/{RESTRICTED}/members", headers=headers("dave")).status_code == 403

    def test_an_open_project_lists_no_members(self, world):
        body = _members(OPEN_PROJECT, headers("dave"))
        assert body == {"members": [], "access": "open", "my_role": None}

    def test_only_an_owner_manages_members(self, world):
        url = f"/api/projects/{RESTRICTED}/members/{_user('dave')}"
        assert client.put(url, json={"role": "viewer"}, headers=headers("bob")).status_code == 403
        assert client.delete(f"/api/projects/{RESTRICTED}/members/{_user('carol')}",
                             headers=headers("bob")).status_code == 403

    def test_an_owner_adds_changes_and_removes_a_member(self, world):
        url = f"/api/projects/{RESTRICTED}/members/{_user('erin')}"
        added = client.put(url, json={"role": "viewer"}, headers=headers("alice"))
        assert added.status_code == 200, added.text
        assert added.json()["role"] == "viewer" and added.json()["added_by"] == _user("alice")
        assert client.get(f"/api/projects/{RESTRICTED}", headers=headers("erin")).status_code == 200

        changed = client.put(url, json={"role": "editor"}, headers=headers("alice"))
        assert changed.json()["role"] == "editor"
        assert changed.json()["added_at"] == added.json()["added_at"]

        assert client.delete(url, headers=headers("alice")).json() == {"status": "removed"}
        assert client.get(f"/api/projects/{RESTRICTED}", headers=headers("erin")).status_code == 403
        assert client.delete(url, headers=headers("alice")).status_code == 404

    def test_an_unknown_user_or_role_is_refused(self, world):
        url = f"/api/projects/{RESTRICTED}/members/{tp('user-nobody')}"
        resp = client.put(url, json={"role": "viewer"}, headers=headers("alice"))
        assert resp.status_code == 404 and resp.json()["detail"] == "No such user"
        bad = client.put(f"/api/projects/{RESTRICTED}/members/{_user('erin')}", json={"role": "boss"},
                         headers=headers("alice"))
        assert bad.status_code == 422

    def test_the_last_owner_cannot_be_removed_or_demoted(self, world):
        url = f"/api/projects/{RESTRICTED}/members/{_user('alice')}"
        removed = client.delete(url, headers=headers("alice"))
        assert removed.status_code == 409
        assert removed.json()["detail"] == "A project must keep at least one owner"
        demoted = client.put(url, json={"role": "editor"}, headers=headers("alice"))
        assert demoted.status_code == 409
        owners = [m["username"] for m in _members(RESTRICTED)["members"] if m["role"] == "owner"]
        assert owners == [_user("alice")]

    def test_a_second_owner_lets_the_first_step_down(self, world):
        alice = f"/api/projects/{RESTRICTED}/members/{_user('alice')}"
        erin = f"/api/projects/{RESTRICTED}/members/{_user('erin')}"
        assert client.put(erin, json={"role": "owner"}, headers=headers("alice")).status_code == 200
        stepped_down = client.put(alice, json={"role": "editor"}, headers=headers("erin"))
        assert stepped_down.status_code == 200 and stepped_down.json()["role"] == "editor"
        # Restore the world: alice owner again, erin gone.
        assert client.put(alice, json={"role": "owner"}, headers=headers("erin")).status_code == 200
        assert client.delete(erin, headers=headers("alice")).status_code == 200
        owners = [m["username"] for m in _members(RESTRICTED)["members"] if m["role"] == "owner"]
        assert owners == [_user("alice")]

    def test_the_first_member_of_an_open_project_must_be_an_owner(self, world):
        pid = tp("access-claimed")
        with GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)) as d:
            d.execute_query("CREATE (p:Project:Entity {id: $id, project_id: $id, name: 'Claimed'})", id=pid)
        url = f"/api/projects/{pid}/members/{_user('dave')}"
        first = client.put(url, json={"role": "editor"}, headers=headers("dave"))
        assert first.status_code == 409
        assert first.json()["detail"] == "The first member of a project must be an owner"
        # Any analyst may claim an open project, by adding an owner.
        assert client.put(url, json={"role": "owner"}, headers=headers("dave")).status_code == 200
        body = _members(pid, headers("dave"))
        assert body["access"] == "restricted" and body["my_role"] == "owner"
        assert client.get(f"/api/projects/{pid}", headers=headers("carol")).status_code == 403


class TestCreation:
    def test_the_creator_becomes_the_owner(self, world):
        resp = client.post("/api/projects", json={"name": "Dave's"}, headers=headers("dave"))
        assert resp.status_code == 200, resp.text
        pid = resp.json()["id"]
        world.created.append(pid)
        assert (resp.json()["my_role"], resp.json()["access"]) == ("owner", "restricted")
        assert [(m["username"], m["role"]) for m in _members(pid)["members"]] == [(_user("dave"), "owner")]
        assert client.get(f"/api/projects/{pid}", headers=headers("carol")).status_code == 403
        # The owner may delete it; afterwards it is simply gone.
        assert client.delete(f"/api/projects/{pid}", headers=headers("dave")).status_code == 200
        assert client.get(f"/api/projects/{pid}/members", headers=ADMIN).status_code == 404

    def test_a_project_an_admin_creates_starts_open(self, world):
        resp = client.post("/api/projects", json={"name": "Admin's"}, headers=ADMIN)
        assert resp.status_code == 200
        pid = resp.json()["id"]
        world.created.append(pid)
        assert (resp.json()["my_role"], resp.json()["access"]) == ("owner", "open")
        assert _members(pid)["members"] == []

    def test_a_failed_owner_write_does_not_leave_an_open_project(self, world, monkeypatch):
        from intel_platform.db import members

        async def down(*args, **kwargs):
            raise OSError("connection refused")

        monkeypatch.setattr(members, "add_owner", down)
        resp = client.post("/api/projects", json={"name": tp("orphan")}, headers=headers("dave"))
        assert resp.status_code == 503
        names = {p["name"] for p in client.get("/api/projects", headers=ADMIN).json()}
        assert tp("orphan") not in names


def test_member_rows_go_with_the_project(world):
    from intel_platform.db import members

    pid = tp(f"access-doomed-{uuid.uuid4().hex[:6]}")
    with GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)) as d:
        d.execute_query("CREATE (p:Project:Entity {id: $id, project_id: $id, name: 'Doomed'})", id=pid)
    asyncio.run(members.put_member(pid, _user("alice"), "owner", added_by="seed"))
    resp = client.delete(f"/api/projects/{pid}", headers=headers("alice"))
    assert resp.status_code == 200, resp.text
    assert resp.json()["relational_rows_removed"]["project_members"] == 1
    assert asyncio.run(members.memberships([pid], _user("alice"))) == {}
