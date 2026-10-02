"""Deleting a project deletes all of it, or none of it.

Project delete removed the Neo4j graph only. PIRs, requirements, plans (with
their sources, activity trail, catalog and acquisition log), chunk embeddings
and topic edits stayed in Postgres, and `/search/semantic` kept returning the
deleted project's chunks. Postgres goes first now: if it cannot be cleared,
nothing is deleted and the caller is told so, rather than removing the part
that is visible and leaving the rest behind.

Postgres is faked (the suite runs without one); Neo4j is real.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from intel_platform.api.app import app
from intel_platform.config import settings
from intel_platform.db import engine as engine_mod
from intel_platform.models.entities import Person
from tests.ids import tp

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

PROJECT_TABLES = {
    "pirs", "pir_requirements", "collection_plans", "collection_sources", "collection_activity",
    "acquisition_log", "data_catalog", "chunk_embeddings", "topic_edits", "project_members",
}


class _Result:
    rowcount = 1


class _FakeSession:
    def __init__(self, log: list, fail: bool):
        self.log, self.fail = log, fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement):
        if self.fail:
            raise OSError("connection refused")
        self.log.append(statement)
        return _Result()

    async def commit(self):
        self.log.append("COMMIT")

    async def rollback(self):
        self.log.append("ROLLBACK")


@pytest.fixture
def postgres(monkeypatch):
    state = {"log": [], "fail": False}
    monkeypatch.setattr(
        engine_mod, "get_session_factory", lambda: (lambda: _FakeSession(state["log"], state["fail"])),
    )
    return state


def _sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _deletes(log) -> dict[str, str]:
    return {s.table.name: _sql(s) for s in log if s != "COMMIT"}


def _project(graph_store, pid: str) -> str:
    with graph_store._driver.session() as session:
        session.run("CREATE (p:Project {id: $id, project_id: $id, name: 'P'})", id=pid)
    graph_store.create_entity(Person(name="Marek Ilyas", project_id=pid))
    return pid


def _node_count(graph_store, pid: str) -> int:
    with graph_store._driver.session() as session:
        return session.run("MATCH (n {project_id: $p}) RETURN count(n) AS n", p=pid).single()["n"]


class TestSingleDelete:
    def test_every_project_table_is_cleared_for_that_project(self, graph_store, postgres):
        pid = _project(graph_store, tp("a13-one"))
        resp = client.delete(f"/api/projects/{pid}", headers=headers)
        assert resp.status_code == 200
        deletes = _deletes(postgres["log"])
        assert set(deletes) == PROJECT_TABLES
        for table, sql in deletes.items():
            assert pid in sql, f"{table} delete is not scoped to the project: {sql}"
        assert postgres["log"][-1] == "COMMIT"
        assert _node_count(graph_store, pid) == 0
        # Membership goes last, in its own transaction after the graph: a delete
        # that fails half way must leave the project restricted, never open.
        tables = [s if s == "COMMIT" else s.table.name for s in postgres["log"]]
        assert tables[-2:] == ["project_members", "COMMIT"]
        assert tables.index("project_members") > tables.index("COMMIT")

    def test_a_postgres_failure_deletes_nothing(self, graph_store, postgres):
        pid = _project(graph_store, tp("a13-fail"))
        postgres["fail"] = True
        resp = client.delete(f"/api/projects/{pid}", headers=headers)
        assert resp.status_code == 503
        assert "connection refused" not in resp.text
        assert _node_count(graph_store, pid) == 2


class TestBatchDelete:
    def test_each_project_is_cleared_in_both_stores(self, graph_store, postgres):
        a = _project(graph_store, tp("a13-batch-a"))
        b = _project(graph_store, tp("a13-batch-b"))
        resp = client.post("/api/projects/batch-delete", json={"project_ids": [a, b]}, headers=headers)
        assert resp.status_code == 200
        sql = " ".join(_deletes(postgres["log"]).values())
        assert a in sql and b in sql
        assert set(_deletes(postgres["log"])) == PROJECT_TABLES
        assert _node_count(graph_store, a) == 0
        assert _node_count(graph_store, b) == 0

    def test_a_postgres_failure_deletes_nothing(self, graph_store, postgres):
        a = _project(graph_store, tp("a13-batch-fail"))
        postgres["fail"] = True
        resp = client.post("/api/projects/batch-delete", json={"project_ids": [a]}, headers=headers)
        assert resp.status_code == 503
        assert _node_count(graph_store, a) == 2

    def test_ids_that_do_not_exist_are_not_counted_as_deleted(self, graph_store, postgres):
        """Low -> A: the count was the number of ids sent, not deleted."""
        a = _project(graph_store, tp("a13-batch-real"))
        resp = client.post(
            "/api/projects/batch-delete", json={"project_ids": [a, tp("a13-never-existed")]}, headers=headers,
        )
        assert resp.json()["deleted"] == 1
