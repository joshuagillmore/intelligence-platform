import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from intel_platform.api.app import app
    return TestClient(app)


@pytest.fixture
def auth_header():
    from intel_platform.api.auth import create_access_token
    token = create_access_token("admin", "admin")
    return {"Authorization": f"Bearer {token}"}


def test_execute_collection_returns_202(client, auth_header):
    """POST /api/collections/{id}/execute should return 202 Accepted."""
    with patch("intel_platform.api.routes.collections.get_collection") as mock_get:
        mock_get.return_value = {
            "id": "coll-test",
            "project_id": "proj-1",
            "plan": [{"id": 1, "description": "test", "source_type": "web_search", "approved": True}],
            "status": "PENDING",
        }

        with patch("intel_platform.api.routes.collections.CollectionRunner") as MockRunner:
            mock_runner_instance = MagicMock()
            mock_runner_instance.execute = AsyncMock(return_value={
                "collection_id": "coll-test",
                "status": "SUCCESS",
                "documents_crawled": 2,
                "entities_created": 5,
                "relationships_created": 3,
                "items_processed": 1,
                "urls_found": 3,
                "errors": [],
            })
            MockRunner.return_value = mock_runner_instance

            response = client.post("/api/collections/coll-test/execute", headers=auth_header)

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "STARTED"
    assert "collection_id" in data


def test_execute_collection_rejects_already_running(client, auth_header):
    """Cannot execute a collection that is already running."""
    with patch("intel_platform.api.routes.collections.get_collection") as mock_get:
        mock_get.return_value = {
            "id": "coll-test",
            "project_id": "proj-1",
            "plan": [],
            "status": "PROGRESS",
        }

        response = client.post("/api/collections/coll-test/execute", headers=auth_header)

    assert response.status_code == 409
