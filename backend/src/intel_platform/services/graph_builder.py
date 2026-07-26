from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

import jellyfish

from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import (
    Person, Organization, Location, Event, IPAddress, Domain, Hash,
    Vulnerability, TTP, Malware, ThreatActor, Campaign, URL, EmailAddress,
)
from intel_platform.models.relationships import Relationship
from intel_platform.models.type_hierarchy import normalize_entity_type

logger = logging.getLogger(__name__)

ENTITY_TYPE_MAP = {
    "Person": Person, "Organization": Organization, "Location": Location,
    "Event": Event, "IPAddress": IPAddress, "Domain": Domain, "Hash": Hash,
    "Vulnerability": Vulnerability, "TTP": TTP, "Malware": Malware,
    "ThreatActor": ThreatActor, "Campaign": Campaign,
    "URL": URL, "EmailAddress": EmailAddress,
}


def resolve_entity_name(
    name: str, existing_names: list[str], threshold: float = 0.92,
    entity_type: str = "", existing_types: dict[str, str] | None = None,
) -> str | None:
    """Resolve entity name using Jaro-Winkler similarity + substring matching.

    Only merges entities of compatible types when type info is available.
    Cyber entities (IP, Domain, Hash, CVE, TTP) require exact match only.
    """
    if not existing_names:
        return None

    # Cyber entity types should ONLY match exactly (no fuzzy matching)
    EXACT_MATCH_TYPES = {
        "IPAddress", "Domain", "URL", "EmailAddress", "Hash", "Vulnerability", "TTP",
    }
    if entity_type in EXACT_MATCH_TYPES:
        name_lower = name.lower().strip()
        for existing in existing_names:
            if existing.lower().strip() == name_lower:
                return existing
        return None

    best_match = None
    best_score = 0.0
    name_lower = name.lower().strip()

    for existing in existing_names:
        existing_lower = existing.lower().strip()

        # Skip type-incompatible entities if type info available
        if existing_types and entity_type:
            existing_type = existing_types.get(existing, "")
            if existing_type in EXACT_MATCH_TYPES or entity_type in EXACT_MATCH_TYPES:
                continue  # Don't fuzzy-match cyber entities

        # Exact match
        if name_lower == existing_lower:
            return existing

        # Jaro-Winkler similarity
        score = jellyfish.jaro_winkler_similarity(name_lower, existing_lower)
        if score > best_score:
            best_score = score
            best_match = existing

    if best_score >= threshold:
        return best_match

    # Fallback: substring matching for partial names (Person names only)
    # "Putin" should match "Vladimir Putin"
    if entity_type in ("Person", "ThreatActor", ""):
        import re as _re
        for existing in existing_names:
            existing_lower = existing.lower().strip()
            # Skip cyber entities
            if existing_types and existing_types.get(existing, "") in EXACT_MATCH_TYPES:
                continue
            shorter = min(name_lower, existing_lower, key=len)
            longer = max(name_lower, existing_lower, key=len)
            if len(shorter) >= 4 and _re.search(r'\b' + _re.escape(shorter) + r'\b', longer) and len(shorter) / len(longer) > 0.3:
                return existing

    return None


# Naming conventions that identify a platform type more reliably than the model
# does. Applied as the last step before type resolution, because an unrecognised
# type collapses to Custom at that point and is unrecoverable afterwards.
_GENERIC_TYPES = frozenset({
    "Custom", "Organization", "Technology", "Infrastructure", "Product", "Person", "",
    # The model reaches for these catch-all equipment labels constantly:
    # "MV Northern Star" came back as EquipmentType, which the naming hint below
    # would otherwise decline to override because it looks like a deliberate choice.
    "EquipmentType", "Equipment", "Vehicle", "Asset", "Platform", "System",
})

_NAME_TYPE_HINTS: tuple[tuple[re.Pattern, str], ...] = (
    # Vessel prefixes: "MV Aurora Trader", "USS Georgia", "FS Provence".
    # National naval prefixes are included because they are unambiguous and the
    # model reaches for Custom otherwise — "BRP Cape San Agustin (MRRV-4408)"
    # landed as Custom on a live South China Sea run.
    (re.compile(
        r'^(MV|M/V|MT|M/T|SS|S/S|MS|M/S|RFA|RV|'
        r'USS|USNS|HMS|HMAS|HMCS|HMNZS|FS|FGS|INS|BRP|KRI|ROKS|JS|ARA|NRP|ITS|'
        r'ESPS|TCG|BNS|CNS|HTMS|KD|PNS|RSS|SPS)\s+\S'
    ), "Ship"),
    # UAV designators: "MQ-9 Reaper", "RQ-4 Global Hawk".
    (re.compile(r'^(MQ|RQ)-\d', re.IGNORECASE), "Drone"),
)


# Share buttons and social embeds on a scraped article are page chrome, not
# reporting. Measured across a 15-run campaign: 299 such nodes, all isolated.
# Applied only to URL/Domain entities — an Organization genuinely named
# "Facebook" is a real entity and must survive.
#
# Matched on the registrable host, never as a substring: "x.com" as a substring
# also matches citrix.com, equinix.com, zerofox.com and nutanix.com, which would
# have silently discarded every Citrix node — about as central a vendor as this
# domain has.
_SOCIAL_HOSTS = frozenset({
    "facebook.com", "fb.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "youtu.be", "instagram.com", "pinterest.com", "reddit.com",
    "whatsapp.com", "t.me", "telegram.me", "tiktok.com", "threads.net",
    "bsky.app", "mastodon.social", "flipboard.com", "tumblr.com",
})


def _host_of(name: str) -> str:
    """Best-effort registrable host for a URL or bare domain entity name."""
    raw = (name or "").strip().lower()
    if not raw:
        return ""
    if "//" not in raw:
        raw = "//" + raw
    host = urlsplit(raw).netloc or ""
    host = host.split("@")[-1].split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _is_web_chrome(name: str, entity_type: str) -> bool:
    """True for link-furniture URLs and domains scraped off a page.

    A crawled article carries share links, embeds and footer links for every
    major platform. Extracted as `URL`/`Domain` entities they dominate the graph
    — URL was the single largest entity type across the campaign at 2,531 nodes
    against 925 Organizations — and none of them answer a requirement.
    """
    if entity_type not in ("URL", "Domain"):
        return False
    host = _host_of(name)
    if not host:
        return False
    return any(host == s or host.endswith("." + s) for s in _SOCIAL_HOSTS)


def _is_junk_name(name: str) -> bool:
    """Reject entity names that carry no information.

    Two artifact classes seen in live crawls, both of which reached the graph
    and one of which reached a generated intelligence product:

    - Markdown heading rules ("###", "######") stored as `Financial` nodes, then
      reasoned about in a product as "undisclosed vessel tonnage". Anything with
      no alphanumeric character at all is markup, not an entity.
    - Navigation blocks captured whole ("Microsoft Security\\nProtect",
      "TRENDS & INSIGHTS\\nEnter"), all typed `Organization`. A real entity name
      does not span lines.

    Deliberately narrow: short real names like "US", "UK" and "G7" must survive.
    """
    name = name or ""
    if not any(c.isalnum() for c in name):
        return True
    return "\n" in name or "\r" in name


def _type_from_name(name: str, current: str) -> str:
    """Re-type an entity whose name follows an unambiguous naming convention.

    Only overrides the generic types the model over-uses — never a specific type
    it chose deliberately, so an entity already typed Submarine stays Submarine.
    """
    n = (name or "").strip()
    if not n or (current or "").strip() not in _GENERIC_TYPES:
        return current
    for pattern, better in _NAME_TYPE_HINTS:
        if pattern.match(n):
            return better
    return current


def build_graph_from_extractions(
    store: GraphStore, entities: list[dict], relationships: list[dict], project_id: str,
    source_doc_id: str = "", auto_enrich_loop=None,
) -> dict:
    from intel_platform.config import settings

    created = 0
    merged = 0
    entities_filtered = 0
    name_to_id: dict[str, str] = {}
    # Newly-created entities (id/name/type/project) — fed to the selective
    # auto-enrich hook after the build; the hook filters to cyber types and is
    # a no-op unless the admin has turned auto-enrich on.
    new_entities: list[dict] = []
    resolution_threshold = settings.entity_resolution_threshold

    # Cache for resolved names within this batch to avoid repeated lookups
    _resolution_cache: dict[str, str | None] = {}
    # Track newly created entities for intra-batch resolution
    batch_names: list[str] = []
    batch_name_to_id: dict[str, str] = {}
    batch_name_to_type: dict[str, str] = {}

    for ent_data in entities:
        name = ent_data["name"]
        raw_type = ent_data["entity_type"]

        if _is_junk_name(name) or _is_web_chrome(name, raw_type):
            entities_filtered += 1
            continue

        # Check intra-batch cache first
        cache_key = f"{name}::{raw_type}"
        if cache_key in _resolution_cache:
            cached = _resolution_cache[cache_key]
            if cached:
                name_to_id[name] = cached
                merged += 1
                continue

        # Try resolution against entities created in this batch
        match = resolve_entity_name(
            name, batch_names, threshold=resolution_threshold,
            entity_type=raw_type, existing_types=batch_name_to_type,
        )
        if match:
            name_to_id[name] = batch_name_to_id[match]
            _resolution_cache[cache_key] = batch_name_to_id[match]
            merged += 1
            continue

        # Use indexed lookup against the graph (instead of loading all entities)
        candidates = store.search_entity_by_name(project_id, name, limit=20)
        if candidates:
            candidate_names = [c["name"] for c in candidates]
            candidate_name_to_id = {c["name"]: c["id"] for c in candidates}
            candidate_name_to_type = {c["name"]: c.get("entity_type", "") for c in candidates}
            match = resolve_entity_name(
                name, candidate_names, threshold=resolution_threshold,
                entity_type=raw_type, existing_types=candidate_name_to_type,
            )
            if match:
                name_to_id[name] = candidate_name_to_id[match]
                _resolution_cache[cache_key] = candidate_name_to_id[match]
                merged += 1
                continue

        _resolution_cache[cache_key] = None

        # Naming conventions get the last word, immediately before the type is
        # resolved. Applying this during extraction was not enough: the model
        # emits long-tail types the canon cannot enumerate ("tanker" is mapped,
        # the next synonym is not), and whatever it chose only collapses here.
        raw_type = _type_from_name(name, raw_type)

        # Normalize the entity type using the hierarchy
        specific_type, parent_category = normalize_entity_type(raw_type)

        # Try to find a Pydantic class for the specific type, then parent category
        cls = ENTITY_TYPE_MAP.get(specific_type) or ENTITY_TYPE_MAP.get(parent_category)
        # Determine source doc ID from extraction data or caller
        entity_doc_id = ent_data.get("source", "") or source_doc_id

        # Build constructor kwargs, passing through extracted attributes
        kwargs: dict = {"name": name, "project_id": project_id, "source_doc_id": entity_doc_id}
        attrs = ent_data.get("attributes", {})
        if attrs and cls:
            # Only pass attributes that the Pydantic model accepts. `is not None`
            # (not truthiness) so a real 0.0 latitude/longitude (equator / prime
            # meridian) survives — setting a text field to "" just matches its
            # default, so this is safe for non-numeric fields too.
            model_fields = set(cls.model_fields.keys())
            for k, v in attrs.items():
                if k in model_fields and v is not None:
                    kwargs[k] = v

        if cls:
            entity = cls(**kwargs)
        else:
            # Generic entity for unknown types
            from intel_platform.models.entities import Entity, EntityType
            try:
                et = EntityType(specific_type)
            except ValueError:
                et = EntityType.CUSTOM
            entity = Entity(name=name, entity_type=et, project_id=project_id, source_doc_id=entity_doc_id)

        store.create_entity(entity)
        name_to_id[name] = entity.id
        batch_names.append(name)
        batch_name_to_id[name] = entity.id
        batch_name_to_type[name] = raw_type
        new_entities.append({
            "id": entity.id, "name": name,
            "entity_type": entity.entity_type.value, "project_id": project_id,
        })
        created += 1

    cooccurrence_min = settings.cooccurrence_confidence_min
    rels_created = 0
    rels_dropped = 0
    dropped_types: dict[str, int] = {}
    for rel_data in relationships:
        source_id = name_to_id.get(rel_data["source_name"])
        target_id = name_to_id.get(rel_data["target_name"])
        if not source_id or not target_id:
            # The model named an endpoint it never extracted as an entity. This
            # was silent, and it is how event dating stayed broken across a
            # 15-run campaign: OCCURRED_ON edges were emitted pointing at event
            # names that had no entity, so 22 of them survived out of 2,418
            # relationships and the timeline had nothing to sort by.
            rels_dropped += 1
            dropped_types[rel_data.get("rel_type", "?")] = (
                dropped_types.get(rel_data.get("rel_type", "?"), 0) + 1
            )
            continue
        confidence = rel_data.get("confidence", 0.5)
        # Blanket co-occurrence edges need a higher confidence bar to be
        # worth storing than typed/pattern-derived relationships — this is
        # what keeps a "these two entities appeared near each other" guess
        # from flooding the graph and skewing SNA/Graph-RAG. Doesn't affect
        # ASSOCIATED_WITH relationships an LLM asserted with real confidence.
        if rel_data["rel_type"] == "ASSOCIATED_WITH" and confidence < cooccurrence_min:
            continue
        rel = Relationship(
            source_id=source_id, target_id=target_id,
            rel_type=rel_data["rel_type"],
            confidence=confidence,
            source=rel_data.get("source", ""), method=rel_data.get("method", ""),
            # Carry the source-sentence evidence through to the edge (was dropped
            # here before, so "Show Evidence" had no real per-edge reference).
            evidence=rel_data.get("evidence", ""),
            # ...and the document it came from, so the evidence chain can end at
            # a real source instead of an unattributed quotation.
            source_doc_id=rel_data.get("source_doc_id", "") or source_doc_id,
            # "denies" marks contradicting reporting; the store turns an
            # assert/deny collision into CONFLICT instead of more agreement.
            polarity=("denies" if str(rel_data.get("polarity", "")).lower() == "denies" else "asserts"),
        )
        store.create_relationship(rel)
        rels_created += 1

    # Selective auto-enrich of newly-created cyber nodes (fire-and-forget,
    # default-off, gated inside the hook). Never let it affect the build.
    # auto_enrich_loop lets callers that run this via asyncio.to_thread (which has
    # no running loop) hand the pass back to their event loop.
    try:
        from intel_platform.enrichment.hook import schedule_auto_enrich
        schedule_auto_enrich(store, new_entities, loop=auto_enrich_loop)
    except Exception:
        pass

    if rels_dropped:
        # Surfaced rather than swallowed: a build that discards a third of its
        # relationships looks identical to one that never produced them.
        logger.warning(
            "Dropped %d relationship(s) naming entities that were never extracted: %s",
            rels_dropped, dropped_types,
        )

    return {
        "entities_created": created,
        "entities_merged": merged,
        "entities_filtered": entities_filtered,
        "relationships_created": rels_created,
        "relationships_dropped": rels_dropped,
        "relationships_dropped_by_type": dropped_types,
    }
