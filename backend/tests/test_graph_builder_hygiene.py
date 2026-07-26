"""Entity hygiene at graph-build time — junk names and platform typing.

Both cases were found in a live intelligence product: markdown heading rules
were reasoned about as financial figures, and Philippine navy vessels were
typed Custom.
"""
from __future__ import annotations

from intel_platform.services.graph_builder import _is_junk_name, _type_from_name


class TestJunkNames:
    def test_markdown_rules_are_junk(self):
        for name in ("###", "####", "#####", "######", "---", "***", "|", "  "):
            assert _is_junk_name(name), name

    def test_short_real_names_survive(self):
        """"US" and "UK" are legitimate entities — the filter must stay narrow."""
        for name in ("US", "UK", "AI", "G7", "Xi"):
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
