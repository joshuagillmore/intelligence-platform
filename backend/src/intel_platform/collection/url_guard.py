"""Shared SSRF guard for outbound collection fetches.

A single validator used by every crawl path so URL validation can't be bypassed
by calling a lower-level fetch helper directly. Rejects non-HTTP(S) schemes,
internal service hostnames, and hosts that resolve to private/reserved IPs
(DNS-rebinding defense). Keep this validation in place — it is a documented
security watch-out for this repo.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

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


def validate_url(url: str) -> None:
    """SSRF protection: reject non-HTTP schemes, private IPs, and internal hostnames.

    Raises ValueError when the URL is unsafe to fetch.
    """
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
        pass  # DNS failure — let the fetcher surface the error


def is_safe_url(url: str) -> bool:
    """Non-raising form of :func:`validate_url` for filtering batches of URLs."""
    try:
        validate_url(url)
        return True
    except ValueError:
        return False
