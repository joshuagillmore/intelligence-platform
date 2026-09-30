"""Tests for search-grounded source resolution (collection/agentic.py)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from intel_platform.collection import agentic
from intel_platform.collection.proxy import ProxyConfig


@pytest.fixture(autouse=True)
def direct_mode(monkeypatch):
    """Pin the proxy mode: reading it from an absent Postgres cost 60 s a test."""
    async def _direct():
        return ProxyConfig(mode="direct")

    monkeypatch.setattr("intel_platform.collection.proxy.get_active_proxy_config", _direct)


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
        cfg = await agentic._resolve_via_search(None, "pir", _src("rss_feed"), max_results=7)

    # Hallucinated feed_url replaced by the top real result.
    assert cfg["feed_url"] == REAL[0]["url"]
    assert cfg["max_items"] == 7  # threaded through from max_results


async def test_grounded_resolution_returns_none_without_search_results():
    with patch("intel_platform.collection.search.web_search", return_value=[]):
        cfg = await agentic._resolve_via_search(None, "pir", _src())
    assert cfg is None


class _Db:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass


def _model_that_follows_the_prompt(reply: dict):
    """A _structured_generate stand-in that behaves like the real one: the model
    answers in the shape the prompt asked for, and the call fails when that
    shape lacks a key the caller requires."""
    async def fake(provider, messages, system, expected_keys=None, max_retries=3):
        if expected_keys and any(k not in reply for k in expected_keys):
            return None
        return dict(reply)

    return fake


async def test_api_feed_resolution_accepts_the_shape_its_prompt_asks_for():
    """RESOLVE_SYSTEM asks an api_feed for {"base_url": ...}; the parser required
    "urls", so every LLM-resolved api_feed failed three times and was dropped."""
    source = SimpleNamespace(
        id="s1", name="Sanctions API", source_type="api_feed", config={},
        collection_status="pending", last_error="",
    )
    plan = SimpleNamespace(id="p1", refined_pir="", pir="Who is sanctioned?", requirement="")

    async def no_search(*a, **kw):
        return None

    reply = {"base_url": "https://api.example.org", "endpoint": "v1/sanctions", "response_path": "data"}
    with patch.object(agentic, "_resolve_via_search", new=no_search), \
         patch.object(agentic, "_structured_generate", new=_model_that_follows_the_prompt(reply)):
        await agentic.resolve_sources(plan, [source], _Db(), provider=None)

    assert source.collection_status == "queued", source.last_error
    assert source.config["base_url"] == "https://api.example.org"


async def test_api_feed_base_url_is_filtered_like_any_other_url():
    source = SimpleNamespace(
        id="s1", name="Internal API", source_type="api_feed", config={},
        collection_status="pending", last_error="",
    )
    plan = SimpleNamespace(id="p1", refined_pir="", pir="x", requirement="")

    async def no_search(*a, **kw):
        return None

    reply = {"base_url": "http://169.254.169.254/latest", "endpoint": ""}
    with patch.object(agentic, "_resolve_via_search", new=no_search), \
         patch.object(agentic, "_structured_generate", new=_model_that_follows_the_prompt(reply)):
        await agentic.resolve_sources(plan, [source], _Db(), provider=None)

    assert source.config.get("base_url", "") == ""


def test_validate_urls_rejects_all_private_ranges():
    """SSRF defense-in-depth: every private/loopback/link-local range is filtered,
    including 172.16/12 (which the old string-prefix check missed)."""
    blocked = [
        "http://10.0.0.5/x", "http://192.168.1.1/x", "http://169.254.1.1/x",
        "http://172.16.0.1/x", "http://172.20.10.5/x", "http://172.31.255.1/x",
        "http://127.0.0.1/x", "http://localhost/x", "http://0.0.0.0/x",
        "ftp://example.com/x",  # non-http scheme
    ]
    allowed = ["https://reuters.com/world", "http://iaea.org/iran", "https://8.8.8.8/x"]
    out = agentic._validate_urls(blocked + allowed)
    assert set(out) == set(allowed), f"unexpected: {out}"
    # 172.16/12 specifically must not survive
    assert not any("172." in u for u in out)
