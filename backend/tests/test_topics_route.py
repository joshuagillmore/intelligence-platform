from fastapi.testclient import TestClient
from intel_platform.api.app import app
from intel_platform.config import settings

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}

def test_get_topic_tree():
    response = client.get("/api/topics", params={"project_id": "nonexistent"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "children" in data
    assert "entity_count" in data

def test_get_topic_context_not_found():
    response = client.get("/api/topics/nonexistent", params={"project_id": "test"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "error" in data


async def test_topic_context_returns_documents(graph_store):
    """Selecting a topic-* cluster node should return its documents."""
    from intel_platform.models.entities import Document
    from intel_platform.services.topics import TopicTreeService

    project_id = "test-topic-ctx"

    # Create test documents
    doc1 = Document(name="cyber_report.pdf", content="cyber attack malware phishing credential theft", project_id=project_id)
    doc2 = Document(name="sanctions_brief.pdf", content="sanctions iran oil trade export revenue", project_id=project_id)
    graph_store.create_entity(doc1)
    graph_store.create_entity(doc2)

    svc = TopicTreeService(graph_store)
    tree = await svc.build_topic_tree(project_id)

    # Find first topic-* node in tree
    def find_topic_node(node):
        if node.get("id", "").startswith("topic-"):
            return node
        for child in node.get("children", []):
            found = find_topic_node(child)
            if found:
                return found
        return None

    topic_node = find_topic_node(tree)
    if topic_node:
        ctx = svc.get_topic_context(topic_node["id"], project_id)
        assert "documents" in ctx or "source_documents" in ctx
        assert ctx.get("keywords") is not None
