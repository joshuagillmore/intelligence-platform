import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from intel_platform.api.deps import verify_api_key
from intel_platform.config import settings

router = APIRouter(dependencies=[Depends(verify_api_key)])


class LLMQueryRequest(BaseModel):
    messages: list[dict]
    system: str = ""
    skill_name: str | None = None
    temperature: float = 0.3
    max_tokens: int = 4096
    provider: str | None = None
    stream: bool = False


class SkillListResponse(BaseModel):
    skills: list[dict]


async def _resolve_api_key(provider_name: str) -> str | None:
    """Resolve an API key for a provider: check DB first, then env vars."""
    from intel_platform.api.routes.admin_config import get_active_api_key
    db_key = await get_active_api_key(provider_name)
    if db_key:
        return db_key
    env_keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "cohere": settings.cohere_api_key,
    }
    return env_keys.get(provider_name) or None


async def _get_provider():
    """Get the configured LLM provider, respecting runtime overrides and DB keys."""
    from intel_platform.api.routes.admin_config import get_active_provider, get_active_model

    provider_name = get_active_provider()
    model = get_active_model()

    if provider_name == "ollama":
        from intel_platform.llm.ollama import OllamaProvider
        return OllamaProvider(base_url=settings.ollama_base_url, model=model or settings.default_llm_model or "qwen3.5:9b-q4_K_M")

    api_key = await _resolve_api_key(provider_name)
    if api_key:
        if provider_name == "cohere":
            from intel_platform.llm.cohere_provider import CohereProvider
            return CohereProvider(api_key=api_key, model=model or "command-a-03-2025")
        if provider_name == "anthropic":
            from intel_platform.llm.anthropic import AnthropicProvider
            return AnthropicProvider(api_key=api_key, model=model or "claude-sonnet-4-20250514")
        if provider_name == "openai":
            from intel_platform.llm.openai_provider import OpenAIProvider
            return OpenAIProvider(api_key=api_key, model=model or "gpt-4o")

    # Fallback: try any provider with a key (DB or env)
    for fallback in ["cohere", "anthropic", "openai"]:
        key = await _resolve_api_key(fallback)
        if key:
            if fallback == "cohere":
                from intel_platform.llm.cohere_provider import CohereProvider
                return CohereProvider(api_key=key)
            if fallback == "anthropic":
                from intel_platform.llm.anthropic import AnthropicProvider
                return AnthropicProvider(api_key=key)
            if fallback == "openai":
                from intel_platform.llm.openai_provider import OpenAIProvider
                return OpenAIProvider(api_key=key)

    # Last resort: try Ollama
    from intel_platform.llm.ollama import OllamaProvider
    return OllamaProvider(base_url=settings.ollama_base_url, model=model or settings.default_llm_model or "qwen3.5:9b-q4_K_M")


@router.post("/llm/query")
async def llm_query(req: LLMQueryRequest):
    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()

    system = req.system
    if req.skill_name:
        skill_prompt = loader.get_system_prompt(req.skill_name, include_foundation=True)
        if skill_prompt:
            system = f"{skill_prompt}\n\n{system}" if system else skill_prompt

    provider = await _get_provider()
    if not provider:
        return {
            "content": "No LLM provider configured. Add API keys to .env file.",
            "skill_applied": req.skill_name,
            "model": "none",
            "tokens_used": 0,
        }

    result = await provider.generate(
        messages=req.messages, system=system,
        temperature=req.temperature, max_tokens=req.max_tokens,
    )
    response = {
        "content": result.content,
        "skill_applied": req.skill_name,
        "model": result.model,
        "tokens_used": result.total_tokens,
    }
    # Extract probability for assessment-related skills
    if req.skill_name in ("threat_assessment", "report_writing"):
        prob_match = re.search(r'PROBABILITY:\s*(0\.\d+)', result.content)
        if prob_match:
            response["probability"] = float(prob_match.group(1))
    return response


@router.get("/llm/skills", response_model=SkillListResponse)
async def list_skills():
    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    return SkillListResponse(skills=loader.list_skills())
