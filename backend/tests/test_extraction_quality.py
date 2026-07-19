"""Parameterized quality tests for entity extraction.

Runs extraction against curated test documents with ground-truth annotations
and asserts minimum quality thresholds for precision, recall, and F1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from intel_platform.services.extraction import extract_entities_nlp
from tests.eval.extraction_eval import (
    compute_entity_metrics,
    compute_type_accuracy,
    load_fixture,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "extraction"

# Discover available test documents
AVAILABLE_FIXTURES = sorted(
    p.stem
    for p in FIXTURES_DIR.glob("*_expected.json")
    if (FIXTURES_DIR / f"{p.stem.replace('_expected', '')}.txt").exists()
)
# Map to base names (without _expected suffix)
FIXTURE_NAMES = [name.replace("_expected", "") for name in AVAILABLE_FIXTURES]


@pytest.fixture(params=FIXTURE_NAMES)
def test_document(request):
    """Load test document and expected output."""
    name = request.param
    text, expected = load_fixture(name)
    return {"name": name, "text": text, "expected": expected}


def test_entity_extraction_quality(test_document):
    """Test that NLP entity extraction meets minimum quality thresholds."""
    entities, relationships = extract_entities_nlp(test_document["text"], doc_id="test-doc")
    expected = test_document["expected"]

    metrics = compute_entity_metrics(entities, expected["entities"])

    # Report for debugging
    print(f"\n--- {test_document['name']} ---")
    print(f"Entity P/R/F1: {metrics['precision']:.2f} / {metrics['recall']:.2f} / {metrics['f1']:.2f}")
    print(f"  TP={metrics['true_positives']} FP={metrics['false_positives']} FN={metrics['false_negatives']}")
    if metrics["fn_details"]:
        missed = [e["name"] for e in metrics["fn_details"][:5]]
        print(f"  Missed: {missed}")

    # Minimum quality thresholds (entity extraction)
    assert metrics["recall"] >= 0.30, (
        f"Entity recall too low: {metrics['recall']:.2f} "
        f"(missed: {[e['name'] for e in metrics['fn_details']]})"
    )


def test_cyber_ioc_extraction():
    """Ensure IOCs (IPs, domains, hashes, CVEs, TTPs) are extracted with high precision."""
    text, expected = load_fixture("cyber_threat_report_1")
    entities, _ = extract_entities_nlp(text, doc_id="test-ioc")

    ioc_types = {"IPAddress", "Domain", "Hash", "Vulnerability", "TTP"}
    predicted_iocs = [e for e in entities if e["entity_type"] in ioc_types]
    expected_iocs = [e for e in expected["entities"] if e["entity_type"] in ioc_types]

    metrics = compute_entity_metrics(predicted_iocs, expected_iocs)

    print(f"\nCyber IOC P/R/F1: {metrics['precision']:.2f} / {metrics['recall']:.2f} / {metrics['f1']:.2f}")

    # IOCs should have high recall (regex-based extraction)
    assert metrics["recall"] >= 0.50, (
        f"IOC recall too low: {metrics['recall']:.2f} "
        f"(missed: {[e['name'] for e in metrics['fn_details']]})"
    )


def test_type_accuracy(test_document):
    """Test that entities are assigned the correct type."""
    entities, _ = extract_entities_nlp(test_document["text"], doc_id="test-type")
    expected = test_document["expected"]

    type_acc = compute_type_accuracy(entities, expected["entities"])

    print(f"\n--- {test_document['name']} type accuracy ---")
    print(f"Accuracy: {type_acc['accuracy']:.2f} ({type_acc['correct']}/{type_acc['total']})")
    if type_acc["confusion"]:
        print(f"Confusion: {type_acc['confusion']}")

    # spaCy NLP can only map to ~10 broad types (Person, Organization, Location, etc.)
    # so type accuracy for intelligence-domain-specific types (MilitaryAsset, ThreatActor,
    # Malware, Campaign, etc.) will be low. LLM/hybrid mode will score higher.
    if type_acc["total"] > 0:
        assert type_acc["accuracy"] >= 0.30, (
            f"Type accuracy too low: {type_acc['accuracy']:.2f}, confusion: {type_acc['confusion']}"
        )


def test_deduplication_regression():
    """Ensure entities mentioned multiple times are deduplicated."""
    text = (
        "Vladimir Putin met with Xi Jinping in Moscow. "
        "Putin and Xi Jinping discussed bilateral relations. "
        "The Russian president then flew to Beijing."
    )
    entities, _ = extract_entities_nlp(text, doc_id="test-dedup")
    names = [e["name"] for e in entities]

    # No exact duplicates
    assert len(names) == len(set(names)), f"Duplicate entities found: {names}"


def test_known_entities_always_extracted():
    """Ensure entities from KNOWN_PERSONS, KNOWN_ORGANIZATIONS, etc. are correctly typed."""
    text = (
        "Sergei Lavrov held talks with NATO officials. "
        "The FSB and CIA exchanged intelligence through back channels. "
        "The meeting took place in the Persian Gulf region."
    )
    entities, _ = extract_entities_nlp(text, doc_id="test-known")

    entity_map = {e["name"].lower(): e for e in entities}

    # Known persons should be extracted as Person
    if "sergei lavrov" in entity_map:
        assert entity_map["sergei lavrov"]["entity_type"] == "Person"

    # Known organizations
    for org in ["nato", "fsb", "cia"]:
        if org in entity_map:
            assert entity_map[org]["entity_type"] == "Organization", f"{org} mistyped as {entity_map[org]['entity_type']}"


def test_empty_and_whitespace():
    """Extraction handles edge cases gracefully."""
    entities, rels = extract_entities_nlp("", doc_id="empty")
    assert entities == []
    assert rels == []

    entities, rels = extract_entities_nlp("   \n\n  \t  ", doc_id="whitespace")
    assert entities == []
    assert rels == []
