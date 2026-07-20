"""Entity type hierarchy — maps specific types to parent categories.

Loads from YAML config at ``data/type_hierarchy.yaml`` with fallback to
the hardcoded default below.
"""

from __future__ import annotations

from intel_platform.data import get_type_hierarchy

# Hardcoded default (used as fallback if YAML not available)
_DEFAULT_HIERARCHY = {
    "Person": [
        "Person", "Analyst", "Operative", "Diplomat", "Commander",
        "Politician", "Scientist", "Executive", "Agent", "Informant",
    ],
    "Organization": [
        "Organization", "Company", "GovernmentAgency", "MilitaryUnit",
        "IntelligenceService", "NGO", "PoliticalParty", "Bank",
        "CriminalGroup", "TerroristGroup", "MediaOutlet", "University",
        "ResearchInstitute", "Corporation", "Consortium",
    ],
    "Location": [
        "Location", "Country", "City", "Region", "Facility", "Base",
        "Port", "Island", "Reef", "Airbase", "Embassy", "Border",
        "Province", "District", "Territory",
    ],
    "Cyber": [
        "IPAddress", "Domain", "URL", "EmailAddress", "Hash",
        "Vulnerability", "TTP", "Malware", "Software", "Exploit",
        "Backdoor", "Botnet", "C2Server", "Ransomware", "Trojan",
    ],
    "Equipment": [
        "Weapon", "Vehicle", "Hardware", "Technology", "Satellite",
        "Aircraft", "Ship", "Drone", "Missile", "Radar",
        "Submarine", "Tank", "Artillery",
    ],
    "Event": [
        "Event", "Attack", "Meeting", "Treaty", "Election",
        "Exercise", "Summit", "Conference", "Incident", "Operation",
    ],
    "Financial": [
        "Financial", "CryptocurrencyExchange", "Transaction",
        "Sanction", "Contract", "Fund",
    ],
    "Intelligence": [
        "Document", "Report", "Assessment", "Briefing",
    ],
    "Campaign": [
        "Campaign", "ThreatActor",
    ],
}


def _get_hierarchy() -> dict[str, list[str]]:
    """Return the type hierarchy, preferring YAML config."""
    h = get_type_hierarchy()
    return h if h else _DEFAULT_HIERARCHY


# Kept as a module-level alias for backward compatibility
TYPE_HIERARCHY = _DEFAULT_HIERARCHY


def _build_reverse_lookup(hierarchy: dict[str, list[str]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for parent, children in hierarchy.items():
        for child in children:
            mapping[child.lower()] = parent
            mapping[child] = parent
    return mapping


def get_parent_category(entity_type: str) -> str:
    """Get the parent category for an entity type."""
    lookup = _build_reverse_lookup(_get_hierarchy())
    return lookup.get(entity_type, lookup.get(entity_type.lower(), "Other"))


def get_all_types_for_category(category: str) -> list[str]:
    """Get all specific types under a parent category."""
    return _get_hierarchy().get(category, [])


def normalize_entity_type(raw_type: str) -> tuple[str, str]:
    """Normalize a raw entity type from LLM. Returns (specific_type, parent_category)."""
    hierarchy = _get_hierarchy()
    lookup = _build_reverse_lookup(hierarchy)

    # Try exact match first
    parent = lookup.get(raw_type)
    if parent:
        return raw_type, parent

    # Try case-insensitive
    parent = lookup.get(raw_type.lower())
    if parent:
        # Find the canonical casing
        for p, children in hierarchy.items():
            for c in children:
                if c.lower() == raw_type.lower():
                    return c, p
        return raw_type, parent

    # Try partial match (e.g., "Military Commander" -> "Commander" -> "Person")
    words = raw_type.split()
    for word in reversed(words):  # Try last word first (more specific)
        parent = lookup.get(word)
        if parent:
            return raw_type, parent

    return raw_type, "Other"
