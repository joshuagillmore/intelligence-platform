from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

from intel_platform.collection.crawler import crawl_urls

_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.internal",
    # Docker Compose service names
    "neo4j",
    "postgres",
    "redis",
    "ollama",
    "backend",
    "frontend",
}


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private, loopback, or link-local."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved
    except ValueError:
        return False


def _validate_url(url: str) -> None:
    """SSRF protection: reject non-HTTP schemes, private IPs, and internal hostnames."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL has no hostname")

    if hostname in _BLOCKED_HOSTNAMES:
        raise ValueError("URLs pointing to internal services are not allowed")

    # Resolve hostname to detect DNS rebinding to internal IPs
    try:
        resolved_ips = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _type, _proto, _canonname, sockaddr in resolved_ips:
            ip_str = sockaddr[0]
            if _is_private_ip(ip_str):
                raise ValueError("URL resolves to a private/internal IP address")
    except socket.gaierror:
        pass  # DNS failure — let crawl4ai handle the error


class WebScraper:
    """Scrape a single URL using crawl4ai's headless browser."""

    async def scrape_url(self, url: str, timeout: float = 30) -> dict:
        _validate_url(url)
        docs = await crawl_urls([url], timeout_ms=int(timeout * 1000))
        if not docs:
            raise RuntimeError(f"Failed to crawl {url}")
        doc = docs[0]
        return {
            "url": doc["url"],
            "title": doc["title"],
            "content": doc["content"],
            "content_length": len(doc["content"]),
        }
