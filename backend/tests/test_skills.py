from intel_platform.llm.skills.loader import SkillsLoader
from intel_platform.llm.skills.registry import SkillRegistry, Skill


def test_skill_model():
    s = Skill(name="test_skill", description="A test skill", system_prompt="You are a test analyst.", temperature=0.3, max_tokens=4096)
    assert s.name == "test_skill"


def test_registry_register_and_get():
    reg = SkillRegistry()
    skill = Skill(name="test", description="Test", system_prompt="Prompt")
    reg.register(skill)
    assert reg.get("test") == skill


def test_registry_list():
    reg = SkillRegistry()
    reg.register(Skill(name="a", description="A", system_prompt="P"))
    reg.register(Skill(name="b", description="B", system_prompt="P"))
    assert len(reg.list_skills()) == 2


def test_loader_loads_builtin_templates():
    loader = SkillsLoader()
    skills = loader.list_skills()
    assert len(skills) >= 7
    assert any(s["name"] == "threat_assessment" for s in skills)


def test_loader_get_system_prompt():
    loader = SkillsLoader()
    prompt = loader.get_system_prompt("threat_assessment")
    assert prompt is not None
    assert len(prompt) > 50


def test_loader_get_system_prompt_with_foundation():
    loader = SkillsLoader()
    prompt = loader.get_system_prompt("threat_assessment", include_foundation=True)
    assert "intelligence" in prompt.lower()


def test_loader_unknown_skill():
    loader = SkillsLoader()
    prompt = loader.get_system_prompt("nonexistent")
    assert prompt is None
