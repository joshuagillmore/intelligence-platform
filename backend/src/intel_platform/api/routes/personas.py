import copy
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from intel_platform.api.deps import require_admin, verify_api_key
from intel_platform.models.responses import (
    EmptyResponse,
    PersonaActivatedResponse,
    PersonaListResponse,
    PersonaResponse,
    StatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(verify_api_key)])

# Built-in personas live here, in code; they cannot be overwritten or deleted.
_BUILTIN_PERSONAS: dict[str, dict] = {
    "osint_collector": {
        "id": "osint_collector",
        "name": "OSINT Collector",
        "description": "Focused on open source acquisition and source reliability assessment",
        "skills": ["collection_planning", "source_evaluation"],
        "temperature": 0.4,
        "active": False,
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
        "active": True,
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

_BUILTIN_PERSONA_IDS = frozenset(_BUILTIN_PERSONAS)
_DEFAULT_ACTIVE = "allsource"

# Custom personas and the active selection are AppSetting rows (custom personas
# as one JSON object keyed by id; the active id as a string), so they survive a
# restart. `_personas` and `_active_persona` are this process's cache of them —
# prompt construction reads the active persona synchronously. The cache is
# loaded with the other persisted settings (admin_config.refresh_persisted_settings).
CUSTOM_PERSONAS_KEY = "personas_custom"
ACTIVE_PERSONA_KEY = "persona_active"

_personas: dict[str, dict] = copy.deepcopy(_BUILTIN_PERSONAS)
_active_persona: str = _DEFAULT_ACTIVE


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


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _custom_personas(personas: dict[str, dict]) -> dict[str, dict]:
    """The custom personas in ``personas``, as stored (no ``active`` flag)."""
    return {
        pid: {k: v for k, v in p.items() if k != "active"}
        for pid, p in personas.items() if pid not in _BUILTIN_PERSONA_IDS
    }


def _apply(custom: dict[str, dict], active: str | None) -> None:
    """Replace the cache with the built-ins, ``custom`` and the active id."""
    global _active_persona
    rebuilt = copy.deepcopy(_BUILTIN_PERSONAS)
    for pid, p in custom.items():
        # A built-in id in the stored row (edited by hand, or written by an
        # older build) never replaces the built-in.
        if pid in _BUILTIN_PERSONA_IDS or not isinstance(p, dict):
            continue
        rebuilt[pid] = {
            "id": pid,
            "name": str(p.get("name", pid)),
            "description": str(p.get("description", "")),
            "skills": [str(s) for s in (p.get("skills") or [])],
            "temperature": p.get("temperature", 0.3),
        }
    if active in rebuilt:
        _active_persona = active
    elif _active_persona not in rebuilt:
        _active_persona = _DEFAULT_ACTIVE
    for pid, p in rebuilt.items():
        p["active"] = pid == _active_persona
    _personas.clear()
    _personas.update(rebuilt)


async def load_personas() -> None:
    """Load the stored custom personas and active selection into the cache."""
    from intel_platform.api.routes import admin_config

    stored = await admin_config.read_app_settings([CUSTOM_PERSONAS_KEY, ACTIVE_PERSONA_KEY])
    custom: dict[str, dict] = {}
    raw = stored.get(CUSTOM_PERSONAS_KEY)
    if raw is not None:
        try:
            parsed = json.loads(raw)
            custom = parsed if isinstance(parsed, dict) else {}
        except ValueError:
            logger.warning("Ignoring an unreadable %s setting", CUSTOM_PERSONAS_KEY)
    _apply(custom, stored.get(ACTIVE_PERSONA_KEY))


async def _persist(values: dict[str, str]) -> None:
    """Save before changing the cache; a change that would not survive a
    restart is refused rather than applied in memory only."""
    from intel_platform.api.routes import admin_config

    try:
        await admin_config.write_app_settings(values)
    except Exception:
        logger.warning("Could not persist personas", exc_info=True)
        raise HTTPException(status_code=503, detail="Could not save personas")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/personas", response_model=PersonaListResponse)
def list_personas():
    return {
        "personas": list(_personas.values()),
        "active_persona": _active_persona,
    }


# The active persona shapes how every user's requirements are decomposed, so
# creating, changing, activating or deleting one is an admin action; reading
# them is not.


@router.post("/personas", response_model=PersonaResponse, dependencies=[Depends(require_admin)])
async def create_persona(req: PersonaRequest):
    """Create a persona, or update a custom one. Built-ins cannot be overwritten."""
    if req.id in _BUILTIN_PERSONA_IDS:
        raise HTTPException(status_code=409, detail="A built-in persona cannot be overwritten")
    persona = {
        "id": req.id,
        "name": req.name,
        "description": req.description,
        "skills": req.skills,
        "temperature": req.temperature,
    }
    custom = {**_custom_personas(_personas), req.id: persona}
    await _persist({CUSTOM_PERSONAS_KEY: json.dumps(custom)})
    # Updating the active persona keeps it active.
    _personas[req.id] = {**persona, "active": req.id == _active_persona}
    return _personas[req.id]


@router.post(
    "/personas/{persona_id}/activate", response_model=PersonaActivatedResponse,
    dependencies=[Depends(require_admin)],
)
async def activate_persona(persona_id: str):
    global _active_persona
    if persona_id not in _personas:
        raise HTTPException(status_code=404, detail="Persona not found")
    await _persist({ACTIVE_PERSONA_KEY: persona_id})
    for p in _personas.values():
        p["active"] = False
    _personas[persona_id]["active"] = True
    _active_persona = persona_id
    return {"active_persona": persona_id}


@router.delete("/personas/{persona_id}", response_model=StatusResponse, dependencies=[Depends(require_admin)])
async def delete_persona(persona_id: str):
    if persona_id not in _personas:
        raise HTTPException(status_code=404, detail="Persona not found")
    if persona_id in _BUILTIN_PERSONA_IDS:
        raise HTTPException(status_code=400, detail="Cannot delete built-in personas")
    custom = {pid: p for pid, p in _custom_personas(_personas).items() if pid != persona_id}
    await _persist({CUSTOM_PERSONAS_KEY: json.dumps(custom)})
    del _personas[persona_id]
    return {"status": "deleted"}


# `{}` once the active persona is a custom one that has been deleted.
@router.get("/personas/active", response_model=PersonaResponse | EmptyResponse)
def get_active_persona():
    return _personas.get(_active_persona, {})
