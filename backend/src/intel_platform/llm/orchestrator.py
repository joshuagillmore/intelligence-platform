from __future__ import annotations
from intel_platform.llm.base import LLMProvider, LLMResponse


class LLMOrchestrator:
    def __init__(self, default_provider: LLMProvider, token_budget: int = 0):
        self._default = default_provider
        self._providers: dict[str, LLMProvider] = {default_provider.name(): default_provider}
        self._token_budget = token_budget
        self._total_tokens = 0
        self._skills_loader = None

    @property
    def providers(self) -> dict[str, LLMProvider]:
        return self._providers

    @property
    def total_tokens_used(self) -> int:
        return self._total_tokens

    def register_provider(self, name: str, provider: LLMProvider) -> None:
        self._providers[name] = provider

    def set_skills_loader(self, loader) -> None:
        self._skills_loader = loader

    async def generate(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096, provider_name: str | None = None, skill_name: str | None = None) -> LLMResponse:
        provider = self._providers.get(provider_name, self._default) if provider_name else self._default
        if skill_name and self._skills_loader:
            skill_system = self._skills_loader.get_system_prompt(skill_name)
            if skill_system:
                system = f"{skill_system}\n\n{system}" if system else skill_system
        result = await provider.generate(messages=messages, system=system, temperature=temperature, max_tokens=max_tokens)
        self._total_tokens += result.total_tokens
        return result

    async def stream(self, messages: list[dict], system: str = "", temperature: float = 0.3, max_tokens: int = 4096, provider_name: str | None = None, skill_name: str | None = None):
        provider = self._providers.get(provider_name, self._default) if provider_name else self._default
        if skill_name and self._skills_loader:
            skill_system = self._skills_loader.get_system_prompt(skill_name)
            if skill_system:
                system = f"{skill_system}\n\n{system}" if system else skill_system
        async for chunk in provider.stream(messages=messages, system=system, temperature=temperature, max_tokens=max_tokens):
            yield chunk
