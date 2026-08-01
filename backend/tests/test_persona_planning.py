"""The active persona shapes how a requirement is decomposed.

Personas existed but reached nothing that mattered: `persona` appeared nowhere
in the planner or the PIR routes, so a cyber analyst and a maritime analyst
broke an identical question into identical elements. Which elements a
requirement is split into decides what gets collected, so the persona has to
reach the decomposition prompt, not just the UI.
"""
from __future__ import annotations

import pytest

from intel_platform.api.routes import personas


@pytest.fixture
def restore_active():
    original = personas._active_persona
    yield
    personas._active_persona = original


class TestPersonaBrief:
    def test_brief_names_the_persona(self, restore_active):
        personas._active_persona = "cyber_analyst"
        brief = personas.active_persona_brief()
        assert "Cyber Threat Analyst" in brief

    def test_brief_carries_the_expertise(self, restore_active):
        personas._active_persona = "cyber_analyst"
        brief = personas.active_persona_brief()
        assert "CTI analysis" in brief
        assert "threat assessment" in brief, "skills should be readable, not snake_case"

    def test_different_personas_produce_different_framing(self, restore_active):
        personas._active_persona = "cyber_analyst"
        cyber = personas.active_persona_brief()
        personas._active_persona = "osint_collector"
        osint = personas.active_persona_brief()
        assert cyber != osint
        assert "OSINT Collector" in osint and "OSINT Collector" not in cyber

    def test_brief_instructs_decomposition_not_just_tone(self, restore_active):
        """A persona that only changed the prose would be decoration."""
        assert "Decompose" in personas.active_persona_brief()

    def test_unknown_active_persona_yields_no_framing(self, restore_active):
        """An empty brief must leave the caller's prompt untouched rather than
        injecting a half-formed sentence."""
        personas._active_persona = "does_not_exist"
        assert personas.active_persona_brief() == ""

    def test_temperature_comes_from_the_persona(self, restore_active):
        personas._active_persona = "osint_collector"
        assert personas.active_persona_temperature() == 0.4
        personas._active_persona = "cyber_analyst"
        assert personas.active_persona_temperature() == 0.3

    def test_temperature_falls_back_when_unset(self, restore_active):
        personas._active_persona = "does_not_exist"
        assert personas.active_persona_temperature(0.7) == 0.7

    def test_temperature_falls_back_on_a_bad_value(self, restore_active):
        personas._personas["broken"] = {"id": "broken", "name": "B", "temperature": "hot"}
        personas._active_persona = "broken"
        try:
            assert personas.active_persona_temperature(0.25) == 0.25
        finally:
            personas._personas.pop("broken", None)


class TestPersonaReachesTheRefinement:
    """The wiring under test: the brief must reach the prompt that produces the
    EEIs, and the EEI instructions must survive it."""

    def test_active_persona_is_in_the_refinement_prompt(self, restore_active):
        from intel_platform.api.routes.collection_plans import refinement_system_prompt

        personas._active_persona = "cyber_analyst"
        prompt = refinement_system_prompt()
        assert "Cyber Threat Analyst" in prompt
        assert "CTI analysis" in prompt

    def test_switching_persona_changes_the_refinement_prompt(self, restore_active):
        from intel_platform.api.routes.collection_plans import refinement_system_prompt

        personas._active_persona = "cyber_analyst"
        cyber = refinement_system_prompt()
        personas._active_persona = "osint_collector"
        osint = refinement_system_prompt()
        assert cyber != osint

    def test_the_eei_instructions_are_preserved(self, restore_active):
        """The persona frames the decomposition; it must not displace the rules
        that stop overlapping elements being generated."""
        from intel_platform.api.routes.collection_plans import refinement_system_prompt

        personas._active_persona = "cyber_analyst"
        prompt = refinement_system_prompt()
        assert "Essential Elements of Information" in prompt
        assert "must not overlap" in prompt
        assert "Return the refined PIR on the first line" in prompt

    def test_no_persona_leaves_the_prompt_intact(self, restore_active):
        from intel_platform.api.routes.collection_plans import refinement_system_prompt

        personas._active_persona = "does_not_exist"
        prompt = refinement_system_prompt()
        assert prompt.startswith("You are an intelligence analyst.")
        assert "Essential Elements of Information" in prompt
