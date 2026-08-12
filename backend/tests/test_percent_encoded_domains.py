"""Domains recovered from percent-encoded URLs rather than mangled by them.

Share links carry a whole encoded URL in a query parameter —
"linkedin.com/shareArticle?url=https%3A%2F%2Fcybelangel.com%2Fblog" — and the
word boundary before "2F" let it start a domain label. The graph gained Domain
nodes named "2fcybelangel.com", "2fwww.facebook.com" and "252fwww.faa.gov";
measured on a live graph, 31 of 1,483. They surfaced in the Cyber view's IOC
table, where an analyst triaging indicators would find them alongside real ones.
"""
from __future__ import annotations

import pytest

from intel_platform.services.extraction import _extract_cyber_entities, _strip_percent_prefix


def domains(text: str) -> list[str]:
    return sorted(
        e["name"] for e in _extract_cyber_entities(text, "doc-1") if e["entity_type"] == "Domain"
    )


class TestRecovery:
    def test_no_mangled_host_survives_a_share_link(self):
        """The original complaint, and it is now answered twice over.

        This module was written when the fix was to *recover* cybelangel.com
        from the encoding. Since then hosts inside a hyperlink are treated as
        the document's sourcing rather than its content (see
        test_observable_vs_provenance), so a share link now yields nothing at
        all — the mangled name and the clean one alike. What must never happen
        either way is a "2f..." node reaching the IOC table."""
        got = domains("https://www.linkedin.com/shareArticle?url=https%3A%2F%2Fcybelangel.com%2Fblog")
        assert not any(d.startswith(("2f", "252f")) for d in got), got
        assert got == [], "a share link is provenance; nothing in it is an indicator"

    def test_the_containing_site_is_also_sourcing(self):
        """linkedin.com is where the link lives, not something being reported."""
        got = domains("https://www.linkedin.com/shareArticle?url=https%3A%2F%2Fcybelangel.com")
        assert "www.linkedin.com" not in got

    def test_double_encoding_is_handled(self):
        """Seen live as "252fwww.faa.gov" — %252F is an encoded %2F."""
        assert "www.faa.gov" in domains("share https%253A%252Fwww.faa.gov/news")

    @pytest.mark.parametrize("encoded,expected", [
        ("%2Fcybelangel.com", "cybelangel.com"),
        ("%2Fwww.facebook.com", "www.facebook.com"),
        ("%3Aexample.org", "example.org"),
    ])
    def test_common_separators_are_stripped(self, encoded, expected):
        assert expected in domains(f"link {encoded}/path")


class TestNothingElseChanges:
    def test_plain_domains_are_untouched(self):
        assert domains("see bbc.com and example.org for detail") == ["bbc.com", "example.org"]

    def test_a_host_that_really_starts_with_hex_survives(self):
        """"2fa.example.com" is a legitimate name; only a match that began
        immediately after a "%" is treated as encoding debris."""
        assert "2fa.example.com" in domains("our portal 2fa.example.com requires MFA")

    def test_a_url_without_encoding_is_still_only_sourcing(self):
        """Nothing about the percent-encoding rule promotes a cited host. A
        plain news link is the clearest case of a document naming where it came
        from."""
        assert domains("https://www.bbc.com/news/articles/abc123") == []

    def test_no_domain_is_invented_from_pure_encoding(self):
        """If nothing but the encoding remains, that is not a domain."""
        assert _strip_percent_prefix("2f", "x%2f", 2) == ""


class TestTheHelperDirectly:
    def test_it_only_fires_after_a_percent(self):
        # Same string, different preceding character.
        assert _strip_percent_prefix("2fexample.com", "%2fexample.com", 1) == "example.com"
        assert _strip_percent_prefix("2fexample.com", " 2fexample.com", 1) == "2fexample.com"

    def test_a_match_at_the_start_of_the_text_is_left_alone(self):
        assert _strip_percent_prefix("2fexample.com", "2fexample.com", 0) == "2fexample.com"
