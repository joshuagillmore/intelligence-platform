"""STIX export coverage — what maps, and what the bundle admits it dropped.

Measured on a campaign project: 175 URL and 24 Software entities were absent
from the bundle with no indication. To a consumer that reads as an incident
with no indicators, rather than as an export that could not carry them.
"""
from __future__ import annotations

from intel_platform.api.routes.export import (
    ENTITY_TO_STIX,
    UNMAPPED_STIX_TYPES,
    _to_stix_object,
)


def _entity(entity_type: str, name: str = "thing") -> dict:
    return {"id": "abc-123", "name": name, "entity_type": entity_type}


class TestObservablesMapToSCOs:
    """The cyber observables a STIX consumer expects to find."""

    def test_url(self):
        obj = _to_stix_object(_entity("URL", "https://malicious.example/payload"))
        assert obj["type"] == "url"
        assert obj["value"] == "https://malicious.example/payload"

    def test_email_address(self):
        obj = _to_stix_object(_entity("EmailAddress", "actor@example.net"))
        assert obj["type"] == "email-addr"
        assert obj["value"] == "actor@example.net"

    def test_software(self):
        obj = _to_stix_object(_entity("Software", "JetBrains TeamCity"))
        assert obj["type"] == "software"
        assert obj["name"] == "JetBrains TeamCity"

    def test_ip_and_domain_still_map(self):
        assert _to_stix_object(_entity("IPAddress", "8.8.8.8"))["value"] == "8.8.8.8"
        assert _to_stix_object(_entity("Domain", "evil.example"))["value"] == "evil.example"

    def test_hash_length_picks_the_algorithm(self):
        assert "SHA-256" in _to_stix_object(_entity("Hash", "a" * 64))["hashes"]
        assert "SHA-1" in _to_stix_object(_entity("Hash", "a" * 40))["hashes"]
        assert "MD5" in _to_stix_object(_entity("Hash", "a" * 32))["hashes"]


class TestReportRequiredFields:
    def test_report_carries_its_required_properties(self):
        """`report` without report_types/published/object_refs is invalid STIX."""
        obj = _to_stix_object(_entity("Report", "Weekly assessment"))
        assert obj["type"] == "report"
        assert obj["report_types"] == ["threat-report"]
        assert obj["published"]
        assert obj["object_refs"] == []


class TestUnmappedAreDeliberate:
    def test_types_with_no_stix_equivalent_return_none(self):
        for etype in ("Custom", "Technology", "Event", "Date", "Financial"):
            assert _to_stix_object(_entity(etype)) is None, etype

    def test_unmapped_list_and_map_do_not_overlap(self):
        """A type must be either mapped or knowingly unmapped, never both."""
        assert not (set(ENTITY_TO_STIX) & UNMAPPED_STIX_TYPES)

    def test_every_stix_type_is_handled_by_the_builder(self):
        """A mapping with no matching branch would emit an object with no value."""
        for etype, stix_type in ENTITY_TO_STIX.items():
            obj = _to_stix_object(_entity(etype, "a" * 64 if stix_type == "file" else "x"))
            assert obj is not None, etype
            assert obj["type"] == stix_type
            # Every SCO/SDO must carry something identifying it.
            assert any(k in obj for k in ("name", "value", "hashes")), (etype, obj)
