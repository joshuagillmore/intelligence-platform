"""Naming conventions re-type entities the model habitually mislabels."""
from intel_platform.services.extraction import _apply_type_hints


def _t(name, etype):
    return {"name": name, "entity_type": etype}


def test_vessel_prefixes_become_ships():
    ents = [_t("MV Aurora Trader", "Custom"), _t("USS Cole", "Organization"), _t("MT Stellar Horizon", "")]
    _apply_type_hints(ents)
    assert [e["entity_type"] for e in ents] == ["Ship", "Ship", "Ship"]


def test_aircraft_designators():
    ents = [_t("MQ-9 Reaper", "Custom"), _t("SU-35", "Technology")]
    _apply_type_hints(ents)
    assert [e["entity_type"] for e in ents] == ["Aircraft", "Aircraft"]


def test_a_confident_specific_type_is_not_overridden():
    """Only the types the model over-uses are replaced."""
    ents = [_t("MV Aurora Trader", "Ship"), _t("USS Cole", "Weapon")]
    _apply_type_hints(ents)
    assert ents[0]["entity_type"] == "Ship"
    assert ents[1]["entity_type"] == "Weapon", "an explicit non-generic type must stand"


def test_unrelated_names_untouched():
    ents = [_t("Maersk Line", "Organization"), _t("Hodeidah", "Location"), _t("Movement Ltd", "Organization")]
    _apply_type_hints(ents)
    assert [e["entity_type"] for e in ents] == ["Organization", "Location", "Organization"]


def test_prefix_must_be_followed_by_a_name():
    """"MV" alone, or "Movement", must not trip the vessel rule."""
    ents = [_t("MV", "Custom"), _t("Movement", "Custom")]
    _apply_type_hints(ents)
    assert [e["entity_type"] for e in ents] == ["Custom", "Custom"]
