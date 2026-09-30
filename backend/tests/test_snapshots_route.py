from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_create_and_list_snapshots():
    resp = client.post("/api/snapshots", json={
        "project_id": "test", "name": "Test Snapshot", "entity_ids": ["fake-id-1", "fake-id-2"]
    }, headers=headers)
    assert resp.status_code == 200
    snapshot_id = resp.json()["id"]

    # List
    resp = client.get("/api/snapshots", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1

    # Delete
    resp = client.delete(f"/api/snapshots/{snapshot_id}", headers=headers)
    assert resp.status_code == 200

def test_snapshot_not_found():
    resp = client.get("/api/snapshots/nonexistent", headers=headers)
    assert resp.status_code == 404


def test_snapshot_edges_are_listed_once_in_their_true_direction(graph_store):
    """A-11: each edge was read from both ends and reported as outgoing from
    whichever end was being read, so it appeared twice, once reversed."""
    from intel_platform.models.entities import Organization, Person, ThreatActor
    from intel_platform.models.relationships import Relationship

    pid = "test-a11-snap"
    actor = ThreatActor(name="APT Example", project_id=pid)
    victim = Organization(name="Kolvane", project_id=pid)
    handler = Person(name="Marek Ilyas", project_id=pid)
    for e in (actor, victim, handler):
        graph_store.create_entity(e)
    graph_store.create_relationship(Relationship(
        source_id=actor.id, target_id=victim.id, rel_type="TARGETS", confidence=0.8, source="t", method="t",
    ))
    graph_store.create_relationship(Relationship(
        source_id=actor.id, target_id=handler.id, rel_type="COMMANDED_BY", confidence=0.6, source="t", method="t",
    ))

    snap = client.post("/api/snapshots", json={
        "project_id": pid, "name": "Kolvane intrusion", "entity_ids": [actor.id, victim.id, handler.id],
    }, headers=headers).json()
    data = client.get(f"/api/snapshots/{snap['id']}", headers=headers).json()
    client.delete(f"/api/snapshots/{snap['id']}", headers=headers)

    got = sorted((e["source_id"], e["rel_type"], e["target_id"], e["confidence"]) for e in data["edges"])
    assert got == sorted([
        (actor.id, "TARGETS", victim.id, 0.8),
        (actor.id, "COMMANDED_BY", handler.id, 0.6),
    ])
    assert data["edge_count"] == 2
