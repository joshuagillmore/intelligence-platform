"""Every by-id lookup on a hot path uses an index (review G-4).

Nodes carried only their type label (Person, Domain, ...), so a lookup by id
with no type — `MATCH (a {id: $id})` — could use no index and scanned every
node in the database. `create_relationship` did about four of those per edge,
so one 40-edge document meant ~160 full scans on the API event loop.

The fix is a shared `:Entity` label with a unique constraint on `id`: applied
on every create, added to existing nodes by `ensure_entity_label` at startup,
and used by the hot-path matches.
"""
from __future__ import annotations

import logging

import pytest

from intel_platform.graph.schema import ensure_entity_label, initialize_schema
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Organization, Person
from intel_platform.models.relationships import Relationship
from tests.ids import tp

PROJECT = tp("entity-label")

# Shared Neo4j state (drops the entity_uid constraint; database-wide ensure_entity_label counts): see tests/neo4j_lock.py.
pytestmark = pytest.mark.neo4j_global


def _labels(driver, node_id: str) -> set[str]:
    with driver.session() as s:
        return set(s.run("MATCH (n {id: $id}) RETURN labels(n) AS l", id=node_id).single()["l"])


@pytest.fixture
def schema(neo4j_driver):
    initialize_schema(neo4j_driver)
    return neo4j_driver


class TestSchema:
    def test_entity_id_is_unique_and_indexed(self, schema):
        with schema.session() as s:
            rows = s.run(
                "SHOW CONSTRAINTS YIELD labelsOrTypes, properties, type "
                "WHERE labelsOrTypes = ['Entity'] RETURN properties, type"
            ).data()
        assert any(r["properties"] == ["id"] and "UNIQUE" in r["type"] for r in rows)


class TestStartupIsNeverBlocked:
    def test_existing_entity_duplicates_do_not_stop_the_boot(self, schema):
        """initialize_schema runs unguarded in the app lifespan. If :Entity
        duplicates already exist the constraint cannot be created; the app
        must boot anyway and say why lookups are slower."""
        dup = tp("entity-label-bootdup")
        with schema.session() as s:
            s.run("DROP CONSTRAINT entity_uid IF EXISTS").consume()
        try:
            with schema.session() as s:
                s.run(
                    "CREATE (:Person:Entity {id: $id, entity_type: 'Person', project_id: $p}), "
                    "(:Organization:Entity {id: $id, entity_type: 'Organization', project_id: $p})",
                    id=dup, p=PROJECT,
                ).consume()
            initialize_schema(schema)
        finally:
            with schema.session() as s:
                s.run("MATCH (n {id: $id}) DETACH DELETE n", id=dup).consume()
            initialize_schema(schema)
        with schema.session() as s:
            names = [r["name"] for r in s.run("SHOW CONSTRAINTS YIELD name")]
        assert "entity_uid" in names, "the constraint must come back once the duplicates are gone"


class TestAppliedOnCreate:
    def test_an_entity_carries_its_type_and_the_shared_label(self, graph_store, neo4j_driver):
        p = Person(name="Marta Lind", project_id=PROJECT)
        graph_store.create_entity(p)
        assert {"Person", "Entity"} <= _labels(neo4j_driver, p.id)

    def test_a_project_carries_it_too(self, graph_store, neo4j_driver):
        project = graph_store.create_project(name="Label test", description="", classification_level="U",
                                             priority="low")
        try:
            assert "Entity" in _labels(neo4j_driver, project["id"])
        finally:
            graph_store.delete_entity(project["id"])


class TestEnsureEntityLabel:
    def _raw(self, driver, label: str, node_id: str, **extra):
        with driver.session() as s:
            s.run(
                f"CREATE (n:{label} $props)",
                props={"id": node_id, "name": node_id, "project_id": PROJECT, **extra},
            )

    def test_a_node_written_before_the_label_existed_gets_it(self, schema):
        self._raw(schema, "Person", tp("entity-label-legacy"), entity_type="Person")
        assert "Entity" not in _labels(schema, tp("entity-label-legacy"))
        assert ensure_entity_label(schema) >= 1
        assert "Entity" in _labels(schema, tp("entity-label-legacy"))

    def test_it_is_idempotent(self, schema):
        self._raw(schema, "Person", tp("entity-label-once"), entity_type="Person")
        ensure_entity_label(schema)
        assert ensure_entity_label(schema) == 0

    def test_initialize_schema_runs_it(self, schema):
        self._raw(schema, "Domain", tp("entity-label-boot"), entity_type="Domain")
        initialize_schema(schema)
        assert "Entity" in _labels(schema, tp("entity-label-boot"))

    def test_nodes_that_are_not_entities_are_left_alone(self, schema):
        """Metadata nodes have an id but no entity_type; they are not looked up
        through the store and must not share the entity id space."""
        self._raw(schema, "SomeMeta", tp("entity-label-meta"))
        ensure_entity_label(schema)
        assert "Entity" not in _labels(schema, tp("entity-label-meta"))

    def test_a_duplicate_id_is_skipped_and_logged_not_fatal(self, schema, caplog):
        """Startup must not fail on legacy data. Two nodes sharing an id cannot
        both take a label whose id is unique: one does, the other is reported."""
        self._raw(schema, "Person", tp("entity-label-dup"), entity_type="Person")
        self._raw(schema, "Organization", tp("entity-label-dup"), entity_type="Organization")
        with caplog.at_level(logging.WARNING, logger="intel_platform.graph.schema"):
            ensure_entity_label(schema)
        with schema.session() as s:
            labelled = s.run(
                "MATCH (n:Entity {id: $id}) RETURN count(n) AS c", id=tp("entity-label-dup")
            ).single()["c"]
        assert labelled == 1
        assert tp("entity-label-dup") in " ".join(r.getMessage() for r in caplog.records)


class _Recording:
    """Wraps a driver, session or transaction and records every query it runs."""

    def __init__(self, inner, log):
        self._inner = inner
        self._log = log

    def session(self, **kwargs):
        return _Recording(self._inner.session(**kwargs), self._log)

    def run(self, query, parameters=None, **kwargs):
        self._log.append((query, {**(parameters or {}), **kwargs}))
        return self._inner.run(query, parameters, **kwargs)

    def execute_write(self, fn, *args, **kwargs):
        return self._inner.execute_write(lambda tx: fn(_Recording(tx, self._log), *args, **kwargs))

    def execute_read(self, fn, *args, **kwargs):
        return self._inner.execute_read(lambda tx: fn(_Recording(tx, self._log), *args, **kwargs))

    def __enter__(self):
        self._inner.__enter__()
        return self

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _operators(plan: dict) -> list[str]:
    return [plan["operatorType"]] + [op for child in plan.get("children", []) for op in _operators(child)]


class TestHotPathsUseTheIndex:
    @pytest.fixture
    def pair(self, schema, graph_store):
        a = Person(name="Marta Lind", project_id=PROJECT)
        b = Organization(name="Halvard Shipping", project_id=PROJECT)
        graph_store.create_entity(a)
        graph_store.create_entity(b)
        return a, b

    def _scans(self, driver, calls) -> list[str]:
        log: list = []
        store = GraphStore(_Recording(driver, log))
        calls(store)
        assert log, "nothing was recorded"
        offenders = []
        with driver.session() as s:
            for query, params in log:
                plan = s.run("EXPLAIN " + query, params).consume().plan
                if any(op.startswith("AllNodesScan") for op in _operators(plan)):
                    offenders.append(" ".join(query.split())[:120])
        return offenders

    def test_create_relationship(self, schema, pair):
        a, b = pair

        def calls(store):
            for doc in ("doc-1", "doc-2"):  # create, then corroborate
                store.create_relationship(Relationship(
                    source_id=a.id, target_id=b.id, rel_type="ASSOCIATED_WITH",
                    source_doc_id=doc, project_id=PROJECT,
                ))
        assert self._scans(schema, calls) == []

    def test_reads_by_id(self, schema, pair):
        a, b = pair

        def calls(store):
            store.get_entity(a.id)
            store.update_entity(a.id, {"note": "x"})
            store.get_relationships(a.id)
            store.get_relationships_bulk([a.id, b.id])
            store.get_subgraph(a.id, hops=2, project_id=PROJECT)
            store.find_shortest_path(a.id, b.id, project_id=PROJECT)
        assert self._scans(schema, calls) == []

    def test_delete(self, schema, pair):
        a, _b = pair
        assert self._scans(schema, lambda store: store.delete_entity(a.id)) == []


class TestUnlabelledNodesStayReachable:
    """A node written by raw Cypher elsewhere since the last startup has no
    :Entity label yet. The generic by-id operations still find it."""

    def test_get_update_and_delete_fall_back(self, graph_store, neo4j_driver):
        with neo4j_driver.session() as s:
            s.run("CREATE (:Project {id: $id, project_id: $id, name: 'Raw'})", id=tp("entity-label-raw"))
        assert graph_store.get_entity(tp("entity-label-raw"))["name"] == "Raw"
        assert graph_store.update_entity(tp("entity-label-raw"), {"name": "Renamed"})["name"] == "Renamed"
        graph_store.delete_entity(tp("entity-label-raw"))
        assert graph_store.get_entity(tp("entity-label-raw")) is None
