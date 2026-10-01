"""One node per entity: (project_id, normalized_name, entity_type) is unique.

`create_entity` was a bare CREATE behind a fulltext lookup. Two builds that met
the same entity at once — the agentic loop ingests sources concurrently — both
looked, both found nothing, and both created it, so the graph split one actor
across two nodes and every analytic read it twice. Resolution could not close
that: the race is between the lookup and the write.

The fix is a uniqueness constraint on (project_id, normalized_name,
entity_type) for :Entity, and `create_entity` as a single MERGE on that key, so
the database rather than the lookup decides. Review focus 5.
"""
from __future__ import annotations

import logging
import threading
import uuid

import pytest

from intel_platform.graph.schema import ENTITY_NAME_KEY, ensure_normalized_names, initialize_schema
from intel_platform.models.entities import (
    Assessment, Document, Organization, Person, Report, normalize_name,
)
from intel_platform.models.relationships import Relationship
from intel_platform.services.graph_builder import build_graph_from_extractions

PROJECT = "test-entity-uniqueness"


@pytest.fixture
def schema(neo4j_driver):
    initialize_schema(neo4j_driver)
    return neo4j_driver


def _nodes(driver, name_key: str, project: str = PROJECT) -> list[dict]:
    with driver.session() as s:
        return [dict(r["n"]) for r in s.run(
            "MATCH (n:Entity {project_id: $p, normalized_name: $k}) RETURN n", p=project, k=name_key,
        )]


class TestNormalizedName:
    @pytest.mark.parametrize("raw, expected", [
        ("Orion Holdings", "orion holdings"),
        ("  Orion\t  Holdings \n", "orion holdings"),
        ("'Orion Holdings.'", "orion holdings"),
        ("“Orion Holdings”,", "orion holdings"),
        ("(Orion Holdings)", "orion holdings"),
        ("U.S. Navy", "u.s. navy"),
    ])
    def test_lower_collapsed_and_trimmed(self, raw, expected):
        assert normalize_name(raw) == expected

    @pytest.mark.parametrize("name", ["C#", "100%", "AT&T", "C++"])
    def test_meaningful_symbols_survive(self, name):
        assert normalize_name(name) == name.lower()

    def test_the_model_carries_it(self):
        assert Person(name=" Marek  Ilyas.", project_id=PROJECT).normalized_name == "marek ilyas"

    @pytest.mark.parametrize("cls", [Document, Report, Assessment])
    def test_records_are_not_keyed_by_name(self, cls):
        assert cls(name="text_input", project_id=PROJECT).normalized_name is None

    def test_a_name_of_only_punctuation_is_not_keyed(self):
        assert Organization(name="...", project_id=PROJECT).normalized_name is None


class TestConstraint:
    def test_the_key_is_a_uniqueness_constraint_on_entity(self, schema):
        with schema.session() as s:
            row = s.run(
                "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties WHERE name = $n "
                "RETURN type, labelsOrTypes, properties",
                n=ENTITY_NAME_KEY,
            ).single()
        assert row is not None, "the entity name-key constraint was not created"
        assert row["type"] == "UNIQUENESS"
        assert row["labelsOrTypes"] == ["Entity"]
        assert row["properties"] == ["project_id", "normalized_name", "entity_type"]


class TestCreateEntityMerges:
    def test_the_same_entity_twice_is_one_node(self, schema, graph_store):
        first = Organization(name="Orion Holdings", project_id=PROJECT)
        second = Organization(name="orion  holdings.", project_id=PROJECT)
        a = graph_store.create_entity(first)
        b = graph_store.create_entity(second)
        assert a["id"] == first.id
        assert b["id"] == first.id, "the second create returns the node that already holds the key"
        assert len(_nodes(schema, "orion holdings")) == 1

    def test_the_first_writer_keeps_its_name_and_properties(self, schema, graph_store):
        graph_store.create_entity(Organization(name="Orion Holdings", project_id=PROJECT, org_type="shipping"))
        graph_store.create_entity(Organization(name="ORION HOLDINGS", project_id=PROJECT, org_type="other"))
        [node] = _nodes(schema, "orion holdings")
        assert node["name"] == "Orion Holdings"
        assert node["org_type"] == "shipping"

    def test_a_different_type_is_a_different_entity(self, schema, graph_store):
        graph_store.create_entity(Organization(name="Wagner", project_id=PROJECT))
        graph_store.create_entity(Person(name="Wagner", project_id=PROJECT))
        assert {n["entity_type"] for n in _nodes(schema, "wagner")} == {"Organization", "Person"}

    def test_a_different_project_is_a_different_entity(self, schema, graph_store):
        graph_store.create_entity(Organization(name="Orion Holdings", project_id=PROJECT))
        graph_store.create_entity(Organization(name="Orion Holdings", project_id=PROJECT + "-b"))
        assert len(_nodes(schema, "orion holdings")) == 1
        assert len(_nodes(schema, "orion holdings", PROJECT + "-b")) == 1

    def test_documents_with_one_name_stay_separate(self, schema, graph_store):
        a = Document(name="text_input", project_id=PROJECT, content="first")
        b = Document(name="text_input", project_id=PROJECT, content="second")
        assert graph_store.create_entity(a)["id"] == a.id
        assert graph_store.create_entity(b)["id"] == b.id
        with schema.session() as s:
            n = s.run("MATCH (d:Document {project_id: $p, name: 'text_input'}) RETURN count(d) AS n", p=PROJECT)
            assert n.single()["n"] == 2

    def test_the_node_keeps_its_type_label_and_entity_label(self, schema, graph_store):
        person = Person(name="Marek Ilyas", project_id=PROJECT)
        graph_store.create_entity(person)
        with schema.session() as s:
            labels = set(s.run("MATCH (n {id: $id}) RETURN labels(n) AS l", id=person.id).single()["l"])
        assert labels == {"Person", "Entity"}


class TestRetype:
    def test_a_retype_onto_a_taken_key_is_a_conflict(self, schema, graph_store):
        """The type is part of the key: retyping onto a name that type already
        holds would make two nodes for one entity. 409, and nothing changes."""
        from fastapi.testclient import TestClient

        from intel_platform.api.app import app
        from intel_platform.config import settings

        org = Organization(name="Wagner", project_id=PROJECT)
        person = Person(name="Wagner", project_id=PROJECT)
        graph_store.create_entity(org)
        graph_store.create_entity(person)
        resp = TestClient(app).put(
            f"/api/entities/{person.id}/type", json={"entity_type": "Organization"},
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )
        assert resp.status_code == 409
        assert graph_store.get_entity(person.id)["entity_type"] == "Person"
        with schema.session() as s:
            labels = set(s.run("MATCH (n {id: $id}) RETURN labels(n) AS l", id=person.id).single()["l"])
        assert labels == {"Person", "Entity"}, "the label swap rolled back with the type"


class TestConcurrentBuilds:
    """Review focus 5: two builds create the same entity at once."""

    WORKERS = 8

    def test_concurrent_builds_of_one_entity_make_one_node(self, schema, graph_store):
        barrier = threading.Barrier(self.WORKERS)
        errors: list[BaseException] = []
        # Different surface forms of one name: the key, not the string, decides.
        spellings = ["Kestrel Maritime", "kestrel maritime", "Kestrel  Maritime.", "'Kestrel Maritime'"]

        def build(i: int) -> None:
            barrier.wait()
            try:
                build_graph_from_extractions(
                    graph_store,
                    [{"name": spellings[i % len(spellings)], "entity_type": "Organization"}],
                    [], project_id=PROJECT, source_doc_id=f"doc-{i}",
                )
            except BaseException as exc:  # noqa: BLE001 — surfaced by the assert below
                errors.append(exc)

        threads = [threading.Thread(target=build, args=(i,)) for i in range(self.WORKERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        nodes = _nodes(schema, "kestrel maritime")
        assert len(nodes) == 1, f"{len(nodes)} nodes for one entity"
        # Every build's document is on the surviving node, none lost to the race.
        assert sorted(nodes[0]["source_doc_ids"]) == sorted(f"doc-{i}" for i in range(self.WORKERS))

    def test_two_threads_creating_directly_make_one_node(self, schema, graph_store):
        barrier = threading.Barrier(2)
        ids: list[str] = []
        errors: list[BaseException] = []

        def create() -> None:
            barrier.wait()
            try:
                ids.append(graph_store.create_entity(Organization(name="Twin Build", project_id=PROJECT))["id"])
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=create) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert len(_nodes(schema, "twin build")) == 1
        assert len(set(ids)) == 1, "both callers are told the id of the one node"


class TestBackfill:
    """Contract 7: nodes written before the key get it at startup, and the
    duplicates that exposes are merged the way the merge route merges."""

    @staticmethod
    def _legacy(driver, label: str, name: str, created: str, **props) -> str:
        """A node as the old CREATE wrote it: labelled, no normalized_name."""
        node_id = f"legacy-{uuid.uuid4()}"
        with driver.session() as s:
            s.run(
                f"CREATE (n:{label}:Entity $props)",
                props={"id": node_id, "name": name, "entity_type": label, "project_id": PROJECT,
                       "created_at": created, **props},
            )
        return node_id

    @staticmethod
    def _edges(driver, node_id: str) -> set[tuple[str, str, str]]:
        with driver.session() as s:
            return {
                (r["a"], r["t"], r["b"]) for r in s.run(
                    "MATCH (a)-[r]->(b) WHERE a.id = $id OR b.id = $id RETURN a.id AS a, type(r) AS t, b.id AS b",
                    id=node_id,
                )
            }

    def test_duplicates_are_merged_into_the_earliest_keeping_edge_direction(self, schema, graph_store, caplog):
        first = self._legacy(schema, "Organization", "Orion Holdings", "2025-01-01T00:00:00+00:00",
                             source_doc_id="doc-a", source_doc_ids=["doc-a"])
        dup = self._legacy(schema, "Organization", "orion holdings.", "2025-02-01T00:00:00+00:00",
                           source_doc_id="doc-b", source_doc_ids=["doc-b"])
        target = Organization(name="Backfill Target", project_id=PROJECT)
        actor = Person(name="Backfill Actor", project_id=PROJECT)
        graph_store.create_entity(target)
        graph_store.create_entity(actor)
        graph_store.create_relationship(Relationship(
            source_id=dup, target_id=target.id, rel_type="TARGETS", project_id=PROJECT, evidence="dup targets"))
        graph_store.create_relationship(Relationship(
            source_id=actor.id, target_id=dup, rel_type="USES", project_id=PROJECT, evidence="actor uses dup"))

        with caplog.at_level(logging.INFO, logger="intel_platform.graph.schema"):
            outcome = ensure_normalized_names(schema)

        assert outcome["merged"] >= 1
        assert graph_store.get_entity(dup) is None
        survivor = graph_store.get_entity(first)
        assert survivor["normalized_name"] == "orion holdings"
        assert survivor["name"] == "Orion Holdings"
        assert self._edges(schema, first) == {(first, "TARGETS", target.id), (actor.id, "USES", first)}
        assert survivor["source_doc_ids"] == ["doc-a", "doc-b"]
        assert any("Merged duplicate" in r.getMessage() and dup in r.getMessage() for r in caplog.records)

    def test_a_legacy_duplicate_of_a_keyed_node_merges_into_the_keyed_node(self, schema, graph_store):
        keyed = Organization(name="Kestrel Maritime", project_id=PROJECT)
        graph_store.create_entity(keyed)
        # Older by created_at, but the node that already holds the key wins.
        legacy = self._legacy(schema, "Organization", "KESTREL MARITIME", "2020-01-01T00:00:00+00:00")
        ensure_normalized_names(schema)
        assert graph_store.get_entity(legacy) is None
        assert [n["id"] for n in _nodes(schema, "kestrel maritime")] == [keyed.id]

    def test_a_lone_legacy_node_is_only_named(self, schema, graph_store):
        lone = self._legacy(schema, "Person", "  Marek   Ilyas ", "2025-01-01T00:00:00+00:00")
        ensure_normalized_names(schema)
        assert graph_store.get_entity(lone)["normalized_name"] == "marek ilyas"

    def test_records_are_left_alone(self, schema, graph_store):
        a = self._legacy(schema, "Document", "text_input", "2025-01-01T00:00:00+00:00")
        b = self._legacy(schema, "Document", "text_input", "2025-01-02T00:00:00+00:00")
        ensure_normalized_names(schema)
        for doc_id in (a, b):
            node = graph_store.get_entity(doc_id)
            assert node is not None
            assert "normalized_name" not in node

    def test_it_is_idempotent(self, schema):
        self._legacy(schema, "Organization", "Idem Corp", "2025-01-01T00:00:00+00:00")
        self._legacy(schema, "Organization", "idem corp", "2025-01-02T00:00:00+00:00")
        ensure_normalized_names(schema)
        assert ensure_normalized_names(schema) == {"named": 0, "merged": 0, "kept": 0}
        assert len(_nodes(schema, "idem corp")) == 1

    def test_initialize_schema_merges_before_creating_the_constraint(self, neo4j_driver):
        """A database holding legacy duplicates still gets the constraint."""
        with neo4j_driver.session() as s:
            s.run(f"DROP CONSTRAINT {ENTITY_NAME_KEY} IF EXISTS").consume()
        self._legacy(neo4j_driver, "Organization", "Boot Corp", "2025-01-01T00:00:00+00:00")
        self._legacy(neo4j_driver, "Organization", "boot corp", "2025-01-02T00:00:00+00:00")
        initialize_schema(neo4j_driver)
        assert len(_nodes(neo4j_driver, "boot corp")) == 1
        with neo4j_driver.session() as s:
            assert s.run("SHOW CONSTRAINTS YIELD name WHERE name = $n RETURN name", n=ENTITY_NAME_KEY).single()
