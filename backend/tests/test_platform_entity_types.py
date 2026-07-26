"""Platform types the extraction taxonomy advertises must survive the graph write.

They previously fell through EntityType(specific_type) -> ValueError -> CUSTOM,
so every ship, aircraft, drone and missile landed as Custom while Weapon —
which happened to be in the enum — came through correctly.
"""
import pytest

from intel_platform.models.entities import EntityType
from intel_platform.models.type_hierarchy import normalize_entity_type

PLATFORM_TYPES = ["Ship", "Submarine", "Aircraft", "Drone", "Missile", "Radar", "Satellite", "Weapon"]


@pytest.mark.parametrize("type_name", PLATFORM_TYPES)
def test_platform_type_is_constructible(type_name):
    """The graph builder's fallback does EntityType(name); it must not raise."""
    assert EntityType(type_name).value == type_name


@pytest.mark.parametrize("type_name", PLATFORM_TYPES)
def test_platform_type_resolves_under_equipment(type_name):
    specific, parent = normalize_entity_type(type_name)
    assert specific == type_name
    assert parent == "Equipment", f"{type_name} should sit under Equipment, got {parent}"


def test_the_advertised_taxonomy_and_the_enum_agree():
    """Anything the extraction prompt offers must be representable in the graph."""
    for name in PLATFORM_TYPES:
        EntityType(name)  # raises if the enum drifts from the prompt again
