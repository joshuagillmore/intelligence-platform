"""Per-element gap analysis — the signal that re-tasks collection.

The PIR assessor grades the whole requirement once collection has finished, so
its verdict cannot change what gets collected: a live run ended "3 element(s)
still unanswered and collection budget remains — continue collection" and
nothing continued it. This module answers the narrower question a loop can act
on, so these tests care most about the cases where a wrong answer would send the
loop somewhere useless.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from intel_platform.services import requirement_assessor as ra


class _Provider:
    def __init__(self, reply="", error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    async def generate(self, messages, system=None, **kw):
        self.calls.append(messages[0]["content"])
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.reply, model="fake")


@pytest.fixture
def material(monkeypatch):
    """Give the assessor some collected material by default."""
    async def fake_search(query, project_id, session, limit=20, **kw):
        return [{"chunk_text": "Fordow is enriching to 60 percent.",
                 "document_id": "doc-a", "similarity": 0.8}]

    monkeypatch.setattr("intel_platform.services.vector_search.vector_search", fake_search)


class TestVerdicts:
    async def test_satisfied_verdict_is_read(self, material):
        p = _Provider('ASSESSMENT: {"satisfied": true, "confidence": "high", '
                      '"missing": "", "next_queries": []}')
        out = await ra.assess_requirement("enrichment levels?", "p1", None, p)
        assert out.satisfied is True and out.assessed is True
        assert out.verdict == "satisfied"

    async def test_gap_queries_are_returned(self, material):
        p = _Provider('ASSESSMENT: {"satisfied": false, "confidence": "medium", '
                      '"missing": "no cascade detail", '
                      '"next_queries": ["IR-6 cascade Fordow", "IAEA cascade count"]}')
        out = await ra.assess_requirement("cascade configuration?", "p1", None, p)
        assert out.satisfied is False
        assert out.next_queries == ["IR-6 cascade Fordow", "IAEA cascade count"]
        assert out.missing == "no cascade detail"

    async def test_pretty_printed_json_is_read(self, material):
        """Models pretty-print constantly. Reading only the requested one-line
        shape is the defect this codebase keeps rediscovering."""
        p = _Provider('Here is my assessment.\n\nASSESSMENT:\n{\n'
                      '  "satisfied": false,\n  "confidence": "low",\n'
                      '  "missing": "dates absent",\n  "next_queries": ["incident dates"]\n}')
        out = await ra.assess_requirement("when?", "p1", None, p)
        assert out.assessed is True
        assert out.next_queries == ["incident dates"]

    async def test_fenced_json_is_read(self, material):
        p = _Provider('```json\n{"satisfied": true, "confidence": "high", '
                      '"missing": "", "next_queries": []}\n```')
        out = await ra.assess_requirement("q?", "p1", None, p)
        assert out.satisfied is True

    async def test_queries_are_capped(self, material):
        p = _Provider('ASSESSMENT: {"satisfied": false, "next_queries": '
                      '["a", "b", "c", "d", "e"]}')
        out = await ra.assess_requirement("q?", "p1", None, p)
        assert len(out.next_queries) == ra._MAX_NEXT_QUERIES


class TestFailuresAreNotVerdicts:
    async def test_provider_outage_is_not_an_unsatisfied_verdict(self, material):
        """An outage is not evidence that the element is unanswered. Recording
        it as unsatisfied would retire elements for infrastructure reasons."""
        p = _Provider(error=RuntimeError("provider down"))
        out = await ra.assess_requirement("q?", "p1", None, p)
        assert out.assessed is False
        assert out.verdict == "unknown"
        assert out.satisfied is False
        assert out.next_queries == []

    async def test_unparseable_reply_is_not_a_verdict(self, material):
        p = _Provider("I think it's probably fine, broadly speaking.")
        out = await ra.assess_requirement("q?", "p1", None, p)
        assert out.assessed is False

    async def test_no_collected_material_is_reported_honestly(self, monkeypatch):
        """Nothing collected is a real, confident answer — and must not cost a
        model call."""
        async def nothing(*a, **kw):
            return []

        monkeypatch.setattr("intel_platform.services.vector_search.vector_search", nothing)
        p = _Provider("should not be called")
        out = await ra.assess_requirement("q?", "p1", None, p)
        assert out.satisfied is False and out.assessed is True
        assert out.confidence == "high"
        assert p.calls == [], "no material means no reason to ask the model"

    async def test_retrieval_failure_still_permits_a_graph_only_assessment(self, monkeypatch):
        async def boom(*a, **kw):
            raise RuntimeError("pgvector down")

        monkeypatch.setattr("intel_platform.services.vector_search.vector_search", boom)

        class _Store:
            def search_entities(self, project_id, limit=50, **kw):
                return [{"id": "e1", "name": "Fordow", "entity_type": "Facility"}]

            def get_relationships(self, entity_id):
                return [{"source_name": "Fordow", "rel_type": "OPERATES",
                         "target_name": "IR-6", "evidence": "cascade installed"}]

        p = _Provider('ASSESSMENT: {"satisfied": true, "confidence": "medium"}')
        out = await ra.assess_requirement("q?", "p1", None, p, store=_Store())
        assert out.assessed is True and out.satisfied is True
        assert "Fordow" in p.calls[0]


class TestPromptGrounding:
    async def test_tried_queries_are_shown_so_they_are_not_repeated(self, material):
        p = _Provider('ASSESSMENT: {"satisfied": false, "next_queries": ["x"]}')
        await ra.assess_requirement("q?", "p1", None, p, tried_queries=["old query"])
        assert "old query" in p.calls[0]

    async def test_collected_material_reaches_the_prompt(self, material):
        p = _Provider('ASSESSMENT: {"satisfied": true}')
        await ra.assess_requirement("q?", "p1", None, p)
        assert "60 percent" in p.calls[0]

    async def test_material_is_delimited_as_untrusted(self, material):
        p = _Provider('ASSESSMENT: {"satisfied": true}')
        await ra.assess_requirement("q?", "p1", None, p)
        assert "<collected>" in p.calls[0] and "</collected>" in p.calls[0]
