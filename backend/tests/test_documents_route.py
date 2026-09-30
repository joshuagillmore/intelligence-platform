from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_list_documents():
    resp = client.get("/api/documents", params={"project_id": "test"}, headers=headers)
    assert resp.status_code == 200
    assert "documents" in resp.json()

def test_get_document_not_found():
    resp = client.get("/api/documents/nonexistent", headers=headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Entities are linked to their document by source_doc_id, not by edges (A-6)
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from intel_platform.models.entities import Document, Organization, Person  # noqa: E402

PID = "test-a6-docs"


@pytest.fixture
def corpus(graph_store):
    """Two documents; entities point back at them the way ingestion writes them.

    Nothing in ingestion creates an edge to a Document — `graph_builder` sets
    `source_doc_id` on each entity — so the old edge count read 0 for every
    document. `source_doc_ids` is the list the store package appends when a
    later document mentions an existing entity (G-11).
    """
    d1 = Document(name="A first report", project_id=PID, content="x" * 1234)
    d2 = Document(name="B second report", project_id=PID, content="Marek Ilyas met Kolvane.")
    for d in (d1, d2):
        graph_store.create_entity(d)
    marek = Person(name="Marek Ilyas", project_id=PID, source_doc_id=d1.id)
    kolvane = Organization(name="Kolvane", project_id=PID, source_doc_id=d1.id)
    graph_store.create_entity(marek)
    graph_store.create_entity(kolvane)
    other = Person(name="Only In Second", project_id=PID, source_doc_id=d2.id)
    graph_store.create_entity(other)
    # Kolvane was also found in d2: the store appends it to source_doc_ids.
    graph_store.update_entity(kolvane.id, {"source_doc_ids": [d1.id, d2.id]})
    return {"d1": d1.id, "d2": d2.id, "marek": marek.id, "kolvane": kolvane.id, "other": other.id}


def _listed(corpus):
    data = client.get("/api/documents", params={"project_id": PID}, headers=headers).json()
    return data, {d["id"]: d for d in data["documents"]}


class TestDocumentEntities:
    def test_list_counts_entities_by_source_document(self, corpus):
        _, docs = _listed(corpus)
        assert docs[corpus["d1"]]["entity_count"] == 2
        assert docs[corpus["d2"]]["entity_count"] == 2  # "Only In Second" + Kolvane via source_doc_ids

    def test_detail_lists_the_entities_extracted_from_it(self, corpus):
        data = client.get(f"/api/documents/{corpus['d2']}", headers=headers).json()
        names = sorted(e["name"] for e in data["entities"])
        assert names == ["Kolvane", "Only In Second"]
        assert data["entity_count"] == 2

    def test_detail_highlights_those_entities(self, corpus):
        data = client.get(f"/api/documents/{corpus['d2']}", headers=headers).json()
        assert [h["entity_name"] for h in data["highlights"]] == ["Kolvane"]

    def test_another_projects_entities_are_not_counted(self, corpus, graph_store):
        graph_store.create_entity(Person(name="Intruder", project_id="test-a6-other", source_doc_id=corpus["d1"]))
        _, docs = _listed(corpus)
        assert docs[corpus["d1"]]["entity_count"] == 2


class TestEvidenceIsBounded:
    """A-9: an empty entity name matched at every index, so a 10 MB document
    built about ten million passages in one request."""

    @pytest.fixture
    def long_doc(self, graph_store):
        doc = Document(name="Repetitive", project_id=PID, content="Kolvane shipped cable. " * 300)
        graph_store.create_entity(doc)
        return doc.id

    @pytest.mark.parametrize("name", ["", "   "])
    def test_a_blank_entity_name_is_rejected(self, long_doc, name):
        resp = client.get(f"/api/documents/{long_doc}/evidence", params={"entity_name": name}, headers=headers)
        assert resp.status_code == 422

    def test_passages_are_capped_and_the_true_total_reported(self, long_doc):
        from intel_platform.api.routes import documents as documents_route

        data = client.get(
            f"/api/documents/{long_doc}/evidence", params={"entity_name": "Kolvane"}, headers=headers,
        ).json()
        assert data["count"] == documents_route.MAX_EVIDENCE_PASSAGES
        assert len(data["passages"]) == documents_route.MAX_EVIDENCE_PASSAGES
        assert data["total"] == 300
        assert data["truncated"] is True

    def test_a_short_answer_is_not_marked_truncated(self, long_doc):
        data = client.get(
            f"/api/documents/{long_doc}/evidence", params={"entity_name": "absent name"}, headers=headers,
        ).json()
        assert data["count"] == 0
        assert data["total"] == 0
        assert data["truncated"] is False


class TestDocumentListIsHonestAboutItsSize:
    """A-19: the list stopped silently at 500 and shipped every document's full
    content over Bolt just to measure it."""

    def test_content_length_is_measured(self, corpus):
        _, docs = _listed(corpus)
        assert docs[corpus["d1"]]["content_length"] == 1234

    def test_total_and_truncated_are_reported(self, corpus):
        data, _ = _listed(corpus)
        assert data["total"] == 2
        assert data["count"] == 2
        assert data["truncated"] is False

    def test_truncation_is_reported(self, corpus, monkeypatch):
        from intel_platform.api.routes import documents as documents_route

        monkeypatch.setattr(documents_route, "DOCUMENT_LIST_LIMIT", 1)
        data, _ = _listed(corpus)
        assert data["count"] == 1
        assert data["total"] == 2
        assert data["truncated"] is True
