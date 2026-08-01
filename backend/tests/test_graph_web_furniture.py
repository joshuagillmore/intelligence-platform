"""Web furniture must not become graph nodes.

Measured on a live project: 22% of a 2,000-entity graph was URL-shaped, and the
campaign before it had URL as the single largest entity type — 2,531 nodes
against 925 Organizations. None of it answers a requirement, and it crowds real
entities out of every view an analyst reads.

The names below are all real, taken from the graph of a Baltic cable project.
"""
from __future__ import annotations

import pytest

from intel_platform.services.graph_builder import _is_malformed_host, _is_web_chrome


def dropped(name: str, entity_type: str = "URL") -> bool:
    return _is_web_chrome(name, entity_type) or _is_malformed_host(name, entity_type)


class TestAssetsAreDropped:
    @pytest.mark.parametrize("name", [
        "https://assets-v2.i-scmp.com/production/_next/static/media/i.woff2",
        "https://assets.newsweek.com/wp-content/uploads/2025/08/photo.jpg",
        "https://cdn.i-scmp.com/sites/default/files/styles/1020x680/p.png",
        "https://en.wikipedia.org/static/images/footer/wikimedia.svg",
        "https://en.wikipedia.org/static/images/icons/enwiki-25.svg",
    ])
    def test_asset_urls(self, name):
        assert dropped(name) is True

    @pytest.mark.parametrize("name", [
        "assets-v2.i-scmp.com", "assets.newsweek.com", "cdn.i-scmp.com",
    ])
    def test_asset_hosts(self, name):
        assert dropped(name, "Domain") is True

    def test_social_hosts_are_still_dropped(self):
        assert dropped("https://www.facebook.com/sharer/sharer.php") is True


class TestMalformedHostsAreDropped:
    @pytest.mark.parametrize("name", [
        ".gov",                       # a bare suffix stored as a Domain node
        "2fen.wikipedia.org",         # the tail of a percent-encoded URL
        "2fwww.atlanticcouncil.org",
        "a.org",                      # a one-character label is a fragment
    ])
    def test_regex_artifacts(self, name):
        assert dropped(name, "Domain") is True

    def test_a_real_short_domain_survives(self):
        """Two characters is a real registrable label; one is not."""
        assert dropped("bp.com", "Domain") is False
        assert dropped("ec.europa.eu", "Domain") is False


class TestRealSourcesSurvive:
    @pytest.mark.parametrize("name", [
        "https://en.wikipedia.org/wiki/EE-S1",
        "https://en.wikipedia.org/wiki/2024_Baltic_Sea_submarine_cable_disruptions",
        "https://www.newsweek.com/chinese-ship-yi-peng-3-undersea-cables",
        "https://www.atlanticcouncil.org/in-depth-research-reports/issue-brief/",
    ])
    def test_article_urls_are_kept(self, name):
        assert dropped(name) is False

    @pytest.mark.parametrize("name", [
        "carnegieendowment.org", "audiovisual.ec.europa.eu",
        "bsaefiling.fincen.treas.gov", "abcnews.go.com",
    ])
    def test_institutional_domains_are_kept(self, name):
        assert dropped(name, "Domain") is False

    def test_non_web_entities_are_untouched(self):
        """The filter only judges URL and Domain nodes."""
        assert dropped("Yi Peng 3", "Ship") is False
        assert dropped("cdn.i-scmp.com", "Organization") is False


class TestEntityNamesAreNormalised:
    """Markdown carried in with an entity name is stripped, not rejected.

    Observed live: "## disruptions" stored as a Financial entity. The name
    underneath is usually real, and a "**Yi Peng 3**" node sitting beside a
    "Yi Peng 3" node is a resolution failure as much as a display one — they
    can never merge while the punctuation is part of the name.
    """

    @pytest.mark.parametrize("raw,expected", [
        ("## disruptions", "disruptions"),
        ("### Background", "Background"),
        ("**Yi Peng 3**", "Yi Peng 3"),
        ("- Finland", "Finland"),
        ("> Estlink 2", "Estlink 2"),
        ("1. Estlink 2", "Estlink 2"),
        ('"Newnew Polar Bear"', "Newnew Polar Bear"),
    ])
    def test_markdown_is_stripped(self, raw, expected):
        from intel_platform.services.graph_builder import _clean_entity_name

        assert _clean_entity_name(raw) == expected

    @pytest.mark.parametrize("name", ["Yi Peng 3", "US", "G7", "C-Lion1", "EE-S1"])
    def test_real_names_are_untouched(self, name):
        from intel_platform.services.graph_builder import _clean_entity_name

        assert _clean_entity_name(name) == name

    @pytest.mark.parametrize("markup", ["###", "**", "- ", ">"])
    def test_pure_markup_cleans_to_nothing_and_is_then_junk(self, markup):
        """The junk filter runs on the cleaned name, so markup-only entities are
        dropped rather than stored as empty nodes."""
        from intel_platform.services.graph_builder import _clean_entity_name, _is_junk_name

        assert _is_junk_name(_clean_entity_name(markup)) is True

    def test_an_emphasised_name_can_now_match_its_plain_twin(self):
        from intel_platform.services.graph_builder import _clean_entity_name

        assert _clean_entity_name("**Yi Peng 3**") == _clean_entity_name("Yi Peng 3")


class TestMarkdownLinksInNames:
    """Link syntax the extractor cut in half.

    Measured on one BBC article collected 2026-08-01: 453 entities, including
    Organizations named "Europe]", "Germany]", "British Broadcasting
    Corporation]" and "BBC News Mundo (Spanish)](https://www.bbc.com/mundo".
    The model was handed markdown and returned a span of it, so the name is the
    link text plus whatever punctuation the span happened to include.
    """

    @pytest.mark.parametrize("raw,expected", [
        # Truncated at the closing bracket.
        ("Europe]", "Europe"),
        ("Germany]", "Germany"),
        ("British Broadcasting Corporation]", "British Broadcasting Corporation"),
        # Truncated inside the URL.
        ("BBC News Mundo (Spanish)](https://www.bbc.com/mundo", "BBC News Mundo (Spanish)"),
        ("Chinese)](https://www.bbc.com/zhongwen", "Chinese"),
        # A whole link: keep what it says, drop where it points.
        ("[BBC News Brasil](https://www.bbc.com/portuguese)", "BBC News Brasil"),
        ("[Yi Peng 3", "Yi Peng 3"),
    ])
    def test_link_syntax_is_stripped(self, raw, expected):
        from intel_platform.services.graph_builder import _clean_entity_name

        assert _clean_entity_name(raw) == expected

    @pytest.mark.parametrize("name", [
        # A balanced bracketed prefix is meaningful — ingestion adds it.
        "[Collection] Germany suspects sabotage over severed undersea cables",
        # Parentheses are part of plenty of real names.
        "Bosch (Germany)",
        "Nord Stream 2 AG (Switzerland)",
    ])
    def test_balanced_punctuation_is_left_alone(self, name):
        from intel_platform.services.graph_builder import _clean_entity_name

        assert _clean_entity_name(name) == name

    def test_a_truncated_link_can_now_match_the_plain_name(self):
        """The point of stripping rather than rejecting: "Germany]" and
        "Germany" are the same country and must resolve to one node."""
        from intel_platform.services.graph_builder import _clean_entity_name

        assert _clean_entity_name("Germany]") == _clean_entity_name("Germany")
