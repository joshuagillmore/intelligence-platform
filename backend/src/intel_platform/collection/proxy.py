from __future__ import annotations

import httpx


class ProxyConfig:
    def __init__(self, mode: str = "direct", proxy_url: str = "", tor_port: int = 9050):
        self.mode = mode  # direct | proxy | tor
        self.proxy_url = proxy_url
        self.tor_port = tor_port

    def get_client_kwargs(self) -> dict:
        if self.mode == "tor":
            return {"proxy": f"socks5://127.0.0.1:{self.tor_port}"}
        elif self.mode == "proxy" and self.proxy_url:
            return {"proxy": self.proxy_url}
        return {}


class ProxiedClient:
    def __init__(self, config: ProxyConfig | None = None):
        self._config = config or ProxyConfig()

    async def get(self, url: str, timeout: float = 30, headers: dict | None = None) -> httpx.Response:
        kwargs = self._config.get_client_kwargs()
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, **kwargs) as client:
            return await client.get(url, headers=headers or {})

    async def fetch_text(self, url: str, timeout: float = 30) -> str:
        response = await self.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
