"""Configurable taxonomy and known entity data loaded from YAML files.

Call reload_taxonomy() to pick up changes at runtime without restart.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_DATA_DIR = Path(__file__).parent

# ── cached data ──────────────────────────────────────────────────────────────

_known: dict | None = None
_hierarchy: dict | None = None
_rel_types: dict | None = None
_tlds: list[str] | None = None


def _load_yaml(filename: str) -> dict:
    path = _DATA_DIR / filename
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def reload_taxonomy() -> None:
    """Reload all YAML data files. Safe to call at runtime."""
    global _known, _hierarchy, _rel_types, _tlds
    _known = _load_yaml("known_entities.yaml")
    _hierarchy = _load_yaml("type_hierarchy.yaml")
    _rel_types = _load_yaml("relationship_types.yaml")
    tld_data = _load_yaml("domain_tlds.yaml")
    _tlds = tld_data.get("tlds", [])


def _ensure_loaded() -> None:
    if _known is None:
        reload_taxonomy()


# ── accessors ────────────────────────────────────────────────────────────────

def get_known_locations() -> set[str]:
    _ensure_loaded()
    return set(_known.get("locations", []))


def get_known_organizations() -> set[str]:
    _ensure_loaded()
    return set(_known.get("organizations", []))


def get_known_persons() -> set[str]:
    _ensure_loaded()
    return set(_known.get("persons", []))


def get_known_acronyms() -> set[str]:
    _ensure_loaded()
    return set(_known.get("acronyms", []))


def get_noise_words() -> set[str]:
    _ensure_loaded()
    return set(_known.get("noise_words", []))


def get_location_keywords() -> list[str]:
    _ensure_loaded()
    return _known.get("location_keywords", [])


def get_org_keywords() -> list[str]:
    _ensure_loaded()
    return _known.get("org_keywords", [])


def get_type_hierarchy() -> dict[str, list[str]]:
    _ensure_loaded()
    return dict(_hierarchy) if _hierarchy else {}


def get_relationship_types() -> dict:
    _ensure_loaded()
    return _rel_types.get("relationship_types", {}) if _rel_types else {}


def get_verb_mappings() -> dict[str, str]:
    _ensure_loaded()
    return _rel_types.get("verb_mappings", {}) if _rel_types else {}


def get_discourse_markers() -> list[str]:
    _ensure_loaded()
    return _rel_types.get("discourse_markers", []) if _rel_types else []


def get_tlds() -> list[str]:
    _ensure_loaded()
    # YAML parses some TLDs (e.g., "no") as booleans; coerce to str
    return [str(t) for t in _tlds] if _tlds else []
