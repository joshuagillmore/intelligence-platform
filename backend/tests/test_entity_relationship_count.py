"""Every entity listed carries its degree, `relationship_count` (contract 4).

The cyber IOC table had a "relations" column reading `relationship_count`,
which `GET /entities` never sent, so every row showed "--". The count is the
entity's degree over the knowledge graph: every edge touching it except the
(:Document)-[:MENTIONS]->(:Entity) edges that record where it was extracted
from, the same edges `get_relationships` leaves out.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.config import settings
from intel_platform.models.entities import Document, IPAddress, Malware
from intel_platform.models.relationships import Relationship
from intel_platform.models.responses import EntityProperties
from tests.ids import tp

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def _seed(store, project: str) -> tuple[str, str, str]:
    """Two entities joined by one edge; a document mentioning one of them."""
    ip = store.create_entity(IPAddress(name="203.0.113.7", project_id=project))["id"]
    malware = store.create_entity(Malware(name="SUNBURST", project_id=project))["id"]
    doc = Document(name="Advisory", project_id=project, content="SUNBURST beacons to 203.0.113.7.")
    store.create_entity(doc)
    store.create_relationship(Relationship(
        source_id=malware, target_id=ip, rel_type="COMMUNICATES_WITH", project_id=project, confidence=0.9,
    ))
    assert store.record_mentions(project, {(doc.id, malware): 2, (doc.id, ip): 1}) == 2
    return ip, malware, doc.id


def test_each_listed_entity_counts_its_edges_but_not_its_document_mentions(graph_store):
    project = tp("rel-count-store")
    ip, malware, doc_id = _seed(graph_store, project)

    counts = {n["id"]: n["relationship_count"] for n in graph_store.search_entities(project_id=project)}
    assert counts == {ip: 1, malware: 1, doc_id: 0}
    # The same edges the entity's own relationship list shows.
    assert counts[malware] == len(graph_store.get_relationships(malware))


def test_an_entity_with_no_edges_counts_zero_and_filters_still_apply(graph_store):
    project = tp("rel-count-filters")
    ip, _, _ = _seed(graph_store, project)
    graph_store.create_entity(IPAddress(name="198.51.100.1", project_id=project))

    rows = graph_store.search_entities(project_id=project, entity_type="IPAddress")
    assert [(n["name"], n["relationship_count"]) for n in rows] == [("198.51.100.1", 0), ("203.0.113.7", 1)]
    page = graph_store.search_entities(project_id=project, entity_type="IPAddress", limit=1, offset=1)
    assert [(n["id"], n["relationship_count"]) for n in page] == [(ip, 1)]
    assert [n["name"] for n in graph_store.search_entities(project_id=project, query="sunburst")] == ["SUNBURST"]


def test_a_second_edge_and_a_self_loop_count_once_each(graph_store):
    project = tp("rel-count-multi")
    ip, malware, _ = _seed(graph_store, project)
    graph_store.create_relationship(Relationship(
        source_id=ip, target_id=malware, rel_type="ASSOCIATED_WITH", project_id=project, confidence=0.9,
    ))
    graph_store.create_relationship(Relationship(
        source_id=malware, target_id=malware, rel_type="RELATED_TO", project_id=project, confidence=0.9,
    ))
    counts = {n["id"]: n["relationship_count"] for n in graph_store.search_entities(project_id=project)}
    assert counts[ip] == 2
    assert counts[malware] == 3


def test_the_entities_route_sends_it_on_every_item(graph_store):
    project = tp("rel-count-route")
    ip, malware, doc_id = _seed(graph_store, project)

    resp = client.get("/api/entities", params={"project_id": project}, headers=headers)
    assert resp.status_code == 200, resp.text
    counts = {item["id"]: item["relationship_count"] for item in resp.json()}
    assert counts == {ip: 1, malware: 1, doc_id: 0}


def test_the_response_model_declares_it():
    field = EntityProperties.model_fields["relationship_count"]
    assert field.annotation == int | None
