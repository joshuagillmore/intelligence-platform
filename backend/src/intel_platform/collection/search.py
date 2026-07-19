from __future__ import annotations

import logging
from ddgs import DDGS

logger = logging.getLogger(__name__)


def web_search(query: str, max_results: int = 10, proxy: str | None = None) -> list[dict]:
    """Search the web via DuckDuckGo and return structured results.

    `proxy` optionally routes the search egress through the active collection
    proxy (VPN/Tor). web_search runs synchronously (in a thread), so async
    callers resolve the proxy via get_active_proxy_config().get_proxy_url()
    and pass it in. None = direct.
    """
    max_results = min(max(1, max_results), 20)
    try:
        with DDGS(proxy=proxy, timeout=10) as ddgs:
            raw = ddgs.text(query, max_results=max_results)
            return [
                {
                    "url": r.get("href", ""),
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw
                if r.get("href")
            ]
    except Exception:
        logger.exception("DuckDuckGo search failed for query: %s", query)
        return []
