from __future__ import annotations

import logging
from ddgs import DDGS

logger = logging.getLogger(__name__)


def web_search(query: str, max_results: int = 10) -> list[dict]:
    """Search the web via DuckDuckGo and return structured results."""
    max_results = min(max(1, max_results), 20)
    try:
        with DDGS() as ddgs:
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
