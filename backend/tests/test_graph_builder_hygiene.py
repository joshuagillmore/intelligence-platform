"""Entity hygiene at graph-build time — junk names and platform typing.

Both cases were found in a live intelligence product: markdown heading rules
were reasoned about as financial figures, and Philippine navy vessels were
typed Custom.
"""
from __future__ import annotations

from intel_platform.services.graph_builder import (
    _is_junk_name,
    _is_web_chrome,
    _type_from_name,
)


class TestJunkNames:
    def test_markdown_rules_are_junk(self):
        for name in ("###", "####", "#####", "######", "---", "***", "|", "  "):
            assert _is_junk_name(name), name

    def test_short_real_names_survive(self):
        """"US" and "UK" are legitimate entities — the filter must stay narrow."""
        for name in ("US", "UK", "AI", "G7", "Xi"):
            assert not _is_junk_name(name), name

    def test_multiline_navigation_blocks_are_junk(self):
        """Observed live, all typed Organization: nav furniture captured whole."""
        for name in ("Microsoft Security\nProtect", "TRENDS & INSIGHTS\nEnter",
                     "Threats & Risks\n*", "Some Org\r\nSubscribe"):
            assert _is_junk_name(name), name

    def test_single_line_names_with_punctuation_survive(self):
        for name in ("Ansar Allah", "AT&T", "Safe{Wallet}", "BRP Datu Sumakwel (MMOV 3019)"):
            assert not _is_junk_name(name), name

    def test_empty_and_none(self):
        assert _is_junk_name("")
        assert _is_junk_name(None)


class TestPlatformTyping:
    def test_philippine_navy_prefix(self):
        assert _type_from_name("BRP Cape San Agustin (MRRV-4408)", "Custom") == "Ship"
        assert _type_from_name("BRP Datu Sumakwel (MMOV 3019)", "Custom") == "Ship"

    def test_other_national_prefixes(self):
        for name in ("HMCS Halifax", "KRI Nanggala", "ROKS Dokdo", "TCG Anadolu"):
            assert _type_from_name(name, "Custom") == "Ship", name

    def test_merchant_prefixes_still_work(self):
        assert _type_from_name("MV Aurora Trader", "Custom") == "Ship"
        assert _type_from_name("MT Coral Sky", "Organization") == "Ship"

    def test_specific_type_is_never_overridden(self):
        """A type the model chose deliberately must win over the name hint."""
        assert _type_from_name("BRP Cape San Agustin", "Submarine") == "Submarine"

    def test_unprefixed_name_unchanged(self):
        assert _type_from_name("Stellar Horizon", "Custom") == "Custom"


class TestWebChrome:
    """Share links and embeds scraped off an article are page furniture.

    Measured across the 15-run campaign: URL was the largest entity type at
    2,531 nodes against 925 Organizations, and 299 were social-platform links —
    all isolated in the graph.
    """

    def test_social_urls_and_domains_are_chrome(self):
        for name in ("https://www.facebook.com/sharer/sharer.php?u=x",
                     "twitter.com", "www.linkedin.com", "https://youtu.be/abc",
                     "instagram.com", "reddit.com", "https://t.me/somechannel"):
            assert _is_web_chrome(name, "URL") or _is_web_chrome(name, "Domain"), name

    def test_reporting_urls_survive(self):
        """Vendors whose names contain a social host as a substring must survive.

        "x.com" as a substring also matches citrix.com, equinix.com, zerofox.com
        and nutanix.com — Citrix in particular is core threat-intel content.
        """
        for name in ("https://www.reuters.com/world/article",
                     "amti.csis.org", "https://cloud.google.com/blog/topics/threat-intelligence",
                     "malicious-c2.example.net",
                     "citrix.com", "https://www.citrix.com/blog/cve-2023-4966",
                     "zerofox.com", "equinix.com", "nutanix.com",
                     "notfacebook.com", "facebook.com.evil.net"):
            assert not _is_web_chrome(name, "URL"), name
            assert not _is_web_chrome(name, "Domain"), name

    def test_only_applies_to_url_and_domain_types(self):
        """An Organization genuinely named Facebook is a real entity."""
        assert not _is_web_chrome("Facebook", "Organization")
        assert not _is_web_chrome("Twitter", "Organization")
        assert not _is_web_chrome("YouTube", "Product")

    def test_empty_name(self):
        assert not _is_web_chrome("", "URL")
        assert not _is_web_chrome(None, "Domain")
