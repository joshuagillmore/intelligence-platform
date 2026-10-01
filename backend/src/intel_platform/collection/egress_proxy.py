"""A pinned local egress proxy for the headless browser.

Chromium resolves hostnames itself, so the SSRF guard's lookup and the
browser's could disagree: a TTL-0 rebinding name answers the guard with a
public address and Chromium with 127.0.0.1, and the in-browser checks in
``crawler._BrowserGuard`` can only reject the page afterwards — page JavaScript
may already have read the response. The httpx path closed the same window by
connecting to the address it vetted (``proxy._PinnedBackend``). This does the
same for Chromium: the crawler starts one of these per crawl and passes it to
the browser as ``--proxy-server``, so every request the browser makes arrives
here first.

For each request (``CONNECT host:port`` for HTTPS and WebSockets, an
absolute-form ``GET http://...`` for plain HTTP):

* **Direct** (no upstream): the host is resolved **once**, through
  ``url_guard.resolve_host_async`` (static checks, one lookup, every answer
  public), and the connection is made to one of exactly those addresses. A
  second lookup never happens, so a rebinding answer has nowhere to land. A
  refused target gets ``403``.
* **Chained** (Tor or VPN selected): the target is not resolved here at all —
  that would leak the hostname to the local resolver and still not be the
  answer the far end uses. Only the lookup-free checks apply
  (``url_guard.check_host``: internal names, private literals), then the
  request is handed to the upstream proxy: SOCKS5 with the hostname (remote
  DNS, ``socks5h``) for Tor, HTTP ``CONNECT`` (or absolute-form forwarding for
  plain HTTP) for the VPN's HTTP proxy.

It listens on ``127.0.0.1`` on an ephemeral port and lives only as long as the
crawl that started it.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import ipaddress
import logging
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from intel_platform.collection import url_guard

logger = logging.getLogger(__name__)

# Request heads larger than this are refused (431).
_HEAD_LIMIT = 64 * 1024
_CHUNK = 64 * 1024

# Headers that describe the hop to this proxy, never forwarded.
_HOP_HEADERS = frozenset({
    "proxy-connection", "proxy-authorization", "connection", "keep-alive", "te", "trailer", "upgrade",
})


class _Reply(Exception):
    """End the exchange by answering the client with this status."""

    def __init__(self, status: int, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.status, self.reason, self.detail = status, reason, detail


@dataclass(frozen=True)
class Upstream:
    """The Tor/VPN proxy chained to instead of resolving locally."""

    kind: str          # "socks5" | "http"
    host: str
    port: int
    username: str = ""
    password: str = ""

    @classmethod
    def parse(cls, url: str) -> "Upstream":
        parts = urlsplit(url)
        scheme = (parts.scheme or "").lower()
        if scheme in ("socks5", "socks5h"):
            kind, default_port = "socks5", 1080
        elif scheme == "http":
            kind, default_port = "http", 8080
        else:
            raise ValueError(f"Unsupported upstream proxy scheme: {scheme or '(none)'}")
        if not parts.hostname:
            raise ValueError("Upstream proxy URL has no host")
        return cls(
            kind=kind, host=parts.hostname, port=parts.port or default_port,
            username=unquote(parts.username or ""), password=unquote(parts.password or ""),
        )


def _authority(host: str, port: int) -> str:
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def _split_authority(authority: str) -> tuple[str, int]:
    """``host:port`` (``[v6]:port``) from a CONNECT target."""
    try:
        parts = urlsplit("//" + authority)
        host, port = parts.hostname, parts.port
    except ValueError as exc:
        raise _Reply(400, "Bad Request", "malformed CONNECT target") from exc
    if not host or not port:
        raise _Reply(400, "Bad Request", "CONNECT needs host:port")
    return host, port


def _parse_head(head: bytes) -> tuple[str, str, str, list[tuple[str, str]]]:
    text = head.decode("latin-1")
    lines = text.split("\r\n")
    request = lines[0].split(" ")
    if len(request) != 3 or not request[2].startswith("HTTP/"):
        raise _Reply(400, "Bad Request", "malformed request line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        name, sep, value = line.partition(":")
        if not sep or not name.strip():
            raise _Reply(400, "Bad Request", "malformed header")
        headers.append((name.strip(), value.strip()))
    method, target, version = request
    return method.upper(), target, version, headers


def _forward_head(start_line: str, headers: list[tuple[str, str]], extra: list[tuple[str, str]] = ()) -> bytes:
    """A request head with hop-by-hop headers dropped and ``Connection: close``.

    One request per upstream connection: the next request on the client's
    connection may be for a different host, which must be resolved and vetted
    on its own.
    """
    lines = [start_line]
    lines += [f"{n}: {v}" for n, v in headers if n.lower() not in _HOP_HEADERS]
    lines += [f"{n}: {v}" for n, v in extra]
    lines.append("Connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")


async def _close(writer) -> None:
    with contextlib.suppress(Exception):
        writer.close()
        await writer.wait_closed()


async def _discard(reader: asyncio.StreamReader) -> None:
    with contextlib.suppress(Exception):
        while await reader.read(_CHUNK):
            pass


async def _pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await src.read(_CHUNK)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except (ConnectionError, OSError, asyncio.IncompleteReadError):
        pass
    finally:
        with contextlib.suppress(Exception):
            if dst.can_write_eof():
                dst.write_eof()


async def _relay(client_r, client_w, upstream_r, upstream_w) -> None:
    """Bytes both ways until the upstream side is done (or the client goes)."""
    up = asyncio.ensure_future(_pump(client_r, upstream_w))
    down = asyncio.ensure_future(_pump(upstream_r, client_w))
    try:
        done, _pending = await asyncio.wait({up, down}, return_when=asyncio.FIRST_COMPLETED)
        if up in done and not down.done():
            # The client finished sending (half-close); the response may still be coming.
            await down
    finally:
        for task in (up, down):
            task.cancel()
        await asyncio.gather(up, down, return_exceptions=True)


async def _socks5_connect(reader, writer, host: str, port: int, username: str, password: str) -> None:
    """RFC 1928 CONNECT, sending the hostname so the far end resolves it."""
    methods = b"\x00\x02" if username else b"\x00"
    writer.write(b"\x05" + bytes([len(methods)]) + methods)
    await writer.drain()
    version, method = await reader.readexactly(2)
    if version != 5:
        raise _Reply(502, "Bad Gateway", "upstream is not a SOCKS5 proxy")
    if method == 0x02:
        user, pw = username.encode(), password.encode()
        writer.write(b"\x01" + bytes([len(user)]) + user + bytes([len(pw)]) + pw)
        await writer.drain()
        if (await reader.readexactly(2))[1] != 0:
            raise _Reply(502, "Bad Gateway", "upstream proxy refused the credentials")
    elif method != 0x00:
        raise _Reply(502, "Bad Gateway", "upstream proxy offered no usable auth method")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            name = host.encode("idna")
        except UnicodeError as exc:
            raise _Reply(400, "Bad Request", "unencodable host name") from exc
        if not 0 < len(name) < 256:
            raise _Reply(400, "Bad Request", "host name too long")
        address = b"\x03" + bytes([len(name)]) + name
    else:
        address = (b"\x01" if literal.version == 4 else b"\x04") + literal.packed
    writer.write(b"\x05\x01\x00" + address + port.to_bytes(2, "big"))
    await writer.drain()
    _ver, reply, _rsv, atyp = await reader.readexactly(4)
    if reply != 0:
        raise _Reply(502, "Bad Gateway", f"upstream proxy could not connect (SOCKS reply {reply})")
    if atyp == 1:
        await reader.readexactly(4 + 2)
    elif atyp == 4:
        await reader.readexactly(16 + 2)
    elif atyp == 3:
        await reader.readexactly((await reader.readexactly(1))[0] + 2)
    else:
        raise _Reply(502, "Bad Gateway", "malformed SOCKS reply")


async def _http_connect(reader, writer, host: str, port: int, auth: list[tuple[str, str]]) -> None:
    authority = _authority(host, port)
    lines = [f"CONNECT {authority} HTTP/1.1", f"Host: {authority}"] + [f"{n}: {v}" for n, v in auth]
    writer.write(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
    await writer.drain()
    head = await reader.readuntil(b"\r\n\r\n")
    status = head.split(b" ", 2)[1] if head.count(b" ") >= 1 else b""
    if status != b"200":
        raise _Reply(502, "Bad Gateway", f"upstream proxy answered CONNECT with {status.decode('latin-1')[:3]}")


class EgressProxy:
    """A local CONNECT/HTTP forward proxy that vets and pins every target.

    ``upstream``: the Tor/VPN proxy URL to chain to, or None to go direct.
    ``open_connection`` is the socket seam (tests point it at local servers);
    it is only ever called with a vetted IP address or the upstream proxy.
    """

    def __init__(self, upstream: str | None = None, *, connect_timeout: float = 15.0,
                 head_timeout: float = 15.0, open_connection=None):
        self.upstream = Upstream.parse(upstream) if upstream else None
        self._connect_timeout = connect_timeout
        self._head_timeout = head_timeout
        self._open = open_connection or asyncio.open_connection
        self._server: asyncio.base_events.Server | None = None
        self._tasks: set[asyncio.Task] = set()
        self.port: int | None = None
        # (target, reason) for every request refused, for the crawl's logs.
        self.refused: list[tuple[str, str]] = []

    @property
    def url(self) -> str:
        if self.port is None:
            raise RuntimeError("egress proxy is not started")
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> "EgressProxy":
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0, limit=_HEAD_LIMIT)
        self.port = self._server.sockets[0].getsockname()[1]
        logger.debug("Egress proxy on 127.0.0.1:%d (%s)", self.port,
                     f"via {self.upstream.kind} upstream" if self.upstream else "direct, pinned")
        return self

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._server is not None:
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def __aenter__(self) -> "EgressProxy":
        return await self.start()

    async def __aexit__(self, *exc) -> None:
        await self.close()

    # -- one client connection --------------------------------------------

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        self._tasks.add(task)
        try:
            await self._serve(reader, writer)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.debug("Egress proxy connection failed", exc_info=True)
        finally:
            await _close(writer)
            self._tasks.discard(task)

    async def _serve(self, reader, writer) -> None:
        try:
            try:
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), self._head_timeout)
            except asyncio.LimitOverrunError as exc:
                raise _Reply(431, "Request Header Fields Too Large") from exc
            except (asyncio.IncompleteReadError, ConnectionError):
                return
            except asyncio.TimeoutError as exc:
                raise _Reply(408, "Request Timeout") from exc
            method, target, version, headers = _parse_head(head)
            if method == "CONNECT":
                host, port = _split_authority(target)
                upstream_r, upstream_w = await self._dial(host, port, f"CONNECT {_authority(host, port)}")
                try:
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    await _relay(reader, writer, upstream_r, upstream_w)
                finally:
                    await _close(upstream_w)
            else:
                await self._forward(reader, writer, method, target, version, headers)
        except _Reply as reply:
            with contextlib.suppress(Exception):
                body = f"{reply.reason}\n".encode()
                writer.write(
                    f"HTTP/1.1 {reply.status} {reply.reason}\r\nContent-Type: text/plain\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
                )
                await writer.drain()
                # Lingering close: closing with unread request bytes makes the
                # OS send a reset, which can destroy the reply before the
                # browser reads it. Half-close, then discard briefly.
                if writer.can_write_eof():
                    writer.write_eof()
                await asyncio.wait_for(_discard(reader), 0.5)

    async def _forward(self, reader, writer, method, target, version, headers) -> None:
        """Plain HTTP: an absolute-form request, re-sent towards the vetted origin."""
        try:
            url_guard.validate_url(target, resolve=False)
        except ValueError as exc:
            self._refuse(f"{method} {target[:200]}", str(exc))
            raise _Reply(403, "Forbidden", str(exc)) from exc
        parts = urlsplit(target)
        if parts.scheme != "http":
            raise _Reply(400, "Bad Request", "only http:// is forwarded; use CONNECT for https")
        host, port = parts.hostname, parts.port or 80
        if self.upstream is not None and self.upstream.kind == "http":
            # The VPN's HTTP proxy takes the absolute form as it is.
            upstream_r, upstream_w = await self._open_upstream()
            start = f"{method} {target} {version}"
            extra = self._upstream_auth()
        else:
            upstream_r, upstream_w = await self._dial(host, port, f"{method} {target[:200]}")
            path = parts.path or "/"
            start = f"{method} {path}{'?' + parts.query if parts.query else ''} {version}"
            extra = []
        try:
            upstream_w.write(_forward_head(start, headers, extra))
            await upstream_w.drain()
            await _relay(reader, writer, upstream_r, upstream_w)
        finally:
            await _close(upstream_w)

    # -- reaching the target ----------------------------------------------

    def _refuse(self, target: str, reason: str) -> None:
        self.refused.append((target, reason))
        logger.warning("Egress proxy refused %s: %s", target, reason)

    async def _dial(self, host: str, port: int, label: str):
        """A connection on which ``host:port`` is reachable: pinned direct, or through the upstream."""
        try:
            if self.upstream is None:
                # The one lookup: static checks, then every answer must be public.
                addresses = await url_guard.resolve_host_async(host)
            else:
                # Resolved at the far end; locally only the lookup-free checks.
                url_guard.check_host(host)
                addresses = None
        except ValueError as exc:
            self._refuse(label, str(exc))
            raise _Reply(403, "Forbidden", str(exc)) from exc

        if addresses is not None:
            last: Exception | None = None
            for address in addresses:
                try:
                    return await asyncio.wait_for(self._open(address, port), self._connect_timeout)
                except (OSError, asyncio.TimeoutError) as exc:
                    last = exc
            raise _Reply(502, "Bad Gateway", f"could not connect to {host}") from last

        reader, writer = await self._open_upstream()
        try:
            if self.upstream.kind == "socks5":
                await asyncio.wait_for(
                    _socks5_connect(reader, writer, host, port, self.upstream.username, self.upstream.password),
                    self._connect_timeout,
                )
            else:
                await asyncio.wait_for(
                    _http_connect(reader, writer, host, port, self._upstream_auth()), self._connect_timeout,
                )
        except _Reply:
            await _close(writer)
            raise
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
            await _close(writer)
            raise _Reply(502, "Bad Gateway", "upstream proxy handshake failed") from exc
        return reader, writer

    async def _open_upstream(self):
        up = self.upstream
        try:
            return await asyncio.wait_for(self._open(up.host, up.port), self._connect_timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            # Fail closed: never fall back to direct when Tor/VPN was chosen.
            raise _Reply(502, "Bad Gateway", "upstream proxy unreachable") from exc

    def _upstream_auth(self) -> list[tuple[str, str]]:
        up = self.upstream
        if up is None or up.kind != "http" or not up.username:
            return []
        token = base64.b64encode(f"{up.username}:{up.password}".encode()).decode()
        return [("Proxy-Authorization", f"Basic {token}")]
