import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, update

from intel_platform.api.deps import require_admin
from intel_platform.collection.proxy import PROXY_MODE_KEY, VALID_PROXY_MODES
from intel_platform.config import settings
from intel_platform.crypto import decrypt, encrypt
from intel_platform.db.engine import get_session_factory
from intel_platform.db.models import ApiKey, AppSetting

router = APIRouter(dependencies=[Depends(require_admin)])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class ProxyConfigRequest(BaseModel):
    mode: str = "direct"  # direct | vpn | tor | proxy
    proxy_url: str = ""
    tor_port: int = 9050


class VpnActionRequest(BaseModel):
    action: str = "start"  # start | stop


class LLMConfigRequest(BaseModel):
    provider: str  # ollama | cohere | anthropic | openai
    model: str = ""


class ApiKeyCreateRequest(BaseModel):
    provider: str  # anthropic | openai | cohere
    label: str
    api_key: str


class ApiKeyActivateRequest(BaseModel):
    key_id: str
    provider: str


# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------

# Runtime-mutable LLM overrides (survive until container restart)
_llm_override: dict = {"provider": "", "model": ""}


async def _read_proxy_mode() -> str:
    """Read the persisted collection-egress proxy mode (fail-safe to direct)."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(AppSetting.value).where(AppSetting.key == PROXY_MODE_KEY)
        )
        mode = result.scalar_one_or_none()
    return mode if mode in VALID_PROXY_MODES else "direct"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _mask_key(key: str) -> str:
    """Show only the last 4 characters of a key."""
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


async def get_active_api_key(provider: str) -> str | None:
    """Return the active API key for a provider from the database, or None."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(ApiKey.api_key).where(
                ApiKey.provider == provider,
                ApiKey.is_active == True,  # noqa: E712
            )
        )
        row = result.scalar_one_or_none()
        return decrypt(row) if row else None


async def _provider_has_key(provider: str) -> bool:
    """Check if a provider has at least one API key stored in the database."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(ApiKey.id).where(ApiKey.provider == provider).limit(1)
        )
        return result.scalar_one_or_none() is not None


async def _provider_has_active_key(provider: str) -> bool:
    """Check if a provider has an active API key (DB or env)."""
    # Check DB first
    db_key = await get_active_api_key(provider)
    if db_key:
        return True
    # Fall back to env vars
    env_keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "cohere": settings.cohere_api_key,
    }
    return bool(env_keys.get(provider, ""))


# ---------------------------------------------------------------------------
# Config endpoints
# ---------------------------------------------------------------------------

@router.get("/admin/config")
async def get_config():
    """Return non-sensitive configuration info."""
    provider = get_active_provider()
    model = get_active_model()
    try:
        proxy_mode = await _read_proxy_mode()
    except Exception:
        proxy_mode = "direct"
    return {
        "llm_provider": provider,
        "llm_model": model,
        "extraction_mode": settings.extraction_mode,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "neo4j_uri": settings.neo4j_uri.split("@")[-1] if "@" in settings.neo4j_uri else settings.neo4j_uri,
        "proxy": {"mode": proxy_mode},
    }


# ---------------------------------------------------------------------------
# API Key management endpoints
# ---------------------------------------------------------------------------

@router.get("/admin/api-keys")
async def list_api_keys():
    """List all stored API keys with masked values."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(ApiKey).order_by(ApiKey.provider, ApiKey.created_at)
        )
        keys = result.scalars().all()
        return {
            "keys": [
                {
                    "id": str(k.id),
                    "provider": k.provider,
                    "label": k.label,
                    "key_preview": _mask_key(decrypt(k.api_key)),
                    "is_active": k.is_active,
                    "created_at": k.created_at.isoformat() if k.created_at else None,
                }
                for k in keys
            ]
        }


@router.post("/admin/api-keys")
async def add_api_key(req: ApiKeyCreateRequest):
    """Add a new API key for a provider."""
    factory = get_session_factory()
    async with factory() as session:
        # Check how many keys exist for this provider
        result = await session.execute(
            select(ApiKey).where(ApiKey.provider == req.provider)
        )
        existing = result.scalars().all()

        # If this is the first key for the provider, make it active
        is_active = len(existing) == 0

        new_key = ApiKey(
            provider=req.provider,
            label=req.label,
            api_key=encrypt(req.api_key),
            is_active=is_active,
        )
        session.add(new_key)
        await session.commit()
        await session.refresh(new_key)

        return {
            "id": str(new_key.id),
            "provider": new_key.provider,
            "label": new_key.label,
            "key_preview": _mask_key(req.api_key),
            "is_active": new_key.is_active,
            "status": "ok",
        }


@router.put("/admin/api-keys/activate")
async def activate_api_key(req: ApiKeyActivateRequest):
    """Set a specific key as the active key for its provider."""
    factory = get_session_factory()
    async with factory() as session:
        # Deactivate all keys for this provider
        await session.execute(
            update(ApiKey)
            .where(ApiKey.provider == req.provider)
            .values(is_active=False)
        )
        # Activate the selected key
        await session.execute(
            update(ApiKey)
            .where(ApiKey.id == req.key_id)
            .values(is_active=True)
        )
        await session.commit()
        return {"status": "ok", "active_key_id": req.key_id}


@router.delete("/admin/api-keys/{key_id}")
async def delete_api_key(key_id: str):
    """Delete an API key by ID."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.id == key_id)
        )
        key = result.scalar_one_or_none()
        if not key:
            return {"status": "not_found"}

        was_active = key.is_active
        provider = key.provider
        await session.delete(key)
        await session.flush()

        # If the deleted key was active, promote another key for this provider
        if was_active:
            result = await session.execute(
                select(ApiKey)
                .where(ApiKey.provider == provider)
                .order_by(ApiKey.created_at)
                .limit(1)
            )
            next_key = result.scalar_one_or_none()
            if next_key:
                next_key.is_active = True

        await session.commit()
        return {"status": "ok"}


# ---------------------------------------------------------------------------
# LLM model listing & selection
# ---------------------------------------------------------------------------

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
                        "configured": True,
                    })
    except Exception:
        pass

    # Cloud providers – always list; check DB + env for configured status
    cloud_models = [
        ("anthropic", "claude-sonnet-4-20250514"),
        ("anthropic", "claude-opus-4-20250514"),
        ("anthropic", "claude-haiku-4-5-20251001"),
        ("openai", "gpt-4o"),
        ("openai", "gpt-4o-mini"),
        ("openai", "o3-mini"),
        ("cohere", "command-a-plus-05-2026"),
        ("cohere", "command-a-03-2025"),
        ("cohere", "command-r-plus"),
        ("cohere", "command-r"),
    ]
    for provider, model in cloud_models:
        configured = await _provider_has_active_key(provider)
        models.append({
            "provider": provider,
            "model": model,
            "params": "",
            "quantization": "",
            "size_gb": 0,
            "configured": configured,
        })

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


# ---------------------------------------------------------------------------
# Collection-egress proxy configuration (persisted; OFF by default)
#
# Only the web-collection egress (crawl4ai + ddgs + httpx connectors) is
# proxied. LLM / cloud API calls always go out direct. The active mode lives
# in Postgres (AppSetting) so it survives restarts.
# ---------------------------------------------------------------------------

def _proxy_state(mode: str) -> dict:
    """Response body: the active mode plus the configured proxy URLs (display)."""
    return {
        "mode": mode,
        "vpn_http_proxy": settings.vpn_http_proxy,
        "tor_socks_proxy": settings.tor_socks_proxy,
    }


@router.get("/admin/proxy")
async def get_proxy_config():
    try:
        mode = await _read_proxy_mode()
    except Exception:
        mode = "direct"
    return _proxy_state(mode)


@router.put("/admin/proxy")
async def update_proxy_config(req: ProxyConfigRequest):
    mode = req.mode if req.mode in VALID_PROXY_MODES else "direct"
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(AppSetting).where(AppSetting.key == PROXY_MODE_KEY)
        )
        row = result.scalar_one_or_none()
        if row is None:
            session.add(AppSetting(key=PROXY_MODE_KEY, value=mode))
        else:
            row.value = mode
        await session.commit()
    return _proxy_state(mode)


# ---------------------------------------------------------------------------
# VPN status / kill-switch — proxies gluetun's control server.
#
# These calls go DIRECTLY to gluetun's control API (not through the tunnel).
# Errors never propagate to the client: gluetun-unreachable degrades to a
# clean {reachable: false} payload rather than a 500.
# ---------------------------------------------------------------------------

def _gluetun_headers() -> dict:
    key = settings.gluetun_control_apikey
    return {"X-API-Key": key} if key else {}


@router.get("/admin/vpn/status")
async def get_vpn_status():
    """Report gluetun VPN status + public IP. Never 500s on an unreachable VPN."""
    base = settings.gluetun_control_url.rstrip("/")
    headers = _gluetun_headers()
    try:
        import asyncio
        async with httpx.AsyncClient(timeout=5) as client:
            ip_resp, status_resp = await asyncio.gather(
                client.get(f"{base}/v1/publicip/ip", headers=headers),
                client.get(f"{base}/v1/vpn/status", headers=headers),
            )
    except Exception:
        return {"reachable": False, "running": False}

    try:
        mode = await _read_proxy_mode()
    except Exception:
        mode = "direct"

    ip_data: dict = {}
    status_data: dict = {}
    try:
        ip_data = ip_resp.json()
    except Exception:
        pass
    try:
        status_data = status_resp.json()
    except Exception:
        pass

    status_val = str(status_data.get("status", "")).lower()
    return {
        "reachable": True,
        "running": status_val == "running",
        "status": status_val,
        "public_ip": ip_data.get("public_ip", "") or ip_data.get("ip", ""),
        "country": ip_data.get("country", ""),
        "region": ip_data.get("region", ""),
        "city": ip_data.get("city", ""),
        "mode": mode,
    }


@router.put("/admin/vpn/status")
async def set_vpn_status(req: VpnActionRequest):
    """Stop (kill-switch) or start the gluetun VPN tunnel."""
    base = settings.gluetun_control_url.rstrip("/")
    headers = _gluetun_headers()
    desired = "stopped" if req.action == "stop" else "running"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.put(
                f"{base}/v1/vpn/status", json={"status": desired}, headers=headers,
            )
    except Exception:
        return {"ok": False, "reachable": False}

    if resp.status_code >= 400:
        return {"ok": False, "reachable": True}
    outcome = desired
    try:
        outcome = resp.json().get("outcome", desired)
    except Exception:
        pass
    return {"ok": True, "reachable": True, "outcome": outcome}
