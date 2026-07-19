"""Collection-egress proxy for web collection ONLY.

Routes crawl4ai + ddgs + the httpx connectors through an optional, admin-
selectable proxy (Off / VPN / Tor). LLM and cloud API calls must NEVER use
this — they always go out direct.

The active mode is persisted in Postgres (AppSetting "collection_proxy_mode")
so it survives restarts. Any error resolving the mode degrades to DIRECT — a
proxy-config problem must never crash a crawl.
"""
from __future__ import annotations

import logging

import httpx

from intel_platform.config import settings

logger = logging.getLogger(__name__)

# AppSetting key the active collection proxy mode is stored under.
PROXY_MODE_KEY = "collection_proxy_mode"

# Selectable modes. "vpn" -> gluetun HTTP proxy, "tor" -> Tor SOCKS5,
# "proxy" -> an explicit ad-hoc proxy_url, "direct" -> no proxy.
VALID_PROXY_MODES = ("direct", "vpn", "tor")


class ProxyConfig:
    def __init__(self, mode: str = "direct", proxy_url: str = "", tor_port: int = 9050):
        self.mode = mode  # direct | vpn | tor | proxy
        self.proxy_url = proxy_url
        self.tor_port = tor_port

    def get_proxy_url(self) -> str | None:
        """Resolve the egress proxy URL for this mode, or None for direct."""
        if self.mode == "vpn":
            return settings.vpn_http_proxy or None
        if self.mode == "tor":
            return settings.tor_socks_proxy or None
        if self.mode == "proxy":
            return self.proxy_url or None
        return None  # direct (and any unknown mode) -> no proxy

    def get_client_kwargs(self) -> dict:
        """httpx.AsyncClient kwargs for this mode: {"proxy": url} or {}."""
        url = self.get_proxy_url()
        return {"proxy": url} if url else {}


async def get_active_proxy_config() -> ProxyConfig:
    """Read the active collection proxy mode from Postgres.

    Fail-safe: any error (DB down, table missing, unknown value) degrades to
    DIRECT so a proxy-config issue can never take down web collection.
    Read fresh each call — collection is not a hot path, so this always
    reflects the latest admin change.
    """
    try:
        from sqlalchemy import select

        from intel_platform.db.engine import get_session_factory
        from intel_platform.db.models import AppSetting

        factory = get_session_factory()
        async with factory() as session:
            result = await session.execute(
                select(AppSetting.value).where(AppSetting.key == PROXY_MODE_KEY)
            )
            mode = result.scalar_one_or_none()
    except Exception:
        logger.debug("Could not read collection proxy mode; defaulting to direct", exc_info=True)
        return ProxyConfig(mode="direct")

    if mode not in VALID_PROXY_MODES:
        return ProxyConfig(mode="direct")
    return ProxyConfig(mode=mode)


class ProxiedClient:
    """Thin httpx wrapper that honors the active collection proxy.

    Constructed with config=None (the default across all connectors), it lazily
    resolves the active ProxyConfig on each request — so switching the admin
    proxy mode takes effect without touching any connector code.
    """

    def __init__(self, config: ProxyConfig | None = None):
        self._config = config

    async def _resolve_config(self) -> ProxyConfig:
        return self._config or await get_active_proxy_config()

    async def get(self, url: str, timeout: float = 30, headers: dict | None = None) -> httpx.Response:
        cfg = await self._resolve_config()
        kwargs = cfg.get_client_kwargs()
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, **kwargs) as client:
            return await client.get(url, headers=headers or {})

    async def fetch_text(self, url: str, timeout: float = 30) -> str:
        response = await self.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
