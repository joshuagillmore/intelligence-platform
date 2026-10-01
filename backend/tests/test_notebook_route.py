from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings
from tests.ids import tp

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_create_and_list_notes():
    # Create project
    proj = client.post("/api/projects", json={"name": "Notebook Test"}, headers=headers).json()
    pid = proj["id"]

    # Create note
    resp = client.post("/api/notebook", json={
        "project_id": pid, "title": "Test Note", "content": "Test content", "note_type": "observation"
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Test Note"

    # Cleanup
    client.delete(f"/api/projects/{pid}", headers=headers)


# ---------------------------------------------------------------------------
# A-18: what the notebook says it stored is what it stored
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from intel_platform.models.entities import Person, Report  # noqa: E402

PID = tp("a18-notebook")


def _note(**overrides):
    body = {"project_id": PID, "title": "Kolvane link", "content": "c", "note_type": "hypothesis"}
    body.update(overrides)
    return client.post("/api/notebook", json=body, headers=headers)


def test_note_type_is_stored_not_just_echoed(graph_store):
    note_id = _note(note_type="hypothesis").json()["note_id"]
    assert client.get(f"/api/notebook/{note_id}", headers=headers).json()["note_type"] == "hypothesis"
    listed = client.get("/api/notebook", params={"project_id": PID}, headers=headers).json()
    assert [n["note_type"] for n in listed] == ["hypothesis"]


def test_an_unknown_note_type_is_rejected(graph_store):
    assert _note(note_type="rumour").status_code == 422


def test_notes_are_not_hidden_behind_other_reports(graph_store):
    """The list took the first 100 Reports of any kind by name and filtered in
    Python, so a project with many reports showed an empty notebook."""
    for i in range(105):
        graph_store.create_entity(Report(name=f"A report {i:03d}", project_id=PID, report_type="assessment"))
    _note(title="Zulu note")
    listed = client.get("/api/notebook", params={"project_id": PID}, headers=headers).json()
    assert [n["name"] for n in listed] == ["Zulu note"]


def test_linked_entities_counts_links_made_not_ids_sent(graph_store):
    marek = Person(name="Marek Ilyas", project_id=PID)
    graph_store.create_entity(marek)
    body = _note(entity_ids=[marek.id, "no-such-entity"]).json()
    assert body["linked_entities"] == 1
    assert body["unlinked_entity_ids"] == ["no-such-entity"]


@pytest.mark.parametrize("note_type", ["observation", "hypothesis", "question", "conclusion"])
def test_every_documented_note_type_is_accepted(graph_store, note_type):
    assert _note(note_type=note_type).status_code == 200
