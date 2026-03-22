"""Entity type hierarchy — maps specific types to parent categories."""

# Parent category → list of child types
TYPE_HIERARCHY = {
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
        "IPAddress", "Domain", "Hash", "Vulnerability", "TTP",
        "Malware", "Software", "Exploit", "Backdoor", "Botnet",
        "C2Server", "Ransomware", "Trojan",
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

# Build reverse lookup: specific_type → parent_category
_TYPE_TO_PARENT: dict[str, str] = {}
for parent, children in TYPE_HIERARCHY.items():
    for child in children:
        _TYPE_TO_PARENT[child.lower()] = parent
        _TYPE_TO_PARENT[child] = parent


def get_parent_category(entity_type: str) -> str:
    """Get the parent category for an entity type."""
    return _TYPE_TO_PARENT.get(entity_type, _TYPE_TO_PARENT.get(entity_type.lower(), "Other"))


def get_all_types_for_category(category: str) -> list[str]:
    """Get all specific types under a parent category."""
    return TYPE_HIERARCHY.get(category, [])


def normalize_entity_type(raw_type: str) -> tuple[str, str]:
    """Normalize a raw entity type from LLM. Returns (specific_type, parent_category)."""
    # Try exact match first
    parent = _TYPE_TO_PARENT.get(raw_type)
    if parent:
        return raw_type, parent

    # Try case-insensitive
    parent = _TYPE_TO_PARENT.get(raw_type.lower())
    if parent:
        # Find the canonical casing
        for p, children in TYPE_HIERARCHY.items():
            for c in children:
                if c.lower() == raw_type.lower():
                    return c, p
        return raw_type, parent

    # Try partial match (e.g., "Military Commander" -> "Commander" -> "Person")
    words = raw_type.split()
    for word in reversed(words):  # Try last word first (more specific)
        parent = _TYPE_TO_PARENT.get(word)
        if parent:
            return raw_type, parent

    return raw_type, "Other"
