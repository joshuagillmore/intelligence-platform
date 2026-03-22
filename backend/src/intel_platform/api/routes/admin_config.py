from fastapi import APIRouter, Depends
from pydantic import BaseModel
from intel_platform.api.deps import verify_api_key
from intel_platform.config import settings

router = APIRouter(dependencies=[Depends(verify_api_key)])


class ProxyConfigRequest(BaseModel):
    mode: str = "direct"  # direct | proxy | tor
    proxy_url: str = ""
    tor_port: int = 9050


_proxy_config: dict = {"mode": "direct", "proxy_url": "", "tor_port": 9050}


@router.get("/admin/config")
def get_config():
    """Return non-sensitive configuration info."""
    return {
        "llm_provider": "cohere" if settings.cohere_api_key else
                        "anthropic" if settings.anthropic_api_key else
                        "openai" if settings.openai_api_key else "none",
        "extraction_mode": settings.extraction_mode,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "neo4j_uri": settings.neo4j_uri.split("@")[-1] if "@" in settings.neo4j_uri else settings.neo4j_uri,
        "proxy": _proxy_config,
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
