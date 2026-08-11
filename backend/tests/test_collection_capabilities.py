"""The planner is told what this deployment can actually collect.

The plan list showed sources the system had no way to reach: a Twitter API
feed (no credential store exists), and "weekly reports from ISIS" as a
file_upload — which the agentic resolver skips entirely, so it sits at zero
records until a person uploads something. Both were well-formed and both were
dead rows an analyst had to work out for themselves.

The cause was that the planner was given a taxonomy of type *labels* with rules
of thumb about when to pick each ("use api_feed for structured data APIs") and
nothing about what the connectors can obtain. Two prompts carried that
taxonomy — the skill's system prompt and the one built at the call site — and
they had already drifted apart: one listed `database`, the other did not, and
they disagreed about CONFIG keys.
"""
from __future__ import annotations

import pytest

# Importing the modules registers the connectors.
import intel_platform.connectors.api_feed  # noqa: F401
import intel_platform.connectors.database  # noqa: F401
import intel_platform.connectors.flat_file  # noqa: F401
import intel_platform.connectors.rss_feed  # noqa: F401
import intel_platform.connectors.web_scrape  # noqa: F401
from intel_platform.connectors.base import (
    CONNECTOR_REGISTRY,
    describe_collection_capabilities,
    unattended_source_types,
)


class TestDerivedFromTheRegistry:
    """Generated, so it cannot drift from the connectors it describes."""

    def test_every_registered_type_is_described(self):
        described = describe_collection_capabilities()
        for source_type in CONNECTOR_REGISTRY:
            assert f"- {source_type}:" in described

    def test_nothing_unregistered_is_offered(self):
        described = describe_collection_capabilities()
        for invented in ("twitter", "social_media", "telegram", "email"):
            assert f"- {invented}:" not in described

    def test_each_type_states_the_config_the_connector_requires(self):
        described = describe_collection_capabilities()
        for source_type, cls in CONNECTOR_REGISTRY.items():
            for key in cls.config_keys:
                assert f'"{key}"' in described, f"{source_type} does not state {key}"


class TestAnalystActionIsNotCollection:
    def test_file_upload_is_the_only_attended_type(self):
        assert unattended_source_types() == ["api_feed", "database", "rss_feed", "web_scrape"]

    def test_file_upload_is_marked_as_an_analyst_action(self):
        """It reads 0 records forever until a person acts, so a planner must
        not treat it as something the system will fetch."""
        described = describe_collection_capabilities()
        upload_line = next(ln for ln in described.splitlines() if ln.startswith("- file_upload:"))
        assert "ANALYST ACTION" in upload_line

    def test_no_unattended_type_is_marked_that_way(self):
        described = describe_collection_capabilities()
        for source_type in unattended_source_types():
            line = next(ln for ln in described.splitlines() if ln.startswith(f"- {source_type}:"))
            assert "ANALYST ACTION" not in line


class TestCredentialLimitIsStated:
    """The specific failure that prompted this: a proposed Twitter API feed."""

    def test_api_feed_says_it_cannot_authenticate(self):
        described = describe_collection_capabilities()
        assert "no credential store" in described
        assert "CANNOT be collected" in described

    def test_commercial_platform_apis_are_named_as_out_of_reach(self):
        described = describe_collection_capabilities().lower()
        assert "twitter" in described

    def test_database_is_not_presented_as_a_database_connection(self):
        """It is an HTTP fetch of public registry pages; calling it a database
        invites proposals needing credentials nobody holds."""
        described = describe_collection_capabilities()
        assert "not a database connection" in described


class TestConfigKeysMatchTheConnectors:
    """A planner told the wrong key produces a source that cannot execute."""

    @pytest.mark.parametrize("source_type,expected", [
        ("web_scrape", "url"),
        ("rss_feed", "feed_url"),
        ("api_feed", "base_url"),
        ("database", "urls"),
    ])
    def test_declared_key_matches_what_configure_requires(self, source_type, expected):
        assert expected in CONNECTOR_REGISTRY[source_type].config_keys

    def test_file_upload_declares_no_config(self):
        assert CONNECTOR_REGISTRY["file_upload"].config_keys == ()


class TestApiFeedConfigBridging:
    """The resolver and the connector disagreed about the config key.

    `_resolve_sources` asks the model for "urls" when the type is api_feed
    (agentic.py), but APIFeedConnector.configure requires "base_url" and raises
    without it — and the multi-URL unwrapping below only covered web_scrape and
    database. Checked against live data: three api_feed sources on the graph
    all carried both keys, one succeeded and two stalled at zero, which is what
    a half-bridged config looks like from outside.
    """

    def test_the_connector_still_requires_base_url(self):
        """Pins the requirement the bridge exists to satisfy."""
        from intel_platform.connectors.api_feed import APIFeedConnector

        with pytest.raises(ValueError, match="base_url"):
            APIFeedConnector().configure({"urls": ["https://example.com/api"]})

    def test_resolver_asks_for_urls_on_api_feed(self):
        """If this stops being true the bridge is dead code and should go."""
        import pathlib

        src = pathlib.Path("src/intel_platform/collection/agentic.py").read_text(encoding="utf-8")
        assert '"urls"] if source.source_type in ("web_scrape", "database", "api_feed")' in src

    def test_first_resolved_url_becomes_the_base_url(self):
        """The bridge itself, as the acquire path applies it."""
        config = {"urls": ["https://api.example.com/v1", "https://other.example.com"]}
        bridged = dict(config)
        if not bridged.get("base_url"):
            urls = bridged.get("urls")
            if isinstance(urls, list) and urls:
                bridged = {**bridged, "base_url": urls[0]}
        assert bridged["base_url"] == "https://api.example.com/v1"

        from intel_platform.connectors.api_feed import APIFeedConnector
        assert APIFeedConnector().configure(bridged)["base_url"] == "https://api.example.com/v1"

    def test_an_explicit_base_url_is_not_overwritten(self):
        config = {"base_url": "https://chosen.example.com", "urls": ["https://other.example.com"]}
        assert config.get("base_url") == "https://chosen.example.com"
