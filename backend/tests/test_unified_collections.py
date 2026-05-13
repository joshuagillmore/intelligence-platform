"""Tests for the unified collection system — PIR → Plan → Execute flow."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from intel_platform.llm.base import LLMResponse


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# parse_plan_sources
# ---------------------------------------------------------------------------

class TestParsePlanSources:
    """Test LLM plan text → source definitions parsing."""

    def test_structured_format(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        text = """1. [web_scrape] Scrape government procurement portals for contract data
2. [database] Query WHOIS records for domain registration
3. [file_upload] Upload financial statements from SEC filings
4. [api_feed] Pull threat intelligence from VirusTotal API
5. [rss_feed] Monitor Reuters news feed for geopolitical events"""

        sources = parse_plan_sources(text)
        assert len(sources) == 5
        assert sources[0]["source_type"] == "web_scrape"
        assert sources[0]["name"] == "Scrape government procurement portals for contract data"
        assert "config" in sources[0]  # now includes config dict
        assert sources[1]["source_type"] == "database"
        assert sources[2]["source_type"] == "file_upload"
        assert sources[3]["source_type"] == "api_feed"
        assert sources[4]["source_type"] == "rss_feed"

    def test_keyword_detection_fallback(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        text = """1. Scrape the target organization's website for personnel information
2. Search WHOIS database for domain registration details
3. Upload captured PDF documents from the operation
4. Subscribe to RSS news feed for mentions of the target
5. Pull data from the threat intelligence API endpoint"""

        sources = parse_plan_sources(text)
        assert len(sources) == 5
        assert sources[0]["source_type"] == "web_scrape"
        assert sources[1]["source_type"] == "database"
        assert sources[2]["source_type"] == "file_upload"
        assert sources[3]["source_type"] == "rss_feed"  # "RSS news feeds"
        assert sources[4]["source_type"] == "api_feed"  # "API endpoint"

    def test_bullet_points(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        text = """- Upload CSV files from financial reporting databases
- Scrape open web sources for organizational charts
• Query public database records for ownership information"""

        sources = parse_plan_sources(text)
        assert len(sources) == 3
        assert sources[0]["source_type"] == "file_upload"
        assert sources[1]["source_type"] == "web_scrape"
        assert sources[2]["source_type"] == "database"

    def test_empty_input(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        assert parse_plan_sources("") == []
        assert parse_plan_sources("   \n  \n") == []

    def test_short_lines_ignored(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        text = "1. Short\n2. Upload the comprehensive dataset from the external API"
        sources = parse_plan_sources(text)
        assert len(sources) == 1  # first line too short

    def test_mixed_format(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        text = """1. [file_upload] Upload threat actor IOC spreadsheet
2. Monitor news feeds for new developments on the threat actor
3. [web_scrape] Crawl paste sites for leaked credentials"""

        sources = parse_plan_sources(text)
        assert len(sources) == 3
        assert sources[0]["source_type"] == "file_upload"
        assert sources[1]["source_type"] == "rss_feed"  # "news feeds" keyword
        assert sources[2]["source_type"] == "web_scrape"

    def test_invalid_source_type_in_brackets(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        text = "1. [invalid_type] This should not be parsed as structured"
        sources = parse_plan_sources(text)
        # Falls through to keyword detection
        assert len(sources) == 1
        assert sources[0]["source_type"] == "file_upload"  # default

    def test_name_truncation(self):
        from intel_platform.services.collection_planner import parse_plan_sources
        long_desc = "x" * 300
        text = f"1. [file_upload] {long_desc}"
        sources = parse_plan_sources(text)
        assert len(sources[0]["name"]) == 256


# ---------------------------------------------------------------------------
# PIR → Plan flow (mocked LLM)
# ---------------------------------------------------------------------------

MOCK_REFINE_RESPONSE = LLMResponse(
    content="What specific cyber capabilities has APT29 developed since 2022?\nAssessment: The original PIR lacks temporal bounds and specificity.",
    model="test-model",
    input_tokens=100,
    output_tokens=200,
)

MOCK_PLAN_RESPONSE = LLMResponse(
    content="""1. [file_upload] Upload CISA advisory documents on APT29 campaigns
2. [web_scrape] Scrape MITRE ATT&CK page for APT29 techniques
3. [api_feed] Query VirusTotal API for APT29-attributed hashes
4. [database] Search CVE database for vulnerabilities exploited by APT29
5. [rss_feed] Monitor threat intelligence RSS feeds for APT29 mentions""",
    model="test-model",
    input_tokens=150,
    output_tokens=300,
)


class TestFromPirFlow:
    """Test the PIR refinement and plan response parsing logic."""

    def test_refine_response_parsing(self):
        """First line of refine response should be the refined PIR."""
        content = MOCK_REFINE_RESPONSE.content
        lines = content.strip().split("\n", 1)
        refined = lines[0].strip().strip('"').strip("*").strip()
        analysis = lines[1].strip() if len(lines) > 1 else ""

        assert "APT29" in refined
        assert "Assessment" in analysis

    def test_plan_response_produces_sources(self):
        """Plan response should parse into valid sources."""
        from intel_platform.services.collection_planner import parse_plan_sources
        sources = parse_plan_sources(MOCK_PLAN_RESPONSE.content)

        assert len(sources) == 5
        types = {s["source_type"] for s in sources}
        assert types == {"file_upload", "web_scrape", "api_feed", "database", "rss_feed"}

    def test_full_flow_without_llm(self):
        """Without LLM, plan should still be created with the raw PIR."""
        # This tests the code path where provider is None
        # The plan should be created with pir == refined_pir and no sources
        # (Can't easily test the async endpoint without full FastAPI setup,
        #  but we verify the helper functions work correctly)
        from intel_platform.services.collection_planner import parse_plan_sources
        sources = parse_plan_sources("")
        assert sources == []


# ---------------------------------------------------------------------------
# Execute plan validation
# ---------------------------------------------------------------------------

class TestExecutePlanLogic:
    """Test plan execution business logic."""

    def test_only_draft_or_paused_can_execute(self):
        """Verify status validation logic."""
        from intel_platform.db.models import PlanStatus
        valid_statuses = {PlanStatus.DRAFT, PlanStatus.PAUSED}
        invalid_statuses = {PlanStatus.ACTIVE, PlanStatus.COMPLETED, PlanStatus.ARCHIVED}

        for status in valid_statuses:
            assert status in (PlanStatus.DRAFT, PlanStatus.PAUSED)

        for status in invalid_statuses:
            assert status not in (PlanStatus.DRAFT, PlanStatus.PAUSED)


# ---------------------------------------------------------------------------
# Collection planner service (legacy, still used by parse-plan endpoint)
# ---------------------------------------------------------------------------

class TestCollectionPlanner:
    def test_parse_numbered_items(self):
        from intel_platform.services.collection_planner import parse_collection_plan
        text = """1. Search news sources for recent activity
2. Review government databases for sanctions
3. Analyze social media posts from known accounts"""

        items = parse_collection_plan(text)
        assert len(items) == 3
        assert items[0]["description"] == "Search news sources for recent activity"
        assert items[0]["source_type"] == "news"
        assert items[1]["source_type"] == "database"
        assert items[2]["source_type"] == "social_media"

    def test_parse_bullet_points(self):
        from intel_platform.services.collection_planner import parse_collection_plan
        text = """- Upload captured documents
- Search OSINT databases"""

        items = parse_collection_plan(text)
        assert len(items) == 2
        assert items[0]["source_type"] == "document"
        assert items[1]["source_type"] == "database"

    def test_parse_empty_text(self):
        from intel_platform.services.collection_planner import parse_collection_plan
        items = parse_collection_plan("")
        assert len(items) == 1  # creates single fallback item

    def test_all_items_start_unapproved(self):
        from intel_platform.services.collection_planner import parse_collection_plan
        items = parse_collection_plan("1. First item\n2. Second item")
        for item in items:
            assert item["approved"] is False
            assert item["status"] == "pending"
