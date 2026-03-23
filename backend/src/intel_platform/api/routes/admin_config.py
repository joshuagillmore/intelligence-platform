import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from intel_platform.api.deps import verify_api_key
from intel_platform.config import settings

router = APIRouter(dependencies=[Depends(verify_api_key)])


class ProxyConfigRequest(BaseModel):
    mode: str = "direct"  # direct | proxy | tor
    proxy_url: str = ""
    tor_port: int = 9050


class LLMConfigRequest(BaseModel):
    provider: str  # ollama | cohere | anthropic | openai
    model: str = ""


_proxy_config: dict = {"mode": "direct", "proxy_url": "", "tor_port": 9050}

# Runtime-mutable LLM overrides (survive until container restart)
_llm_override: dict = {"provider": "", "model": ""}


def get_active_provider() -> str:
    """Return the currently active LLM provider name."""
    if _llm_override["provider"]:
        return _llm_override["provider"]
    return settings.default_llm_provider


def get_active_model() -> str:
    """Return the currently active model name."""
    if _llm_override["model"]:
        return _llm_override["model"]
    return settings.default_llm_model


@router.get("/admin/config")
def get_config():
    """Return non-sensitive configuration info."""
    provider = get_active_provider()
    model = get_active_model()
    return {
        "llm_provider": provider,
        "llm_model": model,
        "extraction_mode": settings.extraction_mode,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "neo4j_uri": settings.neo4j_uri.split("@")[-1] if "@" in settings.neo4j_uri else settings.neo4j_uri,
        "proxy": _proxy_config,
    }


@router.get("/admin/llm/models")
async def list_available_models():
    """List models available from all configured providers."""
    models: list[dict] = []

    # Ollama models
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            if resp.status_code == 200:
                for m in resp.json().get("models", []):
                    size_gb = round(m.get("size", 0) / 1e9, 1)
                    models.append({
                        "provider": "ollama",
                        "model": m["name"],
                        "params": m.get("details", {}).get("parameter_size", ""),
                        "quantization": m.get("details", {}).get("quantization_level", ""),
                        "size_gb": size_gb,
                    })
    except Exception:
        pass

    # Cloud providers (just show configured ones)
    if settings.cohere_api_key:
        models.append({"provider": "cohere", "model": "command-a-03-2025", "params": "", "quantization": "", "size_gb": 0})
    if settings.anthropic_api_key:
        models.append({"provider": "anthropic", "model": "claude-sonnet-4-20250514", "params": "", "quantization": "", "size_gb": 0})
    if settings.openai_api_key:
        models.append({"provider": "openai", "model": "gpt-4o", "params": "", "quantization": "", "size_gb": 0})

    return {
        "models": models,
        "active_provider": get_active_provider(),
        "active_model": get_active_model(),
    }


@router.put("/admin/llm/select")
def select_llm(req: LLMConfigRequest):
    """Switch the active LLM provider and model at runtime."""
    _llm_override["provider"] = req.provider
    _llm_override["model"] = req.model
    return {
        "active_provider": req.provider,
        "active_model": req.model,
        "status": "ok",
    }


@router.get("/admin/proxy")
def get_proxy_config():
    return _proxy_config


@router.put("/admin/proxy")
def update_proxy_config(req: ProxyConfigRequest):
    _proxy_config["mode"] = req.mode
    _proxy_config["proxy_url"] = req.proxy_url
    _proxy_config["tor_port"] = req.tor_port
    return _proxy_config
