"""A project that does not exist must be distinguishable from an empty one.

Every project-scoped read returns a well-formed empty result for an id that was
never created — {"events": [], "count": 0}, {"nodes": 0, "edges": 0} — which is
exactly what a real but empty project returns. A stale deep link or a deleted
project therefore reads to the analyst as "the collection produced nothing".

Reported as a flag rather than a 404: the 200-empty contract is deliberate (a
route test asserts it against project_id="nonexistent"), so callers keep working
and gain the ability to tell the two cases apart.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from intel_platform.api.deps import project_exists


def _store(project=None, entities=None):
    store = MagicMock()
    store.get_project.return_value = project
    store.search_entities.return_value = entities or []
    return store


class TestProjectExists:
    def test_true_when_a_project_node_exists(self):
        assert project_exists(_store(project={"id": "p1", "name": "Real"}), "p1") is True

    def test_true_for_an_id_holding_data_without_a_project_node(self):
        """/api/ingest creates entities under any project_id; such ids exist today."""
        assert project_exists(_store(entities=[{"id": "e1"}]), "ingest-first") is True

    def test_false_when_nothing_exists_under_the_id(self):
        assert project_exists(_store(), "never-existed") is False

    def test_an_existing_but_empty_project_is_still_true(self):
        """The whole point: empty is a different answer from unknown."""
        store = _store(project={"id": "p-empty", "name": "Empty"}, entities=[])
        assert project_exists(store, "p-empty") is True

    def test_does_not_scan_for_entities_when_the_project_node_is_found(self):
        store = _store(project={"id": "p1"})
        project_exists(store, "p1")
        store.search_entities.assert_not_called()
