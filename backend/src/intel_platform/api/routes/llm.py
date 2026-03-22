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


def _get_provider():
    """Get the configured LLM provider."""
    if settings.cohere_api_key:
        from intel_platform.llm.cohere_provider import CohereProvider
        return CohereProvider(api_key=settings.cohere_api_key)
    if settings.anthropic_api_key:
        from intel_platform.llm.anthropic import AnthropicProvider
        return AnthropicProvider(api_key=settings.anthropic_api_key)
    if settings.openai_api_key:
        from intel_platform.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(api_key=settings.openai_api_key)
    return None


@router.post("/llm/query")
async def llm_query(req: LLMQueryRequest):
    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()

    system = req.system
    if req.skill_name:
        skill_prompt = loader.get_system_prompt(req.skill_name, include_foundation=True)
        if skill_prompt:
            system = f"{skill_prompt}\n\n{system}" if system else skill_prompt

    provider = _get_provider()
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
