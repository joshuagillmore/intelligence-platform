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

import httpcore
import httpx

from intel_platform.collection.url_guard import resolve_host_async, validate_url_async
from intel_platform.config import settings

logger = logging.getLogger(__name__)

# AppSetting key the active collection proxy mode is stored under.
PROXY_MODE_KEY = "collection_proxy_mode"

# Cap redirect chains so a hostile server can't loop us; each hop is
# still SSRF-validated by _ssrf_guard_hook below.
MAX_REDIRECTS = 5


async def _ssrf_guard_hook(request: httpx.Request) -> None:
    """httpx request event-hook: SSRF-validate every outbound URL.

    Fires for the initial request AND each redirect hop httpx follows, so a
    3xx pointing at an internal host is rejected before we connect to it.
    Raises ValueError (surfaced to the caller) when a URL is unsafe.

    Only the checks that need no lookup run here. In direct mode the address
    is resolved and vetted once, at connect time, by `_PinnedBackend`; behind a
    proxy the target is resolved at the far end and must not be looked up
    locally at all.
    """
    await validate_url_async(str(request.url), resolve=False)


class _PinnedBackend(httpcore.AsyncNetworkBackend):
    """Connects only to an address the SSRF guard vetted, resolving each host once.

    The guard used to resolve a host and approve it, then httpx resolved it
    again to connect. A TTL-0 rebinding name answers the first lookup with a
    public address and the second with 127.0.0.1. Here the one lookup the guard
    vets is the one the socket uses. TLS still verifies against the hostname:
    httpcore passes it as the SNI/server name independently of the address.
    """

    #: Builds the real socket layer. A class attribute so tests can swap it.
    inner_factory = staticmethod(httpcore.AnyIOBackend)

    def __init__(self):
        self._inner = self.inner_factory()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        addresses = await resolve_host_async(host)
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._inner.connect_tcp(
                    address, port, timeout=timeout,
                    local_address=local_address, socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout, OSError) as exc:
                last_error = exc
        raise last_error or httpcore.ConnectError(f"Could not connect to {host}")

    async def connect_unix_socket(self, path, timeout=None, socket_options=None):
        raise httpcore.ConnectError("Unix sockets are not an outbound collection path")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


def _pinned_transport() -> httpx.AsyncHTTPTransport:
    """An httpx transport whose connections go through `_PinnedBackend`.

    httpx does not expose the network backend, so it is set on the pool it
    builds. If a future httpx/httpcore moves that attribute, refuse to fetch
    rather than silently fall back to the unpinned resolver.
    """
    transport = httpx.AsyncHTTPTransport()
    pool = getattr(transport, "_pool", None)
    if pool is None or not hasattr(pool, "_network_backend"):
        raise RuntimeError("httpx transport internals changed; refusing to fetch without DNS pinning")
    pool._network_backend = _PinnedBackend()
    return transport

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


_DEFAULT_MAX_FETCH_BYTES = 10_000_000

# Headers describing the body as it came off the wire. The rebuilt response
# holds the decoded body, so keeping them would make httpx decode it again.
_WIRE_HEADERS = {"content-encoding", "content-length", "transfer-encoding"}


class ResponseTooLarge(httpx.HTTPError):
    """A response body exceeded the fetch cap.

    An httpx.HTTPError, so callers that already treat transport failures as
    failures (the enrichment providers do) handle it without changes.
    """


def _fetch_cap(max_bytes: int | None) -> int:
    if max_bytes is not None:
        return max_bytes
    return int(getattr(settings, "max_fetch_bytes", _DEFAULT_MAX_FETCH_BYTES))


async def _read_capped(response: httpx.Response, cap: int) -> httpx.Response:
    """Read a streamed response up to `cap` decoded bytes, then rebuild it whole.

    The cap counts decoded bytes, so a small compressed body that inflates past
    it is refused too. A declared Content-Length over the cap is refused before
    anything is read.
    """
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > cap:
        raise ResponseTooLarge(f"Response declares {declared} bytes, over the {cap}-byte fetch cap")
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > cap:
            raise ResponseTooLarge(f"Response exceeded the {cap}-byte fetch cap")
        chunks.append(chunk)
    headers = [(k, v) for k, v in response.headers.multi_items() if k.lower() not in _WIRE_HEADERS]
    return httpx.Response(
        status_code=response.status_code,
        headers=headers,
        content=b"".join(chunks),
        request=response.request,
        extensions=response.extensions,
        history=response.history,
    )


class ProxiedClient:
    """Thin httpx wrapper that honors the active collection proxy.

    Constructed with config=None (the default across all connectors), it lazily
    resolves the active ProxyConfig on each request — so switching the admin
    proxy mode takes effect without touching any connector code.

    Bodies are streamed and capped at `max_bytes` (default
    ``settings.max_fetch_bytes``, 10 MB). A caller that legitimately downloads
    more — a reference catalogue — passes a larger cap per client or per call.
    """

    def __init__(self, config: ProxyConfig | None = None, max_bytes: int | None = None):
        self._config = config
        self._max_bytes = max_bytes

    async def _resolve_config(self) -> ProxyConfig:
        return self._config or await get_active_proxy_config()

    def _cap(self, max_bytes: int | None) -> int:
        return _fetch_cap(max_bytes if max_bytes is not None else self._max_bytes)

    @staticmethod
    def _client_kwargs(cfg: ProxyConfig, timeout: float) -> dict:
        kwargs: dict = {
            "timeout": timeout, "follow_redirects": True, "max_redirects": MAX_REDIRECTS,
            "event_hooks": {"request": [_ssrf_guard_hook]},
        }
        proxy_kwargs = cfg.get_client_kwargs()
        if proxy_kwargs:
            kwargs.update(proxy_kwargs)  # resolved at the proxy's end, never here
        else:
            kwargs["transport"] = _pinned_transport()
        return kwargs

    async def get(self, url: str, timeout: float = 30, headers: dict | None = None,
                  params: dict | None = None, max_bytes: int | None = None) -> httpx.Response:
        cfg = await self._resolve_config()
        async with httpx.AsyncClient(**self._client_kwargs(cfg, timeout)) as client:
            async with client.stream("GET", url, headers=headers or {}, params=params) as response:
                return await _read_capped(response, self._cap(max_bytes))

    async def post(self, url: str, timeout: float = 30, headers: dict | None = None,
                   json: dict | None = None, data: dict | None = None,
                   params: dict | None = None, max_bytes: int | None = None) -> httpx.Response:
        cfg = await self._resolve_config()
        async with httpx.AsyncClient(**self._client_kwargs(cfg, timeout)) as client:
            async with client.stream(
                "POST", url, headers=headers or {}, json=json, data=data, params=params,
            ) as response:
                return await _read_capped(response, self._cap(max_bytes))

    async def fetch_text(self, url: str, timeout: float = 30, max_bytes: int | None = None) -> str:
        response = await self.get(url, timeout=timeout, max_bytes=max_bytes)
        response.raise_for_status()
        return response.text
