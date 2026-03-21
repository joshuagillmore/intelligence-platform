from fastapi import APIRouter, Depends
from pydantic import BaseModel
from intel_platform.api.deps import verify_api_key

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


@router.post("/llm/query")
async def llm_query(req: LLMQueryRequest):
    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    system = req.system
    if req.skill_name:
        skill_prompt = loader.get_system_prompt(req.skill_name, include_foundation=True)
        if skill_prompt:
            system = f"{skill_prompt}\n\n{system}" if system else skill_prompt
    return {"skill_applied": req.skill_name, "system_prompt_length": len(system), "message_count": len(req.messages), "note": "LLM providers require API keys. Configure in .env and restart."}


@router.get("/llm/skills", response_model=SkillListResponse)
async def list_skills():
    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    return SkillListResponse(skills=loader.list_skills())
