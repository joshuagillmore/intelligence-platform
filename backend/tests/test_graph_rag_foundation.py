"""GraphRAG answers under the foundation prompt (review, Low → G).

`GraphRAGPipeline.query` asked the skills loader for the "foundation" skill,
but the loader keeps the foundation prompt apart from its registry, so the
lookup returned None and every GraphRAG answer ran without the tradecraft
grounding every other analytic product gets.

GraphRAG calls `loader.get_system_prompt("foundation")`; registering the
foundation prompt under that name is the llm package's half (WP-C). Until it
lands, the real-loader test below is an expected failure, not a skip.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from intel_platform.models.entities import Person
from intel_platform.services.graph_rag import GraphRAGPipeline

PROJECT = "test-rag-foundation"


class _Provider:
    def __init__(self):
        self.system = None

    async def generate(self, messages, system="", **_kwargs):
        self.system = system
        return SimpleNamespace(content="An answer.", model="fake-model", total_tokens=1)


async def _ask(graph_store) -> str:
    graph_store.create_entity(Person(name="Foundation Target", project_id=PROJECT))
    provider = _Provider()
    with patch("intel_platform.llm.providers._get_provider", new=AsyncMock(return_value=provider)):
        result = await GraphRAGPipeline(graph_store).query("Tell me about Foundation Target", PROJECT)
    assert result["answer"] == "An answer."
    return provider.system


async def test_the_foundation_prompt_leads_the_system_prompt(graph_store):
    class _Loader:
        def get_system_prompt(self, skill_name, include_foundation=False):
            return "FOUNDATION-TEXT" if skill_name == "foundation" else None

    with patch("intel_platform.llm.skills.loader.SkillsLoader", new=_Loader):
        system = await _ask(graph_store)
    assert system.startswith("FOUNDATION-TEXT")
    assert "knowledge graph" in system


async def test_the_real_foundation_prompt_reaches_the_model(graph_store):
    from intel_platform.llm.skills.loader import SkillsLoader

    foundation = SkillsLoader().get_system_prompt("foundation")
    if foundation is None:
        pytest.xfail("the skills loader does not register 'foundation' yet (WP-C)")
    system = await _ask(graph_store)
    assert foundation in system
