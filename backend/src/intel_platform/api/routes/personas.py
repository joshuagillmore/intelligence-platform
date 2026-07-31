from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from intel_platform.api.deps import verify_api_key

router = APIRouter(dependencies=[Depends(verify_api_key)])

# In-memory persona storage
_personas: dict[str, dict] = {
    "osint_collector": {
        "id": "osint_collector",
        "name": "OSINT Collector",
        "description": "Focused on open source acquisition and source reliability assessment",
        "skills": ["collection_planning", "source_evaluation"],
        "temperature": 0.4,
        "active": True,
    },
    "cyber_analyst": {
        "id": "cyber_analyst",
        "name": "Cyber Threat Analyst",
        "description": "Specialized in CTI analysis and threat actor profiling",
        "skills": ["entity_extraction", "threat_assessment", "gap_analysis"],
        "temperature": 0.3,
        "active": False,
    },
    "allsource": {
        "id": "allsource",
        "name": "All-Source Analyst",
        "description": "Full analytical capability for comprehensive assessments",
        "skills": ["entity_extraction", "source_evaluation", "hypothesis_generation", "threat_assessment", "gap_analysis", "report_writing"],
        "temperature": 0.3,
        "active": False,
    },
    "report_writer": {
        "id": "report_writer",
        "name": "Report Writer",
        "description": "Optimized for intelligence product generation",
        "skills": ["report_writing", "source_evaluation"],
        "temperature": 0.3,
        "active": False,
    },
}

_active_persona: str = "allsource"


def active_persona() -> dict:
    """The persona currently driving analytical work."""
    return _personas.get(_active_persona) or {}


def active_persona_brief() -> str:
    """A short framing line for prompts that decompose or judge a requirement.

    Personas existed here but reached nothing that mattered: they were never
    consulted when a PIR was broken into elements, so a cyber analyst and a
    maritime analyst decomposed an identical question identically. Which
    elements a requirement is split into determines what gets collected, so this
    is the point where expertise changes the outcome rather than the wording.

    Returns "" when no persona is active, leaving the caller's prompt untouched.
    """
    persona = active_persona()
    if not persona:
        return ""
    parts = [f"You are working as the {persona.get('name', 'analyst')}."]
    if persona.get("description"):
        parts.append(str(persona["description"]).strip().rstrip(".") + ".")
    skills = [str(s).replace("_", " ") for s in (persona.get("skills") or [])]
    if skills:
        parts.append("Your emphasis: " + ", ".join(skills) + ".")
    parts.append(
        "Decompose and judge from that expertise: the sub-questions a specialist "
        "would insist on are the ones worth collecting against."
    )
    return " ".join(parts)


def active_persona_temperature(default: float = 0.3) -> float:
    try:
        return float(active_persona().get("temperature", default))
    except (TypeError, ValueError):
        return default


class PersonaRequest(BaseModel):
    id: str
    name: str
    description: str
    skills: list[str]
    temperature: float = 0.3


@router.get("/personas")
def list_personas():
    return {
        "personas": list(_personas.values()),
        "active_persona": _active_persona,
    }


@router.post("/personas")
def create_persona(req: PersonaRequest):
    _personas[req.id] = {
        "id": req.id,
        "name": req.name,
        "description": req.description,
        "skills": req.skills,
        "temperature": req.temperature,
        "active": False,
    }
    return _personas[req.id]


@router.post("/personas/{persona_id}/activate")
def activate_persona(persona_id: str):
    global _active_persona
    if persona_id not in _personas:
        raise HTTPException(status_code=404, detail="Persona not found")
    for p in _personas.values():
        p["active"] = False
    _personas[persona_id]["active"] = True
    _active_persona = persona_id
    return {"active_persona": persona_id}


@router.delete("/personas/{persona_id}")
def delete_persona(persona_id: str):
    if persona_id not in _personas:
        raise HTTPException(status_code=404, detail="Persona not found")
    if persona_id in ("osint_collector", "cyber_analyst", "allsource", "report_writer"):
        raise HTTPException(status_code=400, detail="Cannot delete built-in personas")
    del _personas[persona_id]
    return {"status": "deleted"}


@router.get("/personas/active")
def get_active_persona():
    return _personas.get(_active_persona, {})
