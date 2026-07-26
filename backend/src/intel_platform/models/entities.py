from __future__ import annotations

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


class Entity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    entity_type: EntityType
    project_id: str
    source_doc_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
