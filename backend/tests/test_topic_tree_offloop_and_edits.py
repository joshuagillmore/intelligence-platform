"""The topic tree: built off the event loop, and the analyst's edits applied to it.

Contract 15: `build_topic_tree` read 10,000 entities and the full graph through
the synchronous driver and ran tf-idf clustering and Louvain on the event loop,
so a cold `/topics` stalled every other request for its whole ~20 s.

Low -> R: the rename / add / delete endpoints wrote `TopicEdit` rows that
nothing read — the tree came back exactly as the algorithm built it.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from intel_platform.services import topics as topics_svc
from intel_platform.services.topics import TopicTreeService, apply_topic_edits
from tests.ids import tp


class _Store:
    def __init__(self, loop_thread):
        self.loop_thread = loop_thread
        self.on_loop: list[str] = []

    def _note(self, name):
        if threading.current_thread() is self.loop_thread:
            self.on_loop.append(name)

    def search_entities(self, project_id, entity_type=None, limit=50, **kw):
        self._note("search_entities")
        if entity_type == "Document":
            return [{"id": "d1", "name": "doc", "entity_type": "Document", "content": "apt29 phishing"}]
        return [
            {"id": f"e{i}", "name": f"Actor {i}", "entity_type": "Organization"} for i in range(4)
        ] + [{"id": "d1", "name": "doc", "entity_type": "Document"}]

    def get_full_graph(self, project_id, limit=500):
        self._note("get_full_graph")
        return {"nodes": [], "edges": [
            {"source_id": "e0", "target_id": "e1"}, {"source_id": "e1", "target_id": "e2"},
            {"source_id": "e2", "target_id": "e3"},
        ]}


async def test_store_reads_and_clustering_run_off_the_loop(monkeypatch):
    loop_thread = threading.current_thread()
    store = _Store(loop_thread)
    on_loop = store.on_loop

    def _cluster(doc_pairs, project_id):
        if threading.current_thread() is loop_thread:
            on_loop.append("cluster_documents")
        return None, {}, {}

    original_theme = TopicTreeService._build_theme_branch

    def _theme(self, *a, **k):
        if threading.current_thread() is loop_thread:
            on_loop.append("community_detection")
        return original_theme(self, *a, **k)

    monkeypatch.setattr(topics_svc, "cluster_documents", _cluster)
    monkeypatch.setattr(TopicTreeService, "_build_theme_branch", _theme)

    tree = await TopicTreeService(store).build_topic_tree("p1")
    assert tree["entity_count"] == 4
    assert on_loop == [], f"ran on the event loop: {on_loop}"


# ---------------------------------------------------------------------------
# The edit overlay
# ---------------------------------------------------------------------------

def _tree():
    return {
        "id": "root", "name": "Knowledge Base", "children": [
            {"id": "branch-themes", "name": "Topics", "children": [
                {"id": "topic-0", "name": "apt29, phishing", "children": [], "count": 3},
                {"id": "topic-1", "name": "cable, baltic", "children": [
                    {"id": "topic-1-0", "name": "anchor, vessel", "children": [], "count": 2},
                ], "count": 5},
            ]},
        ],
    }


def _edit(node_id, edit_type, name="", description="", parent_id=""):
    return SimpleNamespace(node_id=node_id, edit_type=edit_type, name=name,
                           description=description, parent_id=parent_id)


def _find(node, node_id):
    if node.get("id") == node_id:
        return node
    for child in node.get("children", []):
        hit = _find(child, node_id)
        if hit:
            return hit
    return None


class TestOverlay:
    def test_a_rename_is_applied(self):
        out = apply_topic_edits(_tree(), [_edit("topic-0", "rename", name="APT29 phishing campaign")])
        assert _find(out, "topic-0")["name"] == "APT29 phishing campaign"
        assert _find(out, "topic-0")["edited"] is True
        assert out["edits_applied"] == 1

    def test_a_description_alone_keeps_the_name(self):
        out = apply_topic_edits(_tree(), [_edit("topic-0", "rename", description="Spring 2025 wave")])
        node = _find(out, "topic-0")
        assert node["name"] == "apt29, phishing" and node["description"] == "Spring 2025 wave"

    def test_a_delete_removes_the_subtree(self):
        out = apply_topic_edits(_tree(), [_edit("topic-1", "delete")])
        assert _find(out, "topic-1") is None and _find(out, "topic-1-0") is None

    def test_an_added_child_appears_under_its_parent(self):
        out = apply_topic_edits(_tree(), [_edit("topic-user-ab12", "add", name="Insider angle", parent_id="topic-1")])
        added = _find(_find(out, "topic-1"), "topic-user-ab12")
        assert added["name"] == "Insider angle" and added["user_created"] is True

    def test_a_move_reparents(self):
        out = apply_topic_edits(_tree(), [_edit("topic-1-0", "rename", parent_id="topic-0")])
        assert _find(_find(out, "topic-0"), "topic-1-0") is not None
        assert _find(_find(out, "topic-1"), "topic-1-0") is None

    def test_a_node_cannot_move_under_its_own_descendant(self):
        out = apply_topic_edits(_tree(), [_edit("topic-1", "rename", parent_id="topic-1-0")])
        assert _find(_find(out, "branch-themes"), "topic-1") is not None
        assert out["edits_unmatched"] == 1

    def test_an_edit_for_a_node_the_rebuild_no_longer_has_is_counted(self):
        """Algorithmic ids are not stable across rebuilds; a lost edit must be
        visible, not silently dropped."""
        out = apply_topic_edits(_tree(), [_edit("topic-9", "rename", name="gone")])
        assert out["edits_applied"] == 0 and out["edits_unmatched"] == 1

    def test_an_add_whose_parent_is_gone_is_kept_at_the_root(self):
        out = apply_topic_edits(_tree(), [_edit("topic-user-cd34", "add", name="Keep me", parent_id="topic-9")])
        assert _find(out, "topic-user-cd34")["name"] == "Keep me"

    def test_the_input_tree_is_not_mutated(self):
        """The algorithmic tree is cached and shared between requests."""
        tree = _tree()
        apply_topic_edits(tree, [_edit("topic-0", "rename", name="x"), _edit("topic-1", "delete")])
        assert tree == _tree()


class TestRoute:
    """Edits reach `/topics` on the next request, cached tree or not."""

    @pytest.fixture
    def client(self, monkeypatch):
        from fastapi.testclient import TestClient

        from intel_platform.api.app import app
        from intel_platform.api.cache import clear_cache
        from intel_platform.api.deps import get_graph_store
        from intel_platform.db.engine import get_db

        builds = {"n": 0}

        async def _build(self, project_id, method="tfidf", granularity="medium"):
            builds["n"] += 1
            return _tree()

        monkeypatch.setattr(TopicTreeService, "build_topic_tree", _build)
        state = {"edits": [], "fail": False}

        class _Session:
            async def execute(self, _stmt):
                if state["fail"]:
                    raise ConnectionRefusedError("postgres down")
                rows = list(state["edits"])
                return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

        async def _db():
            yield _Session()

        clear_cache()
        app.dependency_overrides[get_graph_store] = lambda: object()
        app.dependency_overrides[get_db] = _db
        yield TestClient(app), state, builds
        app.dependency_overrides.pop(get_graph_store, None)
        app.dependency_overrides.pop(get_db, None)
        clear_cache()

    def _get(self, client):
        from intel_platform.config import settings

        return client.get("/api/topics", params={"project_id": tp("edits")},
                          headers={"Authorization": f"Bearer {settings.api_key}"}).json()

    def test_an_edit_is_visible_on_the_next_request_despite_the_cache(self, client):
        http, state, builds = client
        assert _find(self._get(http), "topic-0")["name"] == "apt29, phishing"
        state["edits"] = [_edit("topic-0", "rename", name="Renamed")]
        body = self._get(http)
        assert _find(body, "topic-0")["name"] == "Renamed"
        assert builds["n"] == 1, "the algorithmic tree is still served from the cache"
        assert body["edits_overlay"] == "applied"

    def test_an_unreadable_edit_store_is_said_not_hidden(self, client):
        http, state, _builds = client
        state["fail"] = True
        body = self._get(http)
        assert body["edits_overlay"] == "unavailable"
        assert _find(body, "topic-0") is not None
