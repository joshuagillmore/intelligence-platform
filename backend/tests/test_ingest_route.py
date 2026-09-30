import asyncio

import pytest
from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.api.routes import ingest as ingest_route
from intel_platform.config import get_settings, settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


def test_ingest_text():
    proj = client.post(
        "/api/projects",
        json={"name": "Ingest Test Project"},
        headers=headers,
    ).json()

    response = client.post(
        "/api/ingest",
        data={
            "project_id": proj["id"],
            "content": "John Smith from Microsoft met with officials in Washington.",
            "reliability_rating": "B2",
        },
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"]
    assert data["chunks"] >= 1
    client.delete(f"/api/projects/{proj['id']}", headers=headers)


# ---------------------------------------------------------------------------
# A-10: a batch is validated before anything is written; the manual path is
# bounded like collection; blocking work runs off the event loop.
# ---------------------------------------------------------------------------

PID = "test-a10-ingest"


def _documents(graph_store) -> list[dict]:
    with graph_store._driver.session() as session:
        return [dict(r["d"]) for r in session.run("MATCH (d:Document {project_id: $p}) RETURN d", p=PID)]


def _file(name: str, body: bytes = b"Marek Ilyas met Kolvane in Riga."):
    return ("files", (name, body, "text/plain"))


class TestBatchIsAllOrNothing:
    def test_a_bad_extension_on_the_third_file_writes_nothing(self, graph_store):
        """Files 1-2 were stored before file 3 was rejected, so a retry duplicated them."""
        resp = client.post(
            "/api/ingest/batch",
            data={"project_id": PID},
            files=[_file("one.txt"), _file("two.txt"), _file("three.exe")],
            headers=headers,
        )
        assert resp.status_code == 400
        assert _documents(graph_store) == []

    def test_an_oversized_third_file_writes_nothing(self, graph_store, monkeypatch):
        monkeypatch.setattr(ingest_route, "MAX_FILE_SIZE", 64)
        resp = client.post(
            "/api/ingest/batch",
            data={"project_id": PID},
            files=[_file("one.txt"), _file("two.txt"), _file("three.txt", b"x" * 65)],
            headers=headers,
        )
        assert resp.status_code == 400
        assert _documents(graph_store) == []

    def test_a_file_exactly_at_the_limit_is_accepted(self, graph_store, monkeypatch):
        monkeypatch.setattr(ingest_route, "MAX_FILE_SIZE", 64)
        resp = client.post(
            "/api/ingest/batch",
            data={"project_id": PID},
            files=[_file("one.txt", b"Riga " * 12 + b"Riga")],  # 64 bytes
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(_documents(graph_store)) == 1


class TestManualIngestIsBounded:
    def test_content_beyond_max_document_chars_is_not_stored(self, graph_store, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_document_chars", 300)
        text = "Marek Ilyas met officials of Kolvane Holdings in Riga. " * 40  # ~2200 chars
        resp = client.post("/api/ingest", data={"project_id": PID, "content": text}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["content_truncated"] is True
        (doc,) = _documents(graph_store)
        assert len(doc["content"]) <= 300

    def test_content_within_the_bound_is_kept_whole(self, graph_store):
        text = "Marek Ilyas met officials of Kolvane Holdings in Riga."
        resp = client.post("/api/ingest", data={"project_id": PID, "content": text}, headers=headers)
        assert resp.json()["content_truncated"] is False
        (doc,) = _documents(graph_store)
        assert doc["content"] == text


class TestBlockingWorkLeavesTheEventLoop:
    """Contract 15: parsing, spaCy and the sync Neo4j driver stalled /health and
    every other request while one document was ingested."""

    @pytest.fixture
    def on_loop(self, monkeypatch):
        seen: dict[str, bool] = {}

        def probe(name, real):
            def wrapper(*args, **kwargs):
                try:
                    asyncio.get_running_loop()
                    seen[name] = True
                except RuntimeError:
                    seen[name] = False
                return real(*args, **kwargs)
            return wrapper

        for name in ("process_file", "extract_entities_nlp", "build_graph_from_extractions"):
            monkeypatch.setattr(ingest_route, name, probe(name, getattr(ingest_route, name)))
        from intel_platform.graph.store import GraphStore
        monkeypatch.setattr(GraphStore, "create_entity", probe("create_entity", GraphStore.create_entity))
        return seen

    def test_single_ingest(self, graph_store, on_loop):
        resp = client.post(
            "/api/ingest", data={"project_id": PID, "extraction_mode": "nlp"},
            files={"file": ("note.txt", b"Marek Ilyas met Kolvane in Riga.", "text/plain")},
            headers=headers,
        )
        assert resp.status_code == 200
        assert on_loop == {
            "process_file": False, "create_entity": False,
            "extract_entities_nlp": False, "build_graph_from_extractions": False,
        }

    def test_batch_ingest(self, graph_store, on_loop):
        resp = client.post(
            "/api/ingest/batch", data={"project_id": PID, "extraction_mode": "nlp"},
            files=[_file("one.txt")], headers=headers,
        )
        assert resp.status_code == 200
        assert not any(on_loop.values()), on_loop
