from __future__ import annotations

import logging
import time

from ddgs import DDGS

from intel_platform.config import settings

logger = logging.getLogger(__name__)

try:  # ddgs raises a dedicated error for throttling; tolerate older builds
    from ddgs.exceptions import RatelimitException
except Exception:  # pragma: no cover - depends on the installed ddgs build
    class RatelimitException(Exception):
        pass


_DEFAULT_BACKENDS = ("auto", "brave", "bing", "duckduckgo")
_RETRIES_PER_BACKEND = 2


def _backends() -> list[str]:
    configured = [b.strip() for b in (settings.search_backends or "").split(",") if b.strip()]
    return configured or list(_DEFAULT_BACKENDS)


def web_search(query: str, max_results: int = 10, proxy: str | None = None) -> list[dict]:
    """Search the web and return structured results, trying engines in order.

    `ddgs` fronts several engines and they fail independently: the duckduckgo
    backend in particular answers "no results" under light load for queries
    brave and bing serve in under a second. A single-engine search therefore
    reports "nothing found" for questions the web can plainly answer, and a
    collection run starves without ever showing an error — the run just
    acquires nothing and reports success. Measured across a 15-run campaign on
    this stack: 41 source failures against 27 successes, most of them sources
    that could never have resolved.

    The first engine to return anything wins. [] means every engine either
    failed or genuinely had nothing.

    `proxy` optionally routes the search egress through the active collection
    proxy (VPN/Tor). web_search runs synchronously (in a thread), so async
    callers resolve the proxy via get_active_proxy_config().get_proxy_url()
    and pass it in. None = direct.
    """
    max_results = min(max(1, max_results), 20)
    backends = _backends()
    last_error: Exception | None = None

    for backend in backends:
        for attempt in range(_RETRIES_PER_BACKEND):
            try:
                with DDGS(proxy=proxy, timeout=10) as ddgs:
                    raw = list(ddgs.text(query, max_results=max_results, backend=backend))
            except RatelimitException as exc:
                # Throttling is transient and engine-specific: back off briefly,
                # then give up on this engine rather than the whole search.
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
                continue
            except Exception as exc:
                last_error = exc
                logger.debug("Search backend %s failed for %r", backend, query[:80], exc_info=True)
                break

            results = [
                {
                    "url": r.get("href") or r.get("url") or "",
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw
            ]
            results = [r for r in results if r["url"]]
            if results:
                if backend != backends[0]:
                    # Worth a log line: a run whose sources all came from a
                    # fallback engine is one where the primary is degraded.
                    logger.info(
                        "Search for %r served by fallback backend %r (%d results)",
                        query[:80], backend, len(results),
                    )
                return results
            break  # the engine answered, with nothing — try the next one

    logger.warning(
        "No search results for %r from any of %s (%s)",
        query[:80], backends,
        type(last_error).__name__ if last_error else "all empty",
    )
    return []
