"""Every relationship the build does not write is counted, with its reason.

ASSOCIATED_WITH edges below `cooccurrence_confidence_min` were skipped with a
bare `continue`: not in `relationships_dropped`, not in the by-type map, not
logged. NLP co-occurrence edges carry confidence 0.5 against a 0.55 bar, so
every one of them vanished, and a build that wrote none of its relationships
reported nothing dropped. (Found by the extraction package's corpus eval.)

`relationships_dropped` is now every edge not written, and
`relationships_dropped_by_reason` says why: `unknown_endpoint` (an endpoint
the extraction never produced) or `below_cooccurrence_min`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from intel_platform.config import settings
from intel_platform.services.graph_builder import build_graph_from_extractions

ENTITIES = [
    {"name": "Orion Holdings", "entity_type": "Organization"},
    {"name": "Marek Ilyas", "entity_type": "Person"},
]


def _store():
    written: list = []
    return written, SimpleNamespace(
        create_entity=lambda e: {"id": e.id},
        search_entity_by_name=lambda *a, **k: [],
        record_entity_source=lambda *a, **k: None,
        record_mentions=lambda *a, **k: 0,
        create_relationship=lambda rel: written.append(rel) or {},
    )


def _rel(rel_type: str, confidence: float, target: str = "Marek Ilyas") -> dict:
    return {"source_name": "Orion Holdings", "target_name": target, "rel_type": rel_type, "confidence": confidence}


def _build(relationships: list[dict]) -> tuple[list, dict]:
    written, store = _store()
    return written, build_graph_from_extractions(store, ENTITIES, relationships, project_id="test-drop-reasons")


@pytest.fixture(autouse=True)
def _bar(monkeypatch):
    monkeypatch.setattr(settings, "cooccurrence_confidence_min", 0.55)


def test_a_cooccurrence_edge_below_the_bar_is_counted_as_dropped():
    written, result = _build([_rel("ASSOCIATED_WITH", 0.5)])
    assert written == []
    assert result["relationships_created"] == 0
    assert result["relationships_dropped"] == 1
    assert result["relationships_dropped_by_reason"] == {"unknown_endpoint": 0, "below_cooccurrence_min": 1}
    assert result["relationships_dropped_by_type"] == {"ASSOCIATED_WITH": 1}


def test_a_cooccurrence_edge_at_the_bar_is_written():
    written, result = _build([_rel("ASSOCIATED_WITH", 0.55)])
    assert len(written) == 1
    assert result["relationships_dropped"] == 0


def test_a_typed_edge_below_the_bar_is_written():
    """The bar is for blanket co-occurrence only."""
    written, result = _build([_rel("COMMANDED_BY", 0.3)])
    assert len(written) == 1
    assert result["relationships_dropped_by_reason"]["below_cooccurrence_min"] == 0


def test_an_unknown_endpoint_keeps_its_own_reason():
    _, result = _build([_rel("TARGETS", 0.9, target="Never Extracted")])
    assert result["relationships_dropped"] == 1
    assert result["relationships_dropped_by_reason"] == {"unknown_endpoint": 1, "below_cooccurrence_min": 0}
    assert result["relationships_dropped_by_type"] == {"TARGETS": 1}


def test_the_counts_agree():
    _, result = _build([
        _rel("ASSOCIATED_WITH", 0.5), _rel("ASSOCIATED_WITH", 0.4),
        _rel("TARGETS", 0.9, target="Never Extracted"), _rel("USES", 0.9),
    ])
    assert result["relationships_created"] == 1
    assert result["relationships_dropped"] == 3
    assert sum(result["relationships_dropped_by_reason"].values()) == 3
    assert sum(result["relationships_dropped_by_type"].values()) == 3
    assert result["relationships_dropped_by_type"] == {"ASSOCIATED_WITH": 2, "TARGETS": 1}


def test_the_shape_is_stable_when_nothing_is_dropped():
    _, result = _build([])
    assert result["relationships_dropped_by_reason"] == {"unknown_endpoint": 0, "below_cooccurrence_min": 0}
