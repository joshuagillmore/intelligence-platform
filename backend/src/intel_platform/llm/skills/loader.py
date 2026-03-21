from __future__ import annotations
from pathlib import Path
import yaml
from intel_platform.llm.skills.registry import Skill, SkillRegistry

TEMPLATES_DIR = Path(__file__).parent / "templates"


class SkillsLoader:
    def __init__(self, extra_dirs: list[str] | None = None):
        self._registry = SkillRegistry()
        self._foundation_prompt = ""
        self._load_builtin_templates()
        if extra_dirs:
            for d in extra_dirs:
                self._load_directory(d)

    def _load_builtin_templates(self) -> None:
        self._load_directory(str(TEMPLATES_DIR))

    def _load_directory(self, directory: str) -> None:
        dir_path = Path(directory)
        if not dir_path.exists():
            return
        for file in dir_path.glob("*.yaml"):
            try:
                with open(file) as f:
                    data = yaml.safe_load(f)
                if not data or "name" not in data:
                    continue
                skill = Skill(**data)
                if skill.name == "foundation":
                    self._foundation_prompt = skill.system_prompt
                else:
                    self._registry.register(skill)
            except Exception:
                continue

    def get_system_prompt(self, skill_name: str, include_foundation: bool = False) -> str | None:
        skill = self._registry.get(skill_name)
        if not skill:
            return None
        if include_foundation and self._foundation_prompt:
            return f"{self._foundation_prompt}\n\n---\n\n{skill.system_prompt}"
        return skill.system_prompt

    def get_skill(self, skill_name: str) -> Skill | None:
        return self._registry.get(skill_name)

    def list_skills(self) -> list[dict]:
        return [{"name": s.name, "description": s.description, "active": s.active} for s in self._registry.list_skills()]

    def register_custom_skill(self, skill: Skill) -> None:
        self._registry.register(skill)
