"""Tests for agentic collection connectors — WebScrape, RSS, API."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from intel_platform.connectors.base import CONNECTOR_REGISTRY


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Connector registration
# ---------------------------------------------------------------------------

class TestConnectorRegistration:
    def test_web_scrape_registered(self):
        # Trigger registration by importing
        from intel_platform.connectors.web_scrape import WebScrapeConnector  # noqa
        assert "web_scrape" in CONNECTOR_REGISTRY

    def test_rss_feed_registered(self):
        from intel_platform.connectors.rss_feed import RSSFeedConnector  # noqa
        assert "rss_feed" in CONNECTOR_REGISTRY

    def test_api_feed_registered(self):
        from intel_platform.connectors.api_feed import APIFeedConnector  # noqa
        assert "api_feed" in CONNECTOR_REGISTRY

    def test_file_upload_still_registered(self):
        from intel_platform.connectors.flat_file import FlatFileConnector  # noqa
        assert "file_upload" in CONNECTOR_REGISTRY


# ---------------------------------------------------------------------------
# WebScrapeConnector
# ---------------------------------------------------------------------------

class TestWebScrapeConnector:
    def test_configure_valid(self):
        from intel_platform.connectors.web_scrape import WebScrapeConnector
        c = WebScrapeConnector()
        config = c.configure({"url": "https://example.com"})
        assert config["url"] == "https://example.com"
        assert config["max_pages"] == 1
        assert config["timeout"] == 30

    def test_configure_rejects_missing_url(self):
        from intel_platform.connectors.web_scrape import WebScrapeConnector
        c = WebScrapeConnector()
        with pytest.raises(ValueError, match="url"):
            c.configure({})

    def test_configure_rejects_non_http(self):
        from intel_platform.connectors.web_scrape import WebScrapeConnector
        c = WebScrapeConnector()
        with pytest.raises(ValueError, match="http"):
            c.configure({"url": "ftp://example.com/file"})

    def test_configure_caps_max_pages(self):
        from intel_platform.connectors.web_scrape import WebScrapeConnector
        c = WebScrapeConnector()
        config = c.configure({"url": "https://example.com", "max_pages": 100})
        assert config["max_pages"] == 50

    def test_acquire_success(self):
        from intel_platform.connectors.web_scrape import WebScrapeConnector
        c = WebScrapeConnector()

        mock_result = {"url": "https://example.com", "title": "Example", "content": "Hello world", "content_length": 11}

        with patch("intel_platform.connectors.web_scrape.WebScraper") as MockScraper:
            instance = MockScraper.return_value
            instance.scrape_url = AsyncMock(return_value=mock_result)

            result = run(c.acquire({"url": "https://example.com", "timeout": 10}))

        assert result.success
        assert result.record_count == 1
        assert result.records[0]["title"] == "Example"
        assert result.records[0]["content"] == "Hello world"
        assert result.records[0]["url"] == "https://example.com"

    def test_acquire_failure(self):
        from intel_platform.connectors.web_scrape import WebScrapeConnector
        c = WebScrapeConnector()

        with patch("intel_platform.connectors.web_scrape.WebScraper") as MockScraper:
            instance = MockScraper.return_value
            instance.scrape_url = AsyncMock(side_effect=RuntimeError("Connection refused"))

            result = run(c.acquire({"url": "https://unreachable.example.com"}))

        assert not result.success
        assert "Connection refused" in result.error

    def test_acquire_no_url(self):
        from intel_platform.connectors.web_scrape import WebScrapeConnector
        c = WebScrapeConnector()
        result = run(c.acquire({}))
        assert not result.success


# ---------------------------------------------------------------------------
# RSSFeedConnector
# ---------------------------------------------------------------------------

class TestRSSFeedConnector:
    def test_configure_valid(self):
        from intel_platform.connectors.rss_feed import RSSFeedConnector
        c = RSSFeedConnector()
        config = c.configure({"feed_url": "https://feeds.example.com/rss"})
        assert config["feed_url"] == "https://feeds.example.com/rss"
        assert config["max_items"] == 50
        assert config["fetch_full_content"] is False

    def test_configure_rejects_missing_url(self):
        from intel_platform.connectors.rss_feed import RSSFeedConnector
        c = RSSFeedConnector()
        with pytest.raises(ValueError, match="feed_url"):
            c.configure({})

    def test_configure_caps_max_items(self):
        from intel_platform.connectors.rss_feed import RSSFeedConnector
        c = RSSFeedConnector()
        config = c.configure({"feed_url": "https://x.com/feed", "max_items": 1000})
        assert config["max_items"] == 500

    def test_acquire_parses_feed(self):
        """Test feed parsing with mocked feedparser."""
        from intel_platform.connectors.rss_feed import RSSFeedConnector
        c = RSSFeedConnector()

        # Mock feedparser module
        mock_entry_1 = MagicMock()
        mock_entry_1.title = "Article 1"
        mock_entry_1.link = "https://example.com/1"
        mock_entry_1.summary = "First article content"
        mock_entry_1.published_parsed = None
        mock_entry_1.content = []

        mock_entry_2 = MagicMock()
        mock_entry_2.title = "Article 2"
        mock_entry_2.link = "https://example.com/2"
        mock_entry_2.summary = "Second article content"
        mock_entry_2.published_parsed = None
        mock_entry_2.content = []

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [mock_entry_1, mock_entry_2]
        mock_feed.feed.title = "Test Feed"

        mock_feedparser = MagicMock()
        mock_feedparser.parse.return_value = mock_feed

        with patch("intel_platform.connectors.rss_feed.ProxiedClient") as MockClient, \
             patch.dict("sys.modules", {"feedparser": mock_feedparser}):
            instance = MockClient.return_value
            instance.fetch_text = AsyncMock(return_value="<rss>mock</rss>")

            result = run(c.acquire({"feed_url": "https://feeds.example.com/rss"}))

        assert result.success
        assert result.record_count == 2
        assert result.records[0]["title"] == "Article 1"
        assert result.records[0]["content"] == "First article content"

    def test_acquire_no_feed_url(self):
        from intel_platform.connectors.rss_feed import RSSFeedConnector
        c = RSSFeedConnector()
        result = run(c.acquire({}))
        assert not result.success

    def test_acquire_without_feedparser_installed(self):
        """When feedparser isn't installed, acquire should return a clear error."""
        from intel_platform.connectors.rss_feed import RSSFeedConnector
        c = RSSFeedConnector()
        with patch.dict("sys.modules", {"feedparser": None}):
            result = run(c.acquire({"feed_url": "https://feeds.example.com/rss"}))
        # Should fail gracefully with a message about feedparser
        assert not result.success
        assert "feedparser" in result.error.lower()


# ---------------------------------------------------------------------------
# APIFeedConnector
# ---------------------------------------------------------------------------

class TestAPIFeedConnector:
    def test_configure_valid(self):
        from intel_platform.connectors.api_feed import APIFeedConnector
        c = APIFeedConnector()
        config = c.configure({
            "base_url": "https://api.example.com",
            "endpoint": "v1/data",
            "auth_type": "bearer",
            "auth_value": "token123",
        })
        assert config["base_url"] == "https://api.example.com"
        assert config["endpoint"] == "v1/data"
        assert config["auth_type"] == "bearer"

    def test_configure_rejects_missing_url(self):
        from intel_platform.connectors.api_feed import APIFeedConnector
        c = APIFeedConnector()
        with pytest.raises(ValueError, match="base_url"):
            c.configure({})

    def test_configure_rejects_invalid_auth(self):
        from intel_platform.connectors.api_feed import APIFeedConnector
        c = APIFeedConnector()
        with pytest.raises(ValueError, match="auth_type"):
            c.configure({"base_url": "https://api.example.com", "auth_type": "oauth"})

    def test_acquire_json_response(self):
        from intel_platform.connectors.api_feed import APIFeedConnector
        c = APIFeedConnector()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"name": "Entity A"}, {"name": "Entity B"}]}
        mock_resp.raise_for_status = MagicMock()

        with patch("intel_platform.connectors.api_feed.ProxiedClient") as MockClient:
            instance = MockClient.return_value
            instance.get = AsyncMock(return_value=mock_resp)

            result = run(c.acquire({
                "base_url": "https://api.example.com",
                "endpoint": "v1/entities",
                "response_path": "data",
            }))

        assert result.success
        assert result.record_count == 2
        assert result.records[0]["name"] == "Entity A"

    def test_navigate_path(self):
        from intel_platform.connectors.api_feed import APIFeedConnector
        data = {"a": {"b": {"c": [1, 2, 3]}}}
        assert APIFeedConnector._navigate_path(data, "a.b.c") == [1, 2, 3]
        assert APIFeedConnector._navigate_path(data, "a.b") == {"c": [1, 2, 3]}
        assert APIFeedConnector._navigate_path(data, "") == data

    def test_build_headers_bearer(self):
        from intel_platform.connectors.api_feed import APIFeedConnector
        headers = APIFeedConnector._build_headers({
            "auth_type": "bearer", "auth_value": "mytoken", "headers": {},
        })
        assert headers["Authorization"] == "Bearer mytoken"
        assert headers["Accept"] == "application/json"

    def test_build_headers_api_key(self):
        from intel_platform.connectors.api_feed import APIFeedConnector
        headers = APIFeedConnector._build_headers({
            "auth_type": "api_key", "auth_value": "key123", "headers": {},
        })
        assert headers["X-API-Key"] == "key123"

    def test_acquire_no_url(self):
        from intel_platform.connectors.api_feed import APIFeedConnector
        c = APIFeedConnector()
        result = run(c.acquire({}))
        assert not result.success


# ---------------------------------------------------------------------------
# Plan source parsing with configs
# ---------------------------------------------------------------------------

class TestParsePlanSourcesWithConfig:
    def test_structured_with_config(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        text = '''1. [web_scrape] CISA cybersecurity advisories
   CONFIG: {"url": "https://www.cisa.gov/advisories"}
2. [rss_feed] Reuters world news
   CONFIG: {"feed_url": "https://feeds.reuters.com/reuters/worldNews"}
3. [api_feed] VirusTotal threat data
   CONFIG: {"base_url": "https://www.virustotal.com/api/v3", "auth_type": "api_key"}'''

        sources = parse_plan_sources(text)
        assert len(sources) == 3

        assert sources[0]["source_type"] == "web_scrape"
        assert sources[0]["config"]["url"] == "https://www.cisa.gov/advisories"

        assert sources[1]["source_type"] == "rss_feed"
        assert sources[1]["config"]["feed_url"] == "https://feeds.reuters.com/reuters/worldNews"

        assert sources[2]["source_type"] == "api_feed"
        assert sources[2]["config"]["base_url"] == "https://www.virustotal.com/api/v3"

    def test_url_in_description_auto_config(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        text = "1. Scrape threat data from https://www.cisa.gov/advisories for latest advisories"
        sources = parse_plan_sources(text)
        assert len(sources) == 1
        assert sources[0]["config"].get("url") == "https://www.cisa.gov/advisories"

    def test_no_config_produces_empty(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        text = "1. [web_scrape] Some website without a URL"
        sources = parse_plan_sources(text)
        assert sources[0]["config"] == {}


# ---------------------------------------------------------------------------
# PlanExecutor helpers
# ---------------------------------------------------------------------------

class TestPlanExecutorHelpers:
    def test_has_valid_config(self):
        from intel_platform.services.plan_executor import _has_valid_config
        assert _has_valid_config("web_scrape", {"url": "https://example.com"})
        assert not _has_valid_config("web_scrape", {})
        assert _has_valid_config("rss_feed", {"feed_url": "https://feeds.example.com"})
        assert not _has_valid_config("rss_feed", {})
        assert _has_valid_config("api_feed", {"base_url": "https://api.example.com"})
        assert not _has_valid_config("api_feed", {})
        assert _has_valid_config("file_upload", {})

    def test_records_to_text_web_content(self):
        from intel_platform.services.plan_executor import _records_to_text
        source = MagicMock()
        source.source_type = "web_scrape"

        records = [
            {"title": "Article", "url": "https://example.com", "content": "This is the article text."},
        ]
        text = _records_to_text(records, source)
        assert "Article" in text
        assert "This is the article text" in text
        assert "https://example.com" in text

    def test_records_to_text_structured(self):
        from intel_platform.services.plan_executor import _records_to_text
        source = MagicMock()
        source.source_type = "api_feed"

        records = [{"name": "Entity A", "type": "Organization", "country": "US"}]
        text = _records_to_text(records, source)
        assert "name: Entity A" in text
        assert "type: Organization" in text

    def test_records_to_text_skips_internal_fields(self):
        from intel_platform.services.plan_executor import _records_to_text
        source = MagicMock()
        records = [{"name": "Test", "_source_url": "internal", "_acquired_at": "2024-01-01"}]
        text = _records_to_text(records, source)
        assert "_source_url" not in text
        assert "name: Test" in text

    def test_execution_status_tracking(self):
        from intel_platform.services.plan_executor import _running_executions, get_execution_status
        # Initially empty
        assert get_execution_status("nonexistent") is None

        # Simulate setting status
        _running_executions["test-plan"] = {"status": "running", "progress": 0.5}
        status = get_execution_status("test-plan")
        assert status["status"] == "running"
        assert status["progress"] == 0.5

        # Clean up
        del _running_executions["test-plan"]
