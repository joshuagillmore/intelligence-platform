"""Low -> G / contract 18: reading a topic name back, and counting honestly.

A reply with no ``topic_name`` still counted as refined, so a tree whose
labels were all keywords could report ``label_source: "llm"``. And the reply
was read with a fence-split + json.loads, so a name introduced by a sentence
or a bold label was a failure.
"""
from __future__ import annotations

import pytest

from intel_platform.services import document_clustering as dc


class _Reply:
    def __init__(self, content: str):
        self._content = content

    def name(self) -> str:
        return "fake"

    async def generate(self, **_kw):
        from types import SimpleNamespace
        return SimpleNamespace(content=self._content)


@pytest.fixture
def provider(monkeypatch):
    def _install(content: str):
        async def _resolve():
            return _Reply(content)

        monkeypatch.setattr("intel_platform.llm.providers._get_topics_provider", _resolve)

        class _Loader:
            def get_system_prompt(self, *_a, **_kw):
                return "name the topic"

        monkeypatch.setattr("intel_platform.llm.skills.loader.SkillsLoader", _Loader)
    return _install


def _node() -> dict:
    return {"id": "topic-root", "name": "cable / baltic / vessel", "entity_type": "topic",
            "keywords": ["cable"], "doc_ids": ["d1"], "children": []}


NAMED = '{"topic_name": "Baltic Cable Sabotage", "summary": "Damage to subsea cables."}'


@pytest.mark.parametrize("reply", [
    NAMED,
    "Here is a name for this cluster:\n\n" + NAMED,
    "```json\n" + NAMED + "\n```\nHope this helps.",
    "**Result:** " + NAMED,
    "1. Read the excerpts.\n2. Named the topic:\n" + NAMED,
])
async def test_the_name_is_read_whatever_surrounds_it(provider, reply):
    provider(reply)
    tree = await dc.refine_labels_with_llm(_node(), [("d1", "text")])
    assert tree["name"] == "Baltic Cable Sabotage"
    assert tree["summary"] == "Damage to subsea cables."
    assert tree["label_source"] == "llm"


@pytest.mark.parametrize("reply", [
    '{"summary": "A summary but no name."}',
    '{"topic_name": "   ", "summary": "blank name"}',
    '{"topic_name": 42}',
    '{"topic_name": ["Baltic", "Cable"]}',
    "| Topic | Baltic Cable |\n|---|---|",
    "I could not determine a topic.",
])
async def test_a_reply_without_a_usable_name_is_not_counted_as_refined(provider, reply):
    provider(reply)
    tree = await dc.refine_labels_with_llm(_node(), [("d1", "text")])
    assert tree["name"] == "cable / baltic / vessel"
    assert tree["label_source"] == "keywords"
    assert tree["labels_refined"] == 0
    assert tree["labels_failed"] == 1


async def test_a_non_string_summary_is_ignored_not_fatal(provider):
    provider('{"topic_name": "Baltic Cable Sabotage", "summary": {"text": "x"}}')
    tree = await dc.refine_labels_with_llm(_node(), [("d1", "text")])
    assert tree["name"] == "Baltic Cable Sabotage"
    assert "summary" not in tree
    assert tree["label_source"] == "llm"
