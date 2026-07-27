
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from intel_platform.services.llm_output import labelled_probability
from intel_platform.api.deps import verify_api_key

# Provider selection lives in intel_platform.llm.providers (single source of
# truth). Re-exported here for backwards compatibility: existing call sites and
# tests import these names from intel_platform.api.routes.llm, and llm_query
# below patches through the module global _get_provider.
from intel_platform.llm.providers import (  # noqa: F401
    _cloud_provider_from_env,
    _get_collection_provider,
    _get_extraction_provider,
    _get_provider,
    _resolve_api_key,
)

router = APIRouter(dependencies=[Depends(verify_api_key)])


class LLMQueryRequest(BaseModel):
    messages: list[dict]
    system: str = ""
    skill_name: str | None = None
    system_prompt: str | None = None  # explicit override of the skill's system prompt (LLM Hub skill editor)
    temperature: float = 0.3
    max_tokens: int = 4096
    provider: str | None = None
    stream: bool = False


class SkillListResponse(BaseModel):
    skills: list[dict]


@router.post("/llm/query")
async def llm_query(req: LLMQueryRequest):
    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()

    system = req.system
    if req.system_prompt:
        # Explicit system-prompt override (e.g. LLM Hub skill editor) wins over the skill's stored prompt.
        system = req.system_prompt
    elif req.skill_name:
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
        # Emphasis-tolerant: the model replies "**PROBABILITY:** **0.70**", which
        # a pattern anchored on the requested shape cannot cross. The sentinel
        # keeps "not stated" distinct from a real value.
        stated = labelled_probability(result.content, -1.0)
        if stated > 0:
            response["probability"] = stated
    return response


@router.get("/llm/skills", response_model=SkillListResponse)
async def list_skills():
    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    return SkillListResponse(skills=loader.list_skills())
