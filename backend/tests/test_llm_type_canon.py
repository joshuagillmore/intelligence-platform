"""Low -> G: every canonical type the LLM map produces is a type the graph has.

_LLM_TYPE_CANON mapped satellite/vehicle/hardware to "EquipmentType" and tank
to "MilitaryAsset". Neither is an EntityType nor has a model class, so
graph_builder fell back to Custom and every satellite, vehicle and tank the
model named was stored as :Custom.

This is the hook the plan asks for: a canon target that the graph builder
cannot resolve fails here rather than silently at ingest.
"""
from __future__ import annotations

import pytest

from intel_platform.models.entities import EntityType
from intel_platform.models.type_hierarchy import normalize_entity_type
from intel_platform.services.extraction import _LLM_TYPE_CANON, _normalize_llm_entity_type
from intel_platform.services.graph_builder import ENTITY_TYPE_MAP

_ENUM_VALUES = {t.value for t in EntityType}


def _resolves(type_name: str) -> bool:
    """Mirror graph_builder.build_graph_from_extractions' type resolution:
    a model class for the type or its parent category, else EntityType(type)."""
    specific, parent = normalize_entity_type(type_name)
    return (
        specific in ENTITY_TYPE_MAP
        or parent in ENTITY_TYPE_MAP
        or specific in _ENUM_VALUES
    )


@pytest.mark.parametrize("raw,canon", sorted(_LLM_TYPE_CANON.items()))
def test_every_canon_target_is_a_graph_type(raw, canon):
    assert _resolves(canon), f"{raw!r} -> {canon!r} would be stored as Custom"


@pytest.mark.parametrize("raw,expected", [
    ("satellite", "Satellite"),
    ("Vehicle", "Vehicle"),
    ("hardware", "Hardware"),
    ("tank", "Vehicle"),
])
def test_equipment_lands_on_real_types(raw, expected):
    assert _normalize_llm_entity_type(raw) == expected
