"""Tests for enhanced topic tree features: cross-references, relevant excerpts, caching."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from intel_platform.services.topics import TopicTreeService, _cluster_doc_map, _cluster_keywords


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_store():
    """Create a mock GraphStore with common defaults."""
    store = MagicMock()
    store.search_entities.return_value = []
    store.get_full_graph.return_value = {"nodes": [], "edges": []}
    store.get_entity.return_value = None
    store.get_relationships.return_value = []
    return store


def _populate_cluster_cache(project_id: str):
    """Manually populate the module-level cluster caches for testing."""
    import intel_platform.services.topics as topics_module

    topics_module._cluster_doc_map[project_id] = {
        "topic-0": ["doc1", "doc2"],
        "topic-1": ["doc2", "doc3"],
        "topic-2": ["doc4"],
    }
    topics_module._cluster_keywords[project_id] = {
        "topic-0": ["iran", "nuclear", "sanctions"],
        "topic-1": ["russia", "ukraine", "military"],
        "topic-2": ["cyber", "apt", "malware"],
    }


# ---------------------------------------------------------------------------
# Cross-reference detection
# ---------------------------------------------------------------------------

def test_cross_reference_detection():
    """Documents appearing in multiple clusters should be detected."""
    store = _make_mock_store()
    svc = TopicTreeService(store)

    _populate_cluster_cache("test-cross-ref")

    documents = [
        {"id": "doc1", "name": "Iran Report"},
        {"id": "doc2", "name": "Shared Report"},  # In both topic-0 and topic-1
        {"id": "doc3", "name": "Russia Report"},
        {"id": "doc4", "name": "Cyber Report"},
    ]

    cross_refs = svc._detect_cross_references("test-cross-ref", documents)

    # doc2 appears in both topic-0 and topic-1
    assert len(cross_refs) == 1
    assert cross_refs[0]["doc_id"] == "doc2"
    assert cross_refs[0]["doc_name"] == "Shared Report"
    assert set(cross_refs[0]["topic_ids"]) == {"topic-0", "topic-1"}


def test_cross_reference_no_shared_docs():
    """When no documents are shared, cross_references should be empty."""
    store = _make_mock_store()
    svc = TopicTreeService(store)

    import intel_platform.services.topics as topics_module
    topics_module._cluster_doc_map["test-no-cross"] = {
        "topic-0": ["doc1"],
        "topic-1": ["doc2"],
    }

    documents = [
        {"id": "doc1", "name": "Report A"},
        {"id": "doc2", "name": "Report B"},
    ]

    cross_refs = svc._detect_cross_references("test-no-cross", documents)
    assert cross_refs == []


def test_cross_reference_empty_cache():
    """With empty cache, no cross-references should be returned."""
    store = _make_mock_store()
    svc = TopicTreeService(store)

    cross_refs = svc._detect_cross_references("nonexistent-project", [])
    assert cross_refs == []


# ---------------------------------------------------------------------------
# Topic context with relevant excerpts
# ---------------------------------------------------------------------------

def test_get_topic_context_with_excerpts():
    """Topic context should include relevant_excerpts and keyword_matches."""
    store = _make_mock_store()
    svc = TopicTreeService(store)

    _populate_cluster_cache("test-excerpts")

    # Mock get_entity to return documents with content
    def mock_get_entity(entity_id):
        if entity_id == "doc1":
            return {
                "id": "doc1",
                "name": "Iran Nuclear Report",
                "entity_type": "Document",
                "content": "Iran is developing nuclear capabilities. The sanctions against Iran are extensive. Nuclear proliferation is a concern.",
                "reliability_rating": "B2",
            }
        if entity_id == "doc2":
            return {
                "id": "doc2",
                "name": "Sanctions Overview",
                "entity_type": "Document",
                "content": "International sanctions framework overview document with no matching keywords here.",
                "reliability_rating": "C3",
            }
        return None

    store.get_entity.side_effect = mock_get_entity
    store.get_relationships.return_value = []

    context = svc.get_topic_context("topic-0", "test-excerpts")

    assert context["document_count"] == 2
    docs = context["documents"]

    # doc1 should have higher relevance (more keyword matches)
    doc1 = next(d for d in docs if d["id"] == "doc1")
    assert "relevant_excerpts" in doc1
    assert "keyword_matches" in doc1
    assert doc1["keyword_matches"].get("iran", 0) >= 1
    assert doc1["relevance_score"] > 0

    # Documents should be sorted by relevance (doc1 first since it matches more keywords)
    assert docs[0]["id"] == "doc1"


def test_get_topic_context_no_keywords():
    """Without keywords, excerpts should be empty but context should still work."""
    store = _make_mock_store()
    svc = TopicTreeService(store)

    import intel_platform.services.topics as topics_module
    topics_module._cluster_doc_map["test-no-kw"] = {
        "topic-x": ["doc1"],
    }
    topics_module._cluster_keywords["test-no-kw"] = {
        "topic-x": [],
    }

    store.get_entity.return_value = {
        "id": "doc1",
        "name": "Some Report",
        "entity_type": "Document",
        "content": "Some content here.",
    }
    store.get_relationships.return_value = []

    context = svc.get_topic_context("topic-x", "test-no-kw")
    assert context["document_count"] == 1
    doc = context["documents"][0]
    assert doc["relevant_excerpts"] == []
    assert doc["keyword_matches"] == {}


# ---------------------------------------------------------------------------
# Topic context for non-topic entities
# ---------------------------------------------------------------------------

def test_get_topic_context_regular_entity():
    """Regular (non-topic) entities should still work."""
    store = _make_mock_store()
    svc = TopicTreeService(store)

    store.get_entity.return_value = {
        "id": "entity-123",
        "name": "APT29",
        "entity_type": "ThreatActor",
    }
    store.get_relationships.return_value = []

    context = svc.get_topic_context("entity-123", "test-proj")
    assert context["entity"]["name"] == "APT29"
    assert context["document_count"] == 0


def test_get_topic_context_entity_not_found():
    """Non-existent entities should return error."""
    store = _make_mock_store()
    svc = TopicTreeService(store)

    store.get_entity.return_value = None

    context = svc.get_topic_context("nonexistent", "test-proj")
    assert "error" in context


# ---------------------------------------------------------------------------
# Skills templates loaded
# ---------------------------------------------------------------------------

def test_topic_naming_skill_loaded():
    """The topic_naming skill template should be loadable."""
    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    skill = loader.get_skill("topic_naming")
    assert skill is not None
    assert skill.name == "topic_naming"
    assert "topic name" in skill.system_prompt.lower()


def test_topic_summarization_skill_loaded():
    """The topic_summarization skill template should be loadable."""
    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    skill = loader.get_skill("topic_summarization")
    assert skill is not None
    assert skill.name == "topic_summarization"
    assert "TOPIC-level" in skill.system_prompt
    assert "DOCUMENT-level" in skill.system_prompt
    assert "CORPUS-level" in skill.system_prompt
