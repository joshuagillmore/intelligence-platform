from __future__ import annotations
from pydantic import BaseModel


class Skill(BaseModel):
    name: str
    description: str
    system_prompt: str
    temperature: float = 0.3
    max_tokens: int = 4096
    active: bool = True


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Skill] = {}
    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill
    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)
    def list_skills(self) -> list[Skill]:
        return list(self._skills.values())
    def remove(self, name: str) -> None:
        self._skills.pop(name, None)
