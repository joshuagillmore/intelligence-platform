"""Shared SSRF guard for outbound collection fetches.

A single validator used by every crawl path so URL validation can't be bypassed
by calling a lower-level fetch helper directly. Rejects non-HTTP(S) schemes,
internal service hostnames, IP literals in private/reserved ranges, and hosts
that resolve to them. Keep this validation in place — it is a documented
security watch-out for this repo.

Two modes:

* **Direct** (``resolve=True``): the host is resolved and *every* answer must be
  public. A lookup failure is unsafe, not a pass: the fetcher would resolve the
  name itself, possibly differently, and the guard would have vetted nothing.
  :func:`resolve_host_async` returns the vetted addresses so a fetcher can
  connect to exactly those (``proxy._PinnedBackend``) instead of resolving a
  second time, which is the window a TTL-0 rebinding name uses.
* **Behind a proxy** (``resolve=False``): the target is resolved at the far end
  of Tor or the VPN, so resolving it here would leak every hostname to the
  local resolver and still not be the answer the proxy uses. Only the checks
  that need no lookup apply, and they read a host the way a browser does: a
  legacy IPv4 spelling such as ``0x7f.1`` or ``2130706433`` is 127.0.0.1.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class UnsafeURLError(ValueError):
    """The URL must not be fetched. A ValueError, which every caller already handles."""


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
    "gluetun",
    "tor",
}

# Name suffixes that only ever mean a local or private network. Chromium
# resolves ``*.localhost`` to loopback without asking DNS, and Docker publishes
# the host machine as ``host.docker.internal``.
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa")

_DIGITS = {
    10: frozenset("0123456789"),
    16: frozenset("0123456789abcdefABCDEF"),
    8: frozenset("01234567"),
}


def _is_private_ip(ip_str: str) -> bool:
    """True for any address that is not a public unicast address.

    Checking private/loopback/link-local/reserved one by one missed the CGNAT
    range 100.64.0.0/10 — Alibaba Cloud's metadata service at 100.100.100.200,
    Tailscale nodes, carrier-internal hosts — and multicast. `is_global` is the
    positive statement; multicast and reserved are added because Python counts
    some of those as global.
    """
    try:
        addr = ipaddress.ip_address(ip_str.strip("[]"))
    except ValueError:
        return False
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:  # ::ffff:127.0.0.1 is 127.0.0.1
        addr = mapped
    return not addr.is_global or addr.is_multicast or addr.is_reserved


def _ipv4_number(part: str) -> int | None:
    """One label of an IPv4 host, in decimal, 0x-hex or 0-octal (WHATWG URL rules)."""
    radix = 10
    if part[:2] in ("0x", "0X"):
        part, radix = part[2:], 16
        if not part:
            return 0
    elif len(part) > 1 and part[0] == "0":
        part, radix = part[1:], 8
    if not part or not set(part) <= _DIGITS[radix]:
        return None
    return int(part, radix)


def _legacy_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """The IPv4 address a browser reads `host` as, or None when it is a name.

    A host whose last label is a number is an address to a browser, in any of
    the legacy spellings; one that ends in a number but does not parse is not a
    valid host at all. Mirrors the WHATWG URL standard's IPv4 parser.
    """
    parts = host.split(".")
    last = parts[-1]
    ends_in_number = bool(last) and (set(last) <= _DIGITS[10] or _ipv4_number(last) is not None)
    if not ends_in_number:
        return None
    if len(parts) > 4:
        raise UnsafeURLError("Malformed IPv4 host")
    numbers = [_ipv4_number(p) if p else None for p in parts]
    if any(n is None for n in numbers):
        raise UnsafeURLError("Malformed IPv4 host")
    if any(n > 255 for n in numbers[:-1]) or numbers[-1] >= 256 ** (5 - len(numbers)):
        raise UnsafeURLError("Malformed IPv4 host")
    value = numbers[-1]
    for index, n in enumerate(numbers[:-1]):
        value += n * 256 ** (3 - index)
    return ipaddress.IPv4Address(value)


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if ":" in host:
        try:
            return ipaddress.ip_address(host)
        except ValueError as exc:
            raise UnsafeURLError("Malformed IPv6 host") from exc
    return _legacy_ipv4(host)


def check_host(hostname: str) -> str:
    """Every check that needs no DNS lookup. Returns the normalised host.

    Raises :class:`UnsafeURLError` when the host must not be fetched.
    """
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        raise UnsafeURLError("URL has no hostname")
    if host in _BLOCKED_HOSTNAMES or host.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeURLError("URLs pointing to internal services are not allowed")
    literal = _literal_ip(host)
    if literal is not None:
        if _is_private_ip(str(literal)):
            raise UnsafeURLError("URL points to a private/internal IP address")
        return host
    if "." not in host:
        # A single-label name only means something on a local network — it is
        # how Compose services and intranet hosts are addressed.
        raise UnsafeURLError("Single-label hostnames are not allowed")
    return host


def _url_host(url: str) -> str:
    if "\\" in url:
        # urllib and browsers disagree about a backslash in the authority, so
        # the host checked here would not be the host fetched.
        raise UnsafeURLError("Backslash in URL")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"Unsupported URL scheme: {parsed.scheme}")
    return check_host(parsed.hostname or "")


def _getaddrinfo(host: str) -> list:
    """The one DNS lookup the guard makes (a seam for tests)."""
    return socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)


def _vetted(host: str, infos: list) -> list[str]:
    addresses: list[str] = []
    for _family, _type, _proto, _canonname, sockaddr in infos:
        ip = sockaddr[0]
        if _is_private_ip(ip):
            raise UnsafeURLError("URL resolves to a private/internal IP address")
        if ip not in addresses:
            addresses.append(ip)
    if not addresses:
        raise UnsafeURLError(f"{host} did not resolve to any address")
    return addresses


def resolve_host(host: str) -> list[str]:
    """Static checks, then resolve `host` and return its vetted addresses."""
    host = check_host(host)
    literal = _literal_ip(host)
    if literal is not None:
        return [str(literal)]
    try:
        infos = _getaddrinfo(host)
    except (socket.gaierror, UnicodeError) as exc:
        raise UnsafeURLError(f"{host} could not be resolved") from exc
    return _vetted(host, infos)


async def resolve_host_async(host: str) -> list[str]:
    """:func:`resolve_host` for coroutines: the lookup blocks, so it runs off the loop."""
    host = check_host(host)
    literal = _literal_ip(host)
    if literal is not None:
        return [str(literal)]
    try:
        infos = await asyncio.to_thread(_getaddrinfo, host)
    except (socket.gaierror, UnicodeError) as exc:
        raise UnsafeURLError(f"{host} could not be resolved") from exc
    return _vetted(host, infos)


def validate_url(url: str, *, resolve: bool = True) -> list[str]:
    """SSRF protection: reject non-HTTP schemes, private IPs, and internal hostnames.

    Raises ValueError when the URL is unsafe to fetch. Returns the vetted
    addresses (empty when ``resolve=False``).
    """
    host = _url_host(url)
    return resolve_host(host) if resolve else []


def is_safe_url(url: str) -> bool:
    """Non-raising form of :func:`validate_url` for filtering batches of URLs."""
    try:
        validate_url(url)
        return True
    except ValueError:
        return False


async def validate_url_async(url: str, *, resolve: bool = True) -> list[str]:
    """:func:`validate_url` for coroutines.

    `socket.getaddrinfo` blocks, and the browser's request hook calls this for
    every request a page makes, so resolving inline would stall every other
    request the API is serving.
    """
    host = _url_host(url)
    return await resolve_host_async(host) if resolve else []


async def is_safe_url_async(url: str, *, resolve: bool = True) -> bool:
    """Non-raising form of :func:`validate_url_async`."""
    try:
        await validate_url_async(url, resolve=resolve)
        return True
    except ValueError:
        return False
