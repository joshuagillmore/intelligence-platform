from __future__ import annotations

import unicodedata
import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, computed_field


class EntityType(str, Enum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    EVENT = "Event"
    IP_ADDRESS = "IPAddress"
    DOMAIN = "Domain"
    URL = "URL"
    EMAIL_ADDRESS = "EmailAddress"
    HASH = "Hash"
    VULNERABILITY = "Vulnerability"
    TTP = "TTP"
    MALWARE = "Malware"
    THREAT_ACTOR = "ThreatActor"
    CAMPAIGN = "Campaign"
    DOCUMENT = "Document"
    TOPIC = "Topic"
    REPORT = "Report"
    ASSESSMENT = "Assessment"
    # Extended types for LLM extraction
    TECHNOLOGY = "Technology"
    WEAPON = "Weapon"
    VEHICLE = "Vehicle"
    # Platform types the extraction taxonomy already advertises and the type
    # hierarchy already resolves. They were absent here, so build_graph_from_
    # extractions hit `EntityType(specific_type)` -> ValueError -> CUSTOM, and
    # every ship, aircraft, drone and missile silently landed as Custom. Weapon
    # only survived because it happened to be listed.
    SHIP = "Ship"
    SUBMARINE = "Submarine"
    AIRCRAFT = "Aircraft"
    DRONE = "Drone"
    MISSILE = "Missile"
    RADAR = "Radar"
    SATELLITE = "Satellite"
    FACILITY = "Facility"
    FINANCIAL = "Financial"
    INFRASTRUCTURE = "Infrastructure"
    SOFTWARE = "Software"
    HARDWARE = "Hardware"
    COUNTRY = "Country"
    CITY = "City"
    REGION = "Region"
    MILITARY_UNIT = "MilitaryUnit"
    GOVERNMENT_AGENCY = "GovernmentAgency"
    DATE = "Date"
    QUANTITY = "Quantity"
    PRODUCT = "Product"
    CUSTOM = "Custom"


# Entity types that are system/metadata — excluded from the topic mind map
# entity branches. "Collection" is not in the enum but is stored as a raw
# string in Neo4j by the collection planner.
SYSTEM_ENTITY_TYPES = frozenset({
    "Document", "Topic", "Report", "Assessment", "Collection", "Project",
})


PROBABILITY_SCALE = [
    (0.01, 0.05, "Almost No Chance"),
    (0.05, 0.20, "Very Unlikely"),
    (0.20, 0.35, "Unlikely"),
    (0.35, 0.65, "Roughly Even Chance"),
    (0.65, 0.80, "Likely"),
    (0.80, 0.95, "Very Likely"),
    (0.95, 0.99, "Almost Certain"),
]


def probability_to_label(p: float) -> str:
    for low, high, label in PROBABILITY_SCALE:
        if label == "Almost Certain":
            if low <= p <= high:
                return label
        else:
            if low <= p < high:
                return label
    return "Unknown"


DATE_PRECISIONS = ("day", "month", "year")


# Entity types whose identity is the record itself, not its name. Two documents
# called "text_input", two notebook entries titled "Observations" and two
# assessments of one entity are different things, so these are never keyed by
# name and never merged on it. Every other type is: one node per
# (project_id, normalized_name, entity_type).
UNKEYED_ENTITY_TYPES = frozenset({"Document", "Report", "Assessment"})

# Trimmed from both ends of a name before it is compared. Deliberately an
# explicit list rather than every Unicode punctuation character: "C#", "100%",
# "-5" and "AT&T" carry meaning in the character a blanket rule would strip,
# and "C#" must not become the language "C".
_TRIM_CHARS = frozenset(
    ".,;:!?'\"`*_~|/\\()[]{}<>"
    "‘’‚‛“”„‟"  # curly quotes
    "«»‹›"  # guillemets
    "…·•"  # ellipsis, middle dot, bullet
)


def normalize_name(name: str) -> str:
    """The form two names are compared in: lower case, whitespace collapsed,
    punctuation trimmed from both ends.

    "Orion Holdings", " orion  holdings. " and "'Orion Holdings'" are one
    entity. Interior punctuation stays ("U.S. Navy" keeps its dots), as does
    any character outside `_TRIM_CHARS`. NFC first, so a composed and a
    decomposed "é" compare equal.
    """
    text = " ".join(unicodedata.normalize("NFC", name or "").split()).lower()
    start, end = 0, len(text)
    while start < end and (text[start] in _TRIM_CHARS or text[start].isspace()):
        start += 1
    while end > start and (text[end - 1] in _TRIM_CHARS or text[end - 1].isspace()):
        end -= 1
    return text[start:end]


class Entity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    entity_type: EntityType
    project_id: str
    source_doc_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # When the thing this entity describes actually happened, as opposed to when
    # it was ingested. Lives on the base class because dates attach to more than
    # Events — a vulnerability has a disclosure date, a campaign a timeframe.
    #
    # Stored as an interval because reporting rarely gives an instant: "since
    # 2024" and "in March" are intervals, and collapsing them to a point puts
    # every month-only date on the 1st, which shows up as a false spike on any
    # histogram. `t_start`/`t_end` bound the period the source actually
    # supports; `date_precision` records how precise the source was so a reader
    # can render "March 2026" rather than "1 March 2026".
    event_datetime: datetime | None = None
    t_start: datetime | None = None
    t_end: datetime | None = None
    date_precision: str = ""  # one of DATE_PRECISIONS, or "" when undated
    date_text: str = ""  # the source's own wording, e.g. "early March 2026"

    @computed_field
    @property
    def normalized_name(self) -> str | None:
        """The name this entity is unique by, within its project and type.

        `create_entity` MERGEs on (project_id, normalized_name, entity_type),
        which a uniqueness constraint backs, so two builds that meet one entity
        at once make one node. None for record types (UNKEYED_ENTITY_TYPES) and
        for a name with nothing left after normalising: the store never writes
        a None, so such a node is outside the constraint and keyed by id alone.
        """
        if self.entity_type.value in UNKEYED_ENTITY_TYPES:
            return None
        return normalize_name(self.name) or None


class Person(Entity):
    entity_type: EntityType = EntityType.PERSON
    aliases: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    affiliations: list[str] = Field(default_factory=list)


class Organization(Entity):
    entity_type: EntityType = EntityType.ORGANIZATION
    org_type: str = ""


class Location(Entity):
    entity_type: EntityType = EntityType.LOCATION
    latitude: float | None = None
    longitude: float | None = None
    location_type: str = ""


class Event(Entity):
    # `event_datetime` now lives on Entity; Event keeps it only for readability.
    entity_type: EntityType = EntityType.EVENT
    description: str = ""
    event_datetime: datetime | None = None
    event_type: str = ""


class IPAddress(Entity):
    entity_type: EntityType = EntityType.IP_ADDRESS
    asn: str = ""
    geolocation: str = ""


class Domain(Entity):
    entity_type: EntityType = EntityType.DOMAIN
    registrant: str = ""
    registration_date: str = ""
    dns_records: str = ""  # JSON string — Neo4j can't store nested dicts


class URL(Entity):
    entity_type: EntityType = EntityType.URL


class EmailAddress(Entity):
    entity_type: EntityType = EntityType.EMAIL_ADDRESS


class Hash(Entity):
    entity_type: EntityType = EntityType.HASH
    hash_type: str = ""
    malware_family: str = ""


class Vulnerability(Entity):
    entity_type: EntityType = EntityType.VULNERABILITY
    cve_id: str = ""
    cvss_score: float | None = None
    affected_products: list[str] = Field(default_factory=list)


class TTP(Entity):
    entity_type: EntityType = EntityType.TTP
    technique_id: str = ""
    tactic: str = ""
    description: str = ""


class Malware(Entity):
    entity_type: EntityType = EntityType.MALWARE
    family: str = ""
    malware_type: str = ""


class ThreatActor(Entity):
    entity_type: EntityType = EntityType.THREAT_ACTOR
    aliases: list[str] = Field(default_factory=list)
    attributed_nation: str = ""
    motivation: str = ""


class Campaign(Entity):
    entity_type: EntityType = EntityType.CAMPAIGN
    description: str = ""
    timeframe: str = ""
    objectives: str = ""


class Document(Entity):
    entity_type: EntityType = EntityType.DOCUMENT
    url: str = ""
    content: str = ""
    reliability_rating: str = ""
    summary_json: str = ""  # per-doc structured summary (summary/key_facts/sentiment/topics)


class Topic(Entity):
    entity_type: EntityType = EntityType.TOPIC
    parent_id: str | None = None


class Report(Entity):
    entity_type: EntityType = EntityType.REPORT
    report_type: str = ""
    content: str = ""
    version: int = 1


class Assessment(Entity):
    entity_type: EntityType = EntityType.ASSESSMENT
    judgment: str = ""
    probability: float = 0.5
    analyst: str = ""
    methodology: str = ""

    @computed_field
    @property
    def probability_label(self) -> str:
        return probability_to_label(self.probability)
