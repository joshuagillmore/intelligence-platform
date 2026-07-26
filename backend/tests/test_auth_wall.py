"""Login and paywall pages are not intelligence.

They return 200 with a body of site chrome. Measured live: a crawl of
iiss.org/login/?redirectUrl=… was extracted as content, and the project graph
gained six "events" that were the institute's conference calendar — entities
that look entirely real to everything downstream.
"""
from __future__ import annotations

from intel_platform.collection.agentic import _is_auth_wall


class TestUrlPatterns:
    def test_login_and_paywall_paths(self):
        for url in (
            "https://www.iiss.org/login/?redirectUrl=/online-analysis/military-balance",
            "https://example.com/signin",
            "https://example.com/sign-in?next=/article",
            "https://example.com/subscribe",
            "https://example.com/account/login",
            "https://example.com/register/",
        ):
            assert _is_auth_wall(url, "some page text"), url

    def test_reporting_urls_are_not_auth_walls(self):
        for url in (
            "https://www.reuters.com/world/middle-east/houthi-attack-red-sea",
            "https://amti.csis.org/island-tracker/",
            "https://cloud.google.com/blog/topics/threat-intelligence/apt44",
            # A path that merely contains the letters, not the segment.
            "https://example.com/blogin-analysis",
            "https://example.com/articles/subscriber-growth-in-media",
        ):
            assert not _is_auth_wall(url, "some page text"), url


class TestContentPhrases:
    def test_paywall_phrasing_is_detected(self):
        for text in (
            "Sign in to continue reading this analysis.",
            "Subscribe to read the full report.",
            "This content is for subscribers only.",
            "You have reached your article limit for this month.",
        ):
            assert _is_auth_wall("https://example.com/analysis/x", text), text

    def test_article_about_paywalls_survives(self):
        """The phrase must be page chrome, not the subject of the reporting."""
        body = (
            "Houthi forces struck the MV Northern Star in the Red Sea on 12 March 2026. "
            + ("Analysts noted the attack pattern continued through the month. " * 40)
            + "Some outlets require readers to subscribe to read further coverage."
        )
        assert not _is_auth_wall("https://reuters.com/world/houthi-attack", body)

    def test_empty_inputs(self):
        assert not _is_auth_wall("", "")
        assert not _is_auth_wall("https://example.com/news", "")
