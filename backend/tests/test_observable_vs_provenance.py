"""Whether a hostname is an indicator or just where the document came from.

The regex sweep minted a Domain and a URL entity for every host it saw, at 0.9
confidence, with nothing separating a C2 server from a "share on Twitter" link.
On one 5,486-node project that produced 2,653 URL entities — 48% of the graph,
98% of them isolated — and a threat-indicator table whose top rows were
bbc.com, abcnews.go.com and apps.apple.com.

The labelled fixtures could not catch this: they are synthetic threat reports
with no citation links, so the holdout eval scores identically with and without
the fix. These tests supply the case the fixtures lack — prose that carries its
own sourcing, the way a scraped page does.

The rule under test: a host inside a hyperlink is provenance; a host standing
alone in prose is content; defanging overrides both, because writing
``evil[.]com`` is an explicit assertion that a value is an indicator.
"""
from __future__ import annotations

import pytest

from intel_platform.services.extraction import _defanged_values, _extract_cyber_entities


def _named(text: str, entity_type: str | None = None) -> set[str]:
    ents = _extract_cyber_entities(text, doc_id="d1")
    return {e["name"] for e in ents if entity_type is None or e["entity_type"] == entity_type}


class TestSourcingIsNotAnIndicator:
    def test_a_cited_link_mints_nothing(self):
        """The single most common shape in collected text."""
        text = "Read more at https://www.bbc.com/news/world-europe-12345 for background."
        assert _named(text) == set()

    def test_page_furniture_mints_nothing(self):
        """Nav bars and app-store links are what a scraper flattens into prose."""
        text = (
            "Home | About | https://apps.apple.com/gb/app/x | "
            "Share: https://twitter.com/intent/tweet | Cookie policy"
        )
        assert _named(text) == set()

    def test_a_host_inside_a_url_is_not_promoted_to_a_domain(self):
        text = "Source: https://artsci.washington.edu/news/item"
        assert _named(text, "Domain") == set()

    def test_percent_encoded_redirects_do_not_leak_hosts(self):
        """`%2F` reaching the domain regex is what produced `2fen.wikipedia.org`.
        Both the wrapper and the wrapped host are sourcing, so neither survives."""
        text = "Redirect http://tracker.example.com/?u=https%3A%2F%2Fen.wikipedia.org/wiki/Baltic"
        assert _named(text) == set()


class TestContentIsStillExtracted:
    def test_a_host_named_in_prose_is_kept(self):
        """Every Domain in the labelled fixtures is of this shape — an author
        writing the host out because the report is about it."""
        text = "The actor registered microsoftupdate-security.com on 2 March 2026."
        assert "microsoftupdate-security.com" in _named(text, "Domain")

    def test_prose_hosts_survive_alongside_citations(self):
        text = (
            "Per https://www.reuters.com/article/baltic the operator used "
            "gov-ee-portal.com to stage credentials."
        )
        domains = _named(text, "Domain")
        assert "gov-ee-portal.com" in domains, "the reported host was dropped"
        assert "www.reuters.com" not in domains, "the citation became an indicator"

    def test_ip_addresses_are_untouched_by_the_rule(self):
        """The change is scoped to hosts; a bare IP was never the problem."""
        assert "45.83.12.7" in _named("Beaconing observed to 45.83.12.7 over 443.")


class TestDefangingOverrides:
    def test_a_defanged_host_survives_even_inside_a_url(self):
        text = "Implant beaconed to hxxps://evil-c2[.]com/gate.php every 60 seconds."
        assert "evil-c2.com" in _named(text, "Domain")

    def test_a_defanged_url_is_the_only_url_worth_minting(self):
        text = "Stage two pulled from hxxp://bad-host[.]net/payload.bin"
        assert _named(text, "URL") == {"http://bad-host.net/payload.bin"}

    def test_an_ordinary_url_is_never_minted(self):
        """Across all twelve labelled fixtures the expected URL count is zero."""
        text = "See https://www.gov.uk/guidance/sanctions and https://ec.europa.eu/info."
        assert _named(text, "URL") == set()

    def test_assertion_is_recorded_in_the_confidence(self):
        """A defanged value was asserted to be an indicator; a bare one in prose
        is inferred to be. Calling both 0.9 threw that distinction away."""
        asserted = _extract_cyber_entities("C2 at hxxp://bad[.]net/a", "d1")
        inferred = _extract_cyber_entities("They used gov-ee-portal.com to stage.", "d1")
        assert {e["confidence"] for e in asserted if e["entity_type"] == "Domain"} == {0.95}
        assert {e["confidence"] for e in inferred if e["entity_type"] == "Domain"} == {0.9}


class TestDefangDetection:
    @pytest.mark.parametrize("raw,expected", [
        ("evil[.]com", "evil.com"),
        ("hxxps://c2[.]example[.]org/p", "c2.example.org"),
        ("mail[at]bad[.]net", "bad.net"),
        ("10[.]0[.]0[.]1", "10.0.0.1"),
    ])
    def test_the_bare_host_is_recorded_not_just_the_token(self, raw, expected):
        """The Domain check compares against a host, so a value defanged only
        inside a URL still has to register as asserted."""
        assert expected in _defanged_values(f"observed {raw} in traffic")

    def test_ordinary_prose_asserts_nothing(self):
        text = "The report [1] cites figures from 2024. See table [2] for detail."
        assert _defanged_values(text) == set()
