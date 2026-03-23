from __future__ import annotations

from bs4 import BeautifulSoup

from intel_platform.collection.proxy import ProxiedClient, ProxyConfig


class WebScraper:
    def __init__(self, proxy_config: ProxyConfig | None = None, max_content_size: int = 10_000_000):
        self._client = ProxiedClient(proxy_config)
        self._max_size = max_content_size

    async def scrape_url(self, url: str, timeout: float = 30) -> dict:
        # SECURITY: reject non-HTTP(S) schemes and private/internal network URLs
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")
        hostname = (parsed.hostname or "").lower()
        if hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or hostname.startswith("169.254.") or hostname.startswith("10.") or hostname.startswith("192.168."):
            raise ValueError("URLs pointing to internal/private networks are not allowed")

        html = await self._client.fetch_text(url, timeout=timeout)
        if len(html) > self._max_size:
            html = html[: self._max_size]
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        title = soup.title.string if soup.title else ""
        text = soup.get_text(separator="\n", strip=True)
        return {"url": url, "title": title.strip() if title else "", "content": text, "content_length": len(text)}
