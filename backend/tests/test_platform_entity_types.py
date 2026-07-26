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


# --- naming-convention re-typing at the graph-write boundary -----------------
from intel_platform.services.graph_builder import _type_from_name  # noqa: E402


def test_vessel_prefixes_retype_generic_entities():
    assert _type_from_name("MV Aurora Trader", "Custom") == "Ship"
    assert _type_from_name("MT Coral Sky", "Organization") == "Ship"
    assert _type_from_name("FS Provence", "Infrastructure") == "Ship"
    assert _type_from_name("USS Georgia", "") == "Ship"


def test_uav_designators_retype():
    assert _type_from_name("MQ-9 Reaper", "Custom") == "Drone"
    assert _type_from_name("RQ-4 Global Hawk", "Technology") == "Drone"


def test_a_deliberate_specific_type_is_never_overridden():
    assert _type_from_name("USS Georgia", "Submarine") == "Submarine"
    assert _type_from_name("MV Aurora Trader", "Ship") == "Ship"


def test_ordinary_names_are_untouched():
    for name, t in [("Maersk Line", "Organization"), ("Movement", "Custom"),
                    ("Hodeidah", "Location"), ("MV", "Custom")]:
        assert _type_from_name(name, t) == t, name
