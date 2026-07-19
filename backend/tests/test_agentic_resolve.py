"""Tests for search-grounded source resolution (collection/agentic.py)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from intel_platform.collection import agentic


def _src(source_type="web_scrape"):
    return SimpleNamespace(name="Iran nuclear inspections", source_type=source_type, config={})


REAL = [
    {"url": "https://iaea.org/iran", "title": "IAEA Iran", "snippet": "inspections"},
    {"url": "https://reuters.com/world/iran", "title": "Reuters Iran", "snippet": "news"},
    {"url": "https://un.org/sc", "title": "UN SC", "snippet": "resolutions"},
]


async def test_grounded_resolution_filters_hallucinated_urls():
    """The LLM may return a URL not in the search results; it must be dropped."""
    async def fake_gen(provider, messages, system, expected_keys):
        return {"urls": ["https://iaea.org/iran", "https://fabricated.example/x"]}

    with patch("intel_platform.collection.search.web_search", return_value=REAL), \
         patch.object(agentic, "_structured_generate", new=AsyncMock(side_effect=fake_gen)):
        cfg = await agentic._resolve_via_search(None, "Assess Iran nuclear program", _src())

    assert cfg is not None
    # Only the URL that actually appeared in the search results survives.
    assert cfg["urls"] == ["https://iaea.org/iran"]


async def test_grounded_resolution_falls_back_to_top_hits_when_llm_picks_none():
    async def fake_gen(provider, messages, system, expected_keys):
        return {"urls": []}

    with patch("intel_platform.collection.search.web_search", return_value=REAL), \
         patch.object(agentic, "_structured_generate", new=AsyncMock(side_effect=fake_gen)):
        cfg = await agentic._resolve_via_search(None, "pir", _src())

    assert cfg["urls"] == [r["url"] for r in REAL[:3]]


async def test_grounded_resolution_feed_url_must_be_real():
    async def fake_gen(provider, messages, system, expected_keys):
        return {"feed_url": "https://not-in-results.example/feed"}

    with patch("intel_platform.collection.search.web_search", return_value=REAL), \
         patch.object(agentic, "_structured_generate", new=AsyncMock(side_effect=fake_gen)):
        cfg = await agentic._resolve_via_search(None, "pir", _src("rss_feed"))

    # Hallucinated feed_url replaced by the top real result.
    assert cfg["feed_url"] == REAL[0]["url"]
    assert cfg["max_items"] == 20


async def test_grounded_resolution_returns_none_without_search_results():
    with patch("intel_platform.collection.search.web_search", return_value=[]):
        cfg = await agentic._resolve_via_search(None, "pir", _src())
    assert cfg is None
