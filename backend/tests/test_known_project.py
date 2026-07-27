"""A project that does not exist must not look like a project that is empty.

Every project-scoped read returned a well-formed empty result for an id that
was never created — {"events": [], "count": 0}, {"nodes": 0, "edges": 0} — which
is exactly what a real but empty project returns. A stale deep link or a deleted
project therefore reads to the analyst as "the collection produced nothing".
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from intel_platform.api.deps import known_project


class TestKnownProject:
    def test_returns_the_id_when_the_project_exists(self):
        store = MagicMock()
        store.get_project.return_value = {"id": "proj-1", "name": "Real"}
        assert known_project("proj-1", store) == "proj-1"

    def test_accepts_an_id_that_holds_data_without_a_project_node(self):
        """/api/ingest creates entities under any project_id; that flow is real."""
        store = MagicMock()
        store.get_project.return_value = None
        store.search_entities.return_value = [{"id": "e1"}]
        assert known_project("ingest-first", store) == "ingest-first"

    def test_404s_when_the_project_does_not_exist(self):
        store = MagicMock()
        store.get_project.return_value = None
        store.search_entities.return_value = []
        with pytest.raises(HTTPException) as exc:
            known_project("typo-project", store)
        assert exc.value.status_code == 404
        # Name the id back, so a typo is obvious from the message alone.
        assert "typo-project" in exc.value.detail

    def test_empty_project_still_resolves(self):
        """An existing project with nothing in it is a valid, different answer."""
        store = MagicMock()
        store.get_project.return_value = {"id": "proj-empty", "name": "Empty"}
        assert known_project("proj-empty", store) == "proj-empty"
