"""One gate deciding whether a fetched page is content, applied before it costs.

A captcha wall, a login page and an empty shell all return 200. Extraction turns
them into entities that look entirely real — a live crawl of an institute's
login page contributed its conference calendar to the graph as six intelligence
"events" — and each one spends a source from the collection budget that a real
page could have had.

The auth-wall half already existed; interstitials and empty shells did not, and
they fail the same way.
"""
from __future__ import annotations

import pytest

from intel_platform.services import content_quality as cq

# Roughly 380 words, the length of a short news item. Deliberately above the
# thinness threshold: an article is defined here by having substance, and a
# fixture shorter than that would be testing the threshold rather than the rule.
_REAL_ARTICLE = " ".join(
    "Philippine resupply vessels were shadowed by China Coast Guard ship 5205 "
    "near Second Thomas Shoal on 17 June, according to the Armed Forces of the "
    "Philippines, which released video of the encounter showing water cannon "
    "use against the smaller wooden-hulled boats during the mission.".split()
) * 8


class TestRealContentSurvives:
    def test_a_normal_article_is_usable(self):
        assert cq.is_usable("https://amti.csis.org/report/", _REAL_ARTICLE) is True
        assert cq.rejection_reason("https://amti.csis.org/report/", _REAL_ARTICLE) == ""

    def test_an_article_about_paywalls_is_not_rejected(self):
        """Only the head is searched, so a piece discussing paywalls survives."""
        body = _REAL_ARTICLE * 2 + " The publisher later added a paywall: subscribe to read."
        assert cq.rejection_reason("https://example.com/news/story", body) == ""

    def test_a_long_article_mentioning_captchas_is_not_rejected(self):
        """An interstitial is a page with nothing on it. A full article that
        discusses captchas is exactly the reporting a cyber requirement wants,
        and the keyword alone must not condemn it."""
        body = "Researchers studied how captcha challenges deter scraping. " + _REAL_ARTICLE
        assert cq.rejection_reason("https://example.com/news/story", body) == ""

    def test_a_url_containing_login_as_a_word_is_not_rejected(self):
        """The path pattern is anchored on a segment, not a substring."""
        assert cq.rejection_reason("https://example.com/logindustry-report", _REAL_ARTICLE) == ""


class TestJunkIsRejectedWithAReason:
    def test_login_url_is_rejected(self):
        reason = cq.rejection_reason("https://iiss.org/login/?redirectUrl=x", _REAL_ARTICLE)
        assert "login or paywall" in reason

    def test_paywall_phrase_in_the_head_is_rejected(self):
        reason = cq.rejection_reason("https://example.com/a", "Subscribe to read this article. " + _REAL_ARTICLE)
        assert "paywalled" in reason

    @pytest.mark.parametrize("marker", [
        "Checking your browser before accessing",
        "Just a moment...",
        "Please verify you are human",
        "Attention Required! Cloudflare Ray ID",
        "Access denied",
    ])
    def test_interstitials_are_rejected(self, marker):
        """A real interstitial: the marker and nothing else of substance."""
        body = marker + " Please wait while we verify your connection. Enable cookies."
        assert "anti-bot or interstitial" in cq.rejection_reason("https://example.com/a", body)

    def test_a_block_page_detected_by_title(self):
        reason = cq.rejection_reason("https://example.com/a", _REAL_ARTICLE, title="Just a moment...")
        assert "anti-bot or interstitial" in reason

    def test_a_near_empty_page_is_rejected(self):
        reason = cq.rejection_reason("https://example.com/a", "Home About Contact")
        assert "words of content" in reason

    def test_the_reason_is_specific_enough_to_act_on(self):
        """'0 documents' cannot distinguish a blocked site from an empty one."""
        blocked = cq.rejection_reason("https://example.com/a", "Just a moment...")
        empty = cq.rejection_reason("https://example.com/b", "short")
        assert blocked != empty
        assert blocked and empty


class TestAuthWallCompatibility:
    """The crawl path and its existing tests use the narrower name."""

    def test_login_page_is_an_auth_wall(self):
        assert cq.is_auth_wall("https://iiss.org/login/?redirectUrl=x", "") is True

    def test_captcha_page_is_not_called_an_auth_wall(self):
        """A blocked page is a different problem from a paywalled one, and
        conflating them would misreport why collection failed."""
        assert cq.is_auth_wall("https://example.com/a", "Just a moment...") is False

    def test_a_short_real_page_is_not_an_auth_wall(self):
        assert cq.is_auth_wall("https://example.com/a", "brief note") is False

    def test_the_agentic_helper_still_delegates_here(self):
        from intel_platform.collection.agentic import _is_auth_wall

        assert _is_auth_wall("https://iiss.org/login/", "") is True
        assert _is_auth_wall("https://example.com/story", _REAL_ARTICLE) is False


class TestWordCount:
    def test_counts_words_not_characters(self):
        assert cq.word_count("one two three") == 3

    def test_empty_is_zero(self):
        assert cq.word_count("") == 0
        assert cq.word_count(None) == 0

    def test_min_words_is_configurable(self):
        assert cq.rejection_reason("https://e.com/a", "three words here", min_words=2) == ""
