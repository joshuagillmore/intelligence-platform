"""Low -> G: the foundation prompt can be asked for by name.

The loader filed ``foundation.yaml`` aside as ``_foundation_prompt`` and only
ever prepended it to another skill, so ``get_system_prompt("foundation")``
returned None. GraphRAG, which has no skill of its own to prepend it to, never
received the analytic grounding every other product gets. The graph package
now asks for it by name; this is the loader's half of that contract.
"""
from __future__ import annotations

from intel_platform.llm.skills.loader import TEMPLATES_DIR, SkillsLoader


def _foundation_text() -> str:
    import yaml

    with open(TEMPLATES_DIR / "foundation.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["system_prompt"]


def test_the_foundation_prompt_is_returned_by_name():
    prompt = SkillsLoader().get_system_prompt("foundation")
    assert prompt == _foundation_text()
    assert prompt.strip()


def test_asking_for_it_with_the_foundation_flag_does_not_double_it():
    prompt = SkillsLoader().get_system_prompt("foundation", include_foundation=True)
    assert prompt == _foundation_text()


def test_other_skills_still_prepend_it_only_when_asked():
    loader = SkillsLoader()
    plain = loader.get_system_prompt("entity_extraction")
    grounded = loader.get_system_prompt("entity_extraction", include_foundation=True)
    assert _foundation_text() not in plain
    assert grounded.startswith(_foundation_text())


def test_an_unknown_skill_is_still_none():
    assert SkillsLoader().get_system_prompt("no_such_skill") is None


def test_it_is_not_listed_as_a_selectable_skill():
    """Registering it for lookup must not make it appear as a skill the UI
    offers alongside entity_extraction and the rest."""
    names = {s["name"] for s in SkillsLoader().list_skills()}
    assert "foundation" not in names
