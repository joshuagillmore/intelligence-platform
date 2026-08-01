"""Every extractable entity type must be in the name index.

A label missing from `entity_name_search` is invisible to cross-document
deduplication: search_entity_by_name short-circuits on fulltext hits, so a type
the index does not cover never finds its earlier self and every extraction mints
another node.

Measured on a live graph before the fix: 86 duplicated (name, type) pairs and
192 redundant rows, roughly a tenth of the graph, every one of them in an
unindexed label. "Newnew Polar Bear" existed five times as a Document while the
lookup returned an unrelated Organization.

Fourteen labels were missing — Aircraft, Custom, Document, Drone, Financial,
Infrastructure, Product, Quantity, Radar, Ship, Software, Submarine, Technology,
Weapon — and the index had silently kept its original label set since creation,
because CREATE FULLTEXT INDEX ... IF NOT EXISTS is a no-op once it exists.
"""
from __future__ import annotations

import pytest

from intel_platform.graph.schema import (
    ENTITY_NAME_INDEX,
    ENTITY_NAME_LABELS,
    FULLTEXT_INDEXES,
    _sync_entity_name_index,
)

# Types the extractor and graph builder actually produce.
EXTRACTABLE = [
    "Person", "Organization", "Location", "Event", "Document", "Custom",
    "Ship", "Financial", "Quantity", "Infrastructure", "Product", "Software",
    "Technology", "Aircraft", "Drone", "Weapon", "Campaign", "ThreatActor",
    "Malware", "Vulnerability", "TTP", "Domain", "URL", "IPAddress",
    "EmailAddress", "Hash",
]


class TestIndexCoversWhatExtractionProduces:
    @pytest.mark.parametrize("label", EXTRACTABLE)
    def test_every_extractable_type_is_indexed(self, label):
        assert label in ENTITY_NAME_LABELS, (
            f"{label} entities cannot be deduplicated across documents"
        )

    @pytest.mark.parametrize("label", ["Document", "Ship", "Quantity", "Financial", "Custom"])
    def test_the_labels_that_produced_duplicates(self, label):
        assert label in ENTITY_NAME_LABELS

    def test_the_create_statement_uses_the_label_list(self):
        """The statement must be generated, not a hand-maintained duplicate that
        can drift from ENTITY_NAME_LABELS."""
        stmt = FULLTEXT_INDEXES[0]
        for label in ENTITY_NAME_LABELS:
            assert label in stmt


class TestNonEntityLabelsStayOut:
    @pytest.mark.parametrize("label", ["Project", "User", "Snapshot", "Collection", "Date"])
    def test_infrastructure_labels_are_not_indexed(self, label):
        """Resolution must never merge an entity against a project or a user."""
        assert label not in ENTITY_NAME_LABELS

    @pytest.mark.parametrize("label", [
        "AttackTechnique", "AttackGroup", "AttackSoftware", "AttackTactic", "Cwe",
    ])
    def test_shared_reference_data_is_not_indexed(self, label):
        """MITRE nodes are shared across projects; indexing them would let one
        project's resolution match another's catalogue."""
        assert label not in ENTITY_NAME_LABELS


class _FakeSession:
    def __init__(self, existing_labels=None, missing=False):
        self.existing_labels = existing_labels
        self.missing = missing
        self.ran: list[str] = []

    def run(self, query, parameters=None):
        self.ran.append(query)
        if query.startswith("SHOW INDEXES"):
            if self.missing:
                return _FakeResult(None)
            return _FakeResult({"labelsOrTypes": self.existing_labels})
        return _FakeResult(None)


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def single(self):
        return self._row


class TestStaleIndexIsRebuilt:
    def test_a_stale_label_set_is_dropped(self):
        """The whole point: adding a label is a no-op without this, so a
        long-lived database keeps whatever set it was created with."""
        session = _FakeSession(existing_labels=["Person", "Organization"])
        _sync_entity_name_index(session)
        assert any(q.startswith(f"DROP INDEX {ENTITY_NAME_INDEX}") for q in session.ran)

    def test_a_current_index_is_left_alone(self):
        session = _FakeSession(existing_labels=list(ENTITY_NAME_LABELS))
        _sync_entity_name_index(session)
        assert not any("DROP INDEX" in q for q in session.ran)

    def test_a_missing_index_is_not_dropped(self):
        """Nothing to rebuild — the CREATE that follows makes it."""
        session = _FakeSession(missing=True)
        _sync_entity_name_index(session)
        assert not any("DROP INDEX" in q for q in session.ran)

    def test_label_order_does_not_trigger_a_rebuild(self):
        session = _FakeSession(existing_labels=sorted(ENTITY_NAME_LABELS))
        _sync_entity_name_index(session)
        assert not any("DROP INDEX" in q for q in session.ran)
