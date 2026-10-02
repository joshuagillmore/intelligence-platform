from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import spacy

from intel_platform.data import (
    get_known_locations, get_known_organizations, get_known_persons,
    get_known_acronyms, get_noise_words, get_location_keywords,
    get_org_keywords, get_tlds,
)
from intel_platform.enrichment.observables import refang
from intel_platform.models.type_hierarchy import normalize_entity_type
from intel_platform.services.geo.coordinates import parse_coordinates

logger = logging.getLogger(__name__)

_nlp = None


class ExtractionResult(tuple):
    """``(entities, relationships)`` for one chunk, plus how they were produced.

    Still a 2-tuple, so every ``ents, rels = await extract_...(...)`` caller is
    unchanged. The attributes are the per-chunk record that used to be missing:
    a chunk the model never read looked exactly like one it did.

    - ``method``: ``"hybrid" | "llm" | "nlp"`` — what actually ran.
    - ``degraded``: the requested method failed and this is the NLP fallback.
    - ``reason``: why it degraded (empty when it did not). Carries the exception
      *type*, never its message, so it is safe to show an analyst.
    - ``skipped_items``: individual model entities/relationships dropped for
      being malformed, without discarding the rest of the reply.
    - ``relationships_dropped_by_reason``: well-formed model relationships the
      extraction did not keep, by why: ``unlisted_endpoint`` (an endpoint that
      is neither a listed entity nor one's alias), ``same_entity`` (both ends
      resolve to one entity), ``generic_on_typed_pair`` (an ASSOCIATED_WITH on
      a pair a typed relation already links). The graph build keeps its own
      count of what reaches it.
    """

    method: str
    degraded: bool
    reason: str
    skipped_items: int
    relationships_dropped_by_reason: dict[str, int]

    def __new__(cls, entities: list[dict], relationships: list[dict], *, method: str,
                degraded: bool = False, reason: str = "", skipped_items: int = 0,
                relationships_dropped_by_reason: dict[str, int] | None = None):
        self = super().__new__(cls, (entities, relationships))
        self.method = method
        self.degraded = degraded
        self.reason = reason
        self.skipped_items = skipped_items
        self.relationships_dropped_by_reason = dict(relationships_dropped_by_reason or {})
        return self

    def __getnewargs_ex__(self):
        # copy and pickle rebuild a tuple subclass from tuple(self); without
        # this they call __new__ with one argument and fail.
        return (self[0], self[1]), {
            "method": self.method, "degraded": self.degraded,
            "reason": self.reason, "skipped_items": self.skipped_items,
            "relationships_dropped_by_reason": self.relationships_dropped_by_reason,
        }

    @property
    def meta(self) -> dict:
        return {
            "method": self.method,
            "degraded": self.degraded,
            "reason": self.reason,
            "skipped_items": self.skipped_items,
            "relationships_dropped_by_reason": dict(self.relationships_dropped_by_reason),
        }


class _LLMExtractionFailed(Exception):
    """The LLM half produced nothing usable; ``reason`` says why."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


SPACY_TO_ENTITY_TYPE = {
    "PERSON": "Person",
    "ORG": "Organization",
    "GPE": "Location",
    "LOC": "Location",
    "FAC": "Location",
    "EVENT": "Event",
    "NORP": "Organization",
    "DATE": "Date",
    "MONEY": "Financial",
    "QUANTITY": "Quantity",
    "PRODUCT": "Product",
    "LAW": "Document",
    "WORK_OF_ART": "Document",
}

# Regex patterns for cyber-specific entities
IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
_FALLBACK_TLDS = "com|org|net|io|gov|mil|edu|info|onion|ru|uk|de|nl|fr|ua|cn"
_domain_pattern_cache = None


# A percent-encoded separator leaves its hex pair attached to whatever follows.
# Share links carry a whole encoded URL in a query parameter —
# "linkedin.com/shareArticle?url=https%3A%2F%2Fcybelangel.com%2Fblog" — and the
# word boundary before "2F" lets it start a domain label, so the graph gained
# Domain nodes named "2fcybelangel.com", "2fwww.facebook.com" and
# "252fwww.faa.gov" (that one doubly encoded). Measured on a live graph: 31 of
# 1,483 domains. They then appeared in the Cyber view's IOC table as indicators.
_PERCENT_PREFIX = re.compile(r"^(?:25)*[0-9a-f]{2}(?=[a-z])", re.I)


def _strip_percent_prefix(domain: str, text: str, start: int) -> str:
    """Recover the real host from a match that began inside a %XX sequence.

    Only applies when the character immediately before the match is "%", so a
    domain legitimately starting with hex-looking characters ("2fa.example.com"
    written as itself) is untouched.
    """
    if start == 0 or text[start - 1] != "%":
        return domain
    stripped = _PERCENT_PREFIX.sub("", domain)
    # A label of nothing but the encoding is not a domain.
    return stripped if "." in stripped else ""


def _get_domain_pattern() -> re.Pattern:
    """Build domain regex from YAML TLD list (cached)."""
    global _domain_pattern_cache
    if _domain_pattern_cache is not None:
        return _domain_pattern_cache
    yaml_tlds = get_tlds()
    tld_alt = "|".join(yaml_tlds) if yaml_tlds else _FALLBACK_TLDS
    _domain_pattern_cache = re.compile(
        rf'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{{0,61}}[a-zA-Z0-9])?\.)+(?:{tld_alt})\b'
    )
    return _domain_pattern_cache


# Keep module-level pattern for backward compatibility (used if YAML not loaded)
DOMAIN_PATTERN = re.compile(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+(?:com|org|net|io|gov|mil|edu|info|onion|ru|uk|de|nl|fr|ua|cn)\b')
HASH_MD5 = re.compile(r'\b[a-fA-F0-9]{32}\b')
HASH_SHA1 = re.compile(r'\b[a-fA-F0-9]{40}\b')
HASH_SHA256 = re.compile(r'\b[a-fA-F0-9]{64}\b')
CVE_PATTERN = re.compile(r'\bCVE-\d{4}-\d{4,}\b')
MITRE_PATTERN = re.compile(r'\bT\d{4}(?:\.\d{3})?\b')
BTC_PATTERN = re.compile(r'\b(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,39}\b')
URL_PATTERN = re.compile(r"""https?://[^\s<>"')\]}]+""", re.IGNORECASE)
EMAIL_PATTERN = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b')

# Date patterns for intelligence documents
MONTH_NAMES = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
DATE_PATTERNS = [
    # "24 May 2023" — first, so the "May 2023" inside it is not taken as well.
    re.compile(rf'\b\d{{1,2}}\s+{MONTH_NAMES}\s+\d{{4}}\b'),
    # "May 7, 2021" or "May 2021"
    re.compile(rf'\b{MONTH_NAMES}\s+\d{{1,2}},?\s+\d{{4}}\b'),
    re.compile(rf'\b{MONTH_NAMES}\s+\d{{4}}\b'),
    # "2021-05-07" ISO format
    re.compile(r'\b\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b'),
    # "Q1 2026", "Q3 2021"
    re.compile(r'\bQ[1-4]\s+\d{4}\b'),
]

# What makes a span a date rather than a duration: a month or weekday name, a
# year, or a quarter. "6 months", "3 days earlier", "quarterly", "1742Z" and
# "the period" have none, cannot date an event, and reach the graph only as
# orphans the build discards.
_DATE_ANCHOR = re.compile(
    rf"\b(?:{MONTH_NAMES}|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec"
    r"|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b"
    r"|\b(?:1[89]|20)\d{2}\b|\bQ[1-4]\b",
    re.IGNORECASE,
)


def _is_datable(name: str) -> bool:
    return bool(_DATE_ANCHOR.search(name or ""))


def _drop_undatable_dates(entities: list[dict], relationships: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop Date entities that name no date, and the edges that point at them.

    An edge left pointing at a removed entity would be counted as a loss at
    graph build; it is removed with its endpoint instead.
    """
    gone = {e.get("name") for e in entities if e.get("entity_type") == "Date" and not _is_datable(e.get("name", ""))}
    if not gone:
        return entities, relationships
    return (
        [e for e in entities if e.get("name") not in gone],
        [r for r in relationships if r.get("source_name") not in gone and r.get("target_name") not in gone],
    )


# Fills in date components a match doesn't specify (e.g. "May 2021" has no
# day) so parses are deterministic instead of silently borrowing today's date.
_EVENT_DATE_PARSE_DEFAULT = datetime(2000, 1, 1)


def _date_precision(date_str: str) -> str:
    """How precise the source actually was: day, month or year.

    Parsed with two different defaults — a field the source did not state takes
    whichever default was supplied, so a field that moves between the two runs
    is one the text never specified.
    """
    from dateutil import parser as date_parser

    probe_a = datetime(1999, 1, 1, tzinfo=timezone.utc)
    probe_b = datetime(2011, 6, 15, tzinfo=timezone.utc)
    try:
        a = date_parser.parse(date_str.strip(), default=probe_a)
        b = date_parser.parse(date_str.strip(), default=probe_b)
    except (ValueError, OverflowError, TypeError):
        return ""
    if a.year != b.year:
        return ""  # no year stated at all — not a usable date
    if a.month != b.month:
        return "year"
    if a.day != b.day:
        return "month"
    return "day"


def _date_bounds(dt: datetime, precision: str) -> tuple[str, str]:
    """The interval a date of the given precision actually covers.

    "March 2026" is the whole of March, not midnight on the 1st. Collapsing it
    to a point is what puts a false spike on the 1st of every month in any
    histogram built from these values.
    """
    if precision == "year":
        start = dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start.replace(year=start.year + 1) - timedelta(microseconds=1)
    elif precision == "month":
        start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        nxt = start.replace(year=start.year + 1, month=1) if start.month == 12 \
            else start.replace(month=start.month + 1)
        end = nxt - timedelta(microseconds=1)
    else:
        start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(microseconds=1)
    return start.isoformat(), end.isoformat()


def _parse_event_date(date_str: str) -> str | None:
    """Best-effort parse of an extracted date string into an ISO datetime.

    Uses dateutil (already a project dependency — no new dep needed). Returns
    None rather than raising when the string isn't something dateutil can
    confidently resolve (e.g. "Q1 2026" — it has no month/day dateutil knows).
    """
    from dateutil import parser as date_parser

    try:
        dt = date_parser.parse(date_str.strip(), default=_EVENT_DATE_PARSE_DEFAULT)
    except (ValueError, OverflowError, TypeError):
        return None
    return dt.isoformat()


# Intelligence writing hedges and brackets dates far more than it states them
# outright. Measured against fourteen real phrasings, a bare dateutil parse
# resolved five; these forms account for most of the rest and every one of them
# carries a usable year.
_QUARTER = re.compile(r"\bQ([1-4])\s*,?\s*(?:of\s+)?(\d{4})\b", re.IGNORECASE)
_BETWEEN = re.compile(
    r"\bbetween\s+(.+?)\s+and\s+(.+)$", re.IGNORECASE,
)
_SINCE = re.compile(r"\b(?:since|from|after)\s+(.+)$", re.IGNORECASE)
_HEDGE = re.compile(
    r"\b(early|mid|late|beginning\s+of|start\s+of|end\s+of|middle\s+of)\b[\s\-]*",
    re.IGNORECASE,
)
# Which third of the period a hedge points at, as (start fraction, end fraction).
_HEDGE_SPAN = {
    "early": (0.0, 1 / 3), "beginning": (0.0, 1 / 3), "start": (0.0, 1 / 3),
    "mid": (1 / 3, 2 / 3), "middle": (1 / 3, 2 / 3),
    "late": (2 / 3, 1.0), "end": (2 / 3, 1.0),
}


def _plain(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _resolve_plain(text: str) -> tuple[str, str, str] | None:
    """(t_start, t_end, precision) for a date dateutil can take as written."""
    precision = _date_precision(text)
    if not precision:
        return None
    iso = _parse_event_date(text)
    if not iso:
        return None
    t_start, t_end = _date_bounds(_plain(iso), precision)
    return t_start, t_end, precision


def resolve_date_text(date_str: str) -> dict | None:
    """Resolve a date as written into an interval plus its stated precision.

    Returns ``None`` when the text carries no usable year — the honest answer
    for "last Tuesday" or "12 March" with no year in sight, which is better than
    silently anchoring to today. Reporting that omits the year is relying on its
    publication date to supply it, and that is not information this function has.
    """
    raw = (date_str or "").strip()
    if not raw:
        return None
    label = raw[:120]

    def out(t_start: str, t_end: str, precision: str) -> dict:
        return {
            "event_datetime": t_start,
            "t_start": t_start,
            "t_end": t_end,
            "date_precision": precision,
            "date_text": label,
        }

    # "Q1 2026" — a defined three-month span dateutil cannot read.
    q = _QUARTER.search(raw)
    if q:
        quarter, year = int(q.group(1)), int(q.group(2))
        start = datetime(year, 3 * (quarter - 1) + 1, 1, tzinfo=timezone.utc)
        end_month = start.month + 3
        end = (datetime(year + 1, end_month - 12, 1, tzinfo=timezone.utc)
               if end_month > 12 else datetime(year, end_month, 1, tzinfo=timezone.utc))
        return out(start.isoformat(), (end - timedelta(microseconds=1)).isoformat(), "month")

    # "between March and June 2026" — the trailing year governs both ends, so
    # the opening half is retried with it appended when it parses alone.
    b = _BETWEEN.search(raw)
    if b:
        left, right = b.group(1).strip(), b.group(2).strip()
        right_r = _resolve_plain(right)
        if right_r:
            left_r = _resolve_plain(left) or _resolve_plain(f"{left} {right_r[0][:4]}")
            if left_r:
                return out(left_r[0], right_r[1], right_r[2])
            return out(right_r[0], right_r[1], right_r[2])

    # "since 2024" — open at the right-hand end. `t_end` carries the bound of
    # the stated period; that the period continues is the reader's inference.
    s = _SINCE.search(raw)
    if s:
        inner = _resolve_plain(s.group(1).strip())
        if inner:
            return out(inner[0], inner[1], inner[2])

    # "early March 2026", "mid-2024" — resolve the underlying date, then narrow
    # to the third of the period the hedge points at.
    h = _HEDGE.search(raw)
    if h:
        stripped = _HEDGE.sub("", raw).strip()
        inner = _resolve_plain(stripped)
        if inner:
            t_start, t_end, precision = inner
            word = h.group(1).split()[0].lower()
            span = _HEDGE_SPAN.get(word)
            if span:
                start_dt, end_dt = _plain(t_start), _plain(t_end)
                total = (end_dt - start_dt).total_seconds()
                lo = start_dt + timedelta(seconds=total * span[0])
                hi = start_dt + timedelta(seconds=total * span[1])
                return out(lo.isoformat(), hi.isoformat(), precision)
            return out(t_start, t_end, precision)

    plain = _resolve_plain(raw)
    return out(*plain) if plain else None


def _link_event_dates(entities: list[dict], relationships: list[dict]) -> None:
    """Attach event_datetime to Event entities linked to a Date via OCCURRED_ON.

    Mutates `entities` in place. OCCURRED_ON is the relationship both the NLP
    co-occurrence heuristic (below) and the LLM skill prompt already use to
    connect an Event to a Date entity — this just resolves that Date's text
    into a real datetime so build_graph_from_extractions can populate
    Event.event_datetime (see models/entities.py) and the timeline can sort/
    display by real event time instead of falling back to ingestion time.
    Entities that can't be linked or parsed are left untouched (event_datetime
    stays null; callers fall back to created_at).
    """
    by_name = {e["name"]: e for e in entities if e.get("name")}
    for rel in relationships:
        if rel.get("rel_type") != "OCCURRED_ON":
            continue

        src_name = rel.get("source_name", "")
        tgt_name = rel.get("target_name", "")
        source = by_name.get(src_name)
        target = by_name.get(tgt_name)

        # Models emit this edge in either direction — "strike OCCURRED_ON
        # 12 March 2026" and "12 March 2026 OCCURRED_ON strike" both appear in
        # live output. Orient it so the Date is always the target.
        if source is not None and source.get("entity_type") == "Date" and (
            target is None or target.get("entity_type") != "Date"
        ):
            src_name, tgt_name = tgt_name, src_name
            source, target = target, source
            rel["source_name"], rel["target_name"] = src_name, tgt_name

        if target is None or target.get("entity_type") != "Date":
            continue

        # The event is very often named only in the relationship and never
        # extracted as an entity — measured live, this is the norm rather than
        # the exception, and graph_builder then drops the edge for having a
        # missing endpoint. That is why 22 OCCURRED_ON edges survived across a
        # 15-run campaign and the timeline had almost nothing to sort by.
        # Recover the event rather than losing the only temporal signal there is.
        if source is None and src_name.strip():
            source = {
                "name": src_name.strip(),
                "entity_type": "Event",
                "confidence": float(rel.get("confidence", 0.7) or 0.7),
                "source": rel.get("source", ""),
                "attributes": {},
            }
            entities.append(source)
            by_name[src_name] = source
        if source is None:
            continue

        _, parent_category = normalize_entity_type(source.get("entity_type", ""))
        if parent_category != "Event":
            continue
        if source.get("attributes", {}).get("event_datetime"):
            continue  # already resolved (e.g. by an earlier relationship)
        resolved = resolve_date_text(target["name"])
        if resolved:
            source.setdefault("attributes", {}).update(resolved)
            # The Date has now been absorbed into the entity it dates. Mark it
            # so the graph builder can drop the node: a date has no agency —
            # it cannot act, be targeted or be attributed — so as a node it
            # only ever dilutes centrality and returns useless Graph-RAG
            # context, while as a property it is directly filterable.
            target.setdefault("attributes", {})["_absorbed"] = True


def _merge_attributes(primary: dict, secondary: dict) -> None:
    """Copy attributes from `secondary` into `primary` without overwriting.

    Used when hybrid extraction matches an NLP entity to an LLM entity: the
    LLM entity wins the merge, but attributes only the NLP pass found (e.g.
    an event_datetime resolved via _link_event_dates) would otherwise be
    silently dropped.
    """
    extra = secondary.get("attributes")
    if not extra:
        return
    target = primary.setdefault("attributes", {})
    for k, v in extra.items():
        target.setdefault(k, v)


# Relationship types the graph accepts (mirror of GraphStore.VALID_REL_TYPES —
# keep in sync). LLM rel_types outside this set collapse to ASSOCIATED_WITH.
_VALID_REL_TYPES = frozenset({
    "ASSOCIATED_WITH", "BELONGS_TO", "LOCATED_AT", "COMMUNICATES_WITH",
    "RESOLVES_TO", "EXPLOITS", "USES", "TARGETS", "ATTRIBUTED_TO",
    "MENTIONED_IN", "MENTIONS", "PARENT_OF", "RELATED_TO", "ASSESSES",
    "SUPPORTED_BY", "SHARED_WITH", "OCCURRED_ON",
    "COMMANDED_BY", "FUNDED_BY", "SUPPLIED_BY", "DEPLOYED_AT",
})

# The LLM emits fine-grained subtypes; the graph + eval gold track them at a
# coarser canonical level. Map the umbrella subtypes down, keep analytically
# meaningful specifics (ThreatActor, Malware, Campaign, Vulnerability, TTP...)
# as-is.
_LLM_TYPE_CANON = {
    # Organization umbrella
    "governmentagency": "Organization", "intelligenceservice": "Organization",
    "militaryunit": "Organization", "ngo": "Organization", "bank": "Organization",
    "company": "Organization", "corporation": "Organization", "consortium": "Organization",
    "politicalparty": "Organization", "mediaoutlet": "Organization",
    "university": "Organization", "researchinstitute": "Organization",
    "criminalgroup": "Organization", "terroristgroup": "Organization",
    # Malware umbrella
    "backdoor": "Malware", "ransomware": "Malware", "trojan": "Malware",
    "botnet": "Malware", "malwarefamily": "Malware", "rootkit": "Malware",
    "c2server": "Infrastructure",
    # Maritime/air platforms the model emits that had no canonical mapping, so
    # they degraded to Custom in the graph builder and vessels never typed as
    # vessels. Ship/Aircraft are already valid Equipment types.
    "vessel": "Ship", "boat": "Ship", "tanker": "Ship", "cargoship": "Ship",
    "warship": "Ship", "frigate": "Ship", "destroyer": "Ship", "carrier": "Ship",
    "airplane": "Aircraft", "jet": "Aircraft", "helicopter": "Aircraft", "uav": "Drone",
    # Location umbrella
    "country": "Location", "city": "Location", "region": "Location",
    "facility": "Location", "base": "Location", "port": "Location",
    "island": "Location", "airbase": "Location", "embassy": "Location",
    "province": "Location", "district": "Location", "territory": "Location",
    "border": "Location", "reef": "Location",
    # Place subtypes the model invents ("Kirvo airfield" came back "Airfield"),
    # none of them a graph type, so each landed as Custom.
    "airfield": "Location", "airport": "Location", "harbour": "Location", "harbor": "Location",
    "naval base": "Location", "navalbase": "Location", "militarybase": "Location", "military base": "Location",
    "anchorage": "Location", "strait": "Location", "sea": "Location", "bay": "Location", "gulf": "Location",
    "peninsula": "Location", "coast": "Location", "coastline": "Location", "waterway": "Location",
    "river": "Location", "town": "Location", "village": "Location", "state": "Location",
    # Person umbrella
    "analyst": "Person", "operative": "Person", "diplomat": "Person",
    "commander": "Person", "politician": "Person", "scientist": "Person",
    "executive": "Person", "agent": "Person", "informant": "Person",
    # Equipment / naval. These previously mapped onto "Vessel" and
    # "EquipmentType", neither of which is a real graph type — they normalise to
    # parent "Other" and the graph builder then falls back to Custom. So every
    # ship, submarine, aircraft and drone landed as Custom. Map onto the types
    # the hierarchy actually defines under Equipment.
    "ship": "Ship", "submarine": "Submarine", "aircraft": "Aircraft",
    "drone": "Drone", "missile": "Weapon", "radar": "Radar",
    # Satellite/Vehicle/Hardware are graph types in their own right; these had
    # the same EquipmentType/MilitaryAsset mapping the comment above describes
    # and landed as Custom. Tank has no type of its own — a tank is a vehicle.
    # tests/test_llm_type_canon.py fails if a target here is not a graph type.
    "satellite": "Satellite", "artillery": "Weapon", "vehicle": "Vehicle",
    "hardware": "Hardware", "tank": "Vehicle",
    # Intelligence docs
    "report": "Document", "assessment": "Document", "briefing": "Document",
}


def _normalize_llm_entity_type(raw: str) -> str:
    """Map an LLM-emitted fine-grained type down to the canonical taxonomy."""
    if not raw:
        return "Person"
    return _LLM_TYPE_CANON.get(raw.strip().lower(), raw.strip())


# Naming conventions that identify a type more reliably than the model does.
# The taxonomy already offers Ship/Aircraft/Missile; the model reaches for
# "Custom" or "Organization" instead, so vessels never render as vessels.
_TYPE_HINTS: tuple[tuple[re.Pattern, str, tuple[str, ...]], ...] = (
    # Vessel prefixes: MV/MT/SS/USS/HMS/RFA/FGS, e.g. "MV Aurora Trader".
    (re.compile(r'^(MV|M/V|MT|M/T|SS|S/S|USS|USNS|HMS|HMAS|RFA|FGS|FS|INS)\s+\S', re.IGNORECASE),
     "Ship", ("Custom", "Organization", "Technology", "Person", "")),
    # Air platforms and UAV designators, e.g. "MQ-9 Reaper", "F/A-18".
    (re.compile(r'^(MQ|RQ|F/A|F-|SU-|MIG-|KC-|C-|P-8|E-3)\s?-?\d', re.IGNORECASE),
     "Aircraft", ("Custom", "Technology", "Organization", "")),
    # Ship classes by hull designation: "LHA", "LPD-27", "DDG-51". spaCy and
    # the model call them organizations and "Equipment".
    (re.compile(r'^(?:DDG|FFG|LPD|LHA|LHD|LSD|LCS|CG|CVN|SSN|SSBN|SSGN|LSM|LST|AOR|T-AO|TAOL|LCU)(?:[- ]?\d+)?$'),
     "Ship", ("Custom", "Organization", "Technology", "Person", "Location", "Product", "Equipment",
              "EquipmentType", "Vehicle", "")),
    # Missile designators: a name and a number, "Fateh-110", "Qiam-1".
    (re.compile(r'^(?!Covid|COVID)[A-Z][a-z]{2,10}-\d{1,4}[A-Z]?$'),
     "Weapon", ("Custom", "Organization", "Person", "Location", "Product", "Technology", "")),
    # Named operations: "Operation Hard Kill".
    (re.compile(r'^Operation\s+[A-Z]'), "Event", ("Custom", "Organization", "Location", "Person", "Product", "")),
    # A ship class named as one: "Constellation-class frigate", "Medium Landing
    # Ship (LSM) program", which the model types "Equipment".
    (re.compile(r'(?i).*?\b(?:[\w-]+-class|frigate|destroyer|corvette|cruiser|warship|submarine|'
                r'landing ship|amphibious ship|oiler)\b'),
     "Ship", ("Equipment", "EquipmentType", "Technology", "Custom", "Product", "Vehicle", "Organization",
              "Location", "Person", "")),
)

# Types outside the vocabulary that name no thing: the model files reporting
# sources, gradings, substances and abstractions under them ("Commercial
# reporting [DataSource]", "B2 [Indicator]", "fissile material [Material]",
# "uranium enrichment program [Program]"). None maps to a graph type.
_ABSTRACT_TYPES = frozenset({
    "source", "datasource", "indicator", "material", "concept", "activity", "duration", "program", "programme",
    "capability", "trend", "issue", "quote", "statement",
})


def _drop_abstract_types(entities: list[dict], relationships: list[dict]) -> tuple[list[dict], list[dict]]:
    """Drop entities of an abstract invented type, and the edges that point at them."""
    gone = {e.get("name") for e in entities if (e.get("entity_type") or "").strip().lower() in _ABSTRACT_TYPES}
    if not gone:
        return entities, relationships
    return (
        [e for e in entities if e.get("name") not in gone],
        [r for r in relationships if r.get("source_name") not in gone and r.get("target_name") not in gone],
    )


def _apply_type_hints(entities: list[dict]) -> list[dict]:
    """Re-type entities whose name follows an unambiguous naming convention.

    Only overrides types the model is known to over-use for these — never a
    confident, specific type it already chose correctly.
    """
    for ent in entities:
        name = (ent.get("name") or "").strip()
        if not name:
            continue
        current = (ent.get("entity_type") or "").strip()
        # A system binary is software whatever the model called it: Cohere
        # typed netsh, ntdsutil and wmic as TTPs ("living-off-the-land
        # techniques including netsh, ntdsutil and wmic"), which put a tool in
        # the technique column and left it unmatched against ATT&CK.
        if current != "Software" and _KNOWN_SOFTWARE_NAME.fullmatch(name):
            ent["entity_type"] = "Software"
            continue
        for pattern, better, overridable in _TYPE_HINTS:
            if current in overridable and pattern.match(name):
                ent["entity_type"] = better
                break
    return entities


# Head words that say what a name is, whatever else it contains.
_WEAPON_HEAD = re.compile(
    r"\b(?:Missiles?|Weapons? System|Projectiles?|Rockets?|Torpedo(?:es)?|Interceptors?|SRBMs?|MRBMs?|ICBMs?|"
    r"Glide Vehicle)$"
)
_ORG_HEAD = re.compile(r"\b(?:Company|Council|Corporation|Commission|Committee|Authority|Bank|Group|Ltd|Inc)$")

# Single all-caps words that head a section rather than name anything.
_HEADING_WORDS = frozenset({
    "BACKGROUND", "SUMMARY", "OUTLOOK", "ASSESSMENT", "JUDGEMENT", "JUDGMENT", "JUDGEMENTS", "JUDGMENTS",
    "CONCLUSION", "CONCLUSIONS", "INTRODUCTION", "OVERVIEW", "RECOMMENDATIONS", "ANNEX", "APPENDIX",
    "DISTRIBUTION", "CLASSIFICATION", "SECRET", "CONFIDENTIAL", "RESTRICTED", "UNCLASSIFIED", "NOTE",
    "COMMENT", "SOURCE", "SOURCES", "CONTEXT", "DISCUSSION", "SCOPE", "METHODOLOGY", "FINDINGS", "NAMES",
})

# Legal instruments written by number.
_DOCUMENT_REF = re.compile(
    r"\b(?:Executive Order(?:\s*\(E\.O\.\))?|E\.O\.)\s+\d{4,5}\b|\b(?:FY\s?\d{4}\s+)?NDAA\b"
)
# A name ending in what it is: an act, a resolution, a strategy, a treaty.
_DOCUMENT_NAME = re.compile(
    r"\b(?:Act(?: of \d{4})?|Resolution(?: \d+)?|Strategy|Threat Assessment|Plan of Action|Treaty|Accord|"
    r"Agreement|Doctrine)$"
)
_DOCUMENT_OVERRIDABLE = frozenset({"Organization", "Location", "Product", "Person", "Event", "Document", ""})

# spaCy labels whose spans are names, so a lower-case one is a misfire.
_NAME_LABELS = frozenset({"PERSON", "ORG", "GPE", "LOC", "FAC", "NORP", "PRODUCT", "EVENT"})

# Signal, navigation and collection-discipline acronyms spaCy tags as
# organizations ("ceases AIS transmission", "GNSS position jumps").
_TECHNICAL_ACRONYMS = frozenset({
    "AIS", "VHF", "UHF", "HF", "GNSS", "GPS", "SAR", "NIIRS", "SIGINT", "HUMINT", "IMINT",
    "GEOINT", "OSINT", "ELINT", "COMINT", "MASINT", "ISR", "EW", "UAV", "UAS", "IED",
    "C2", "C4ISR", "SATCOM", "RF",
    # Cyber and finance terms written in capitals: standards, protocols, tickers.
    "CVSS", "WHOIS", "IOC", "IOCS", "TTPS", "USDT", "USDC", "BTC", "XMR", "SWIFT",
})


# ── Vessels ──────────────────────────────────────────────────────────────────
# Reporting names a ship the way no other entity is named: with its pennant or
# hull number in brackets ("Ostravik (A-411)"), or right after what kind of
# vessel it is ("bulk carrier Mirenda", "patrol vessels Brenna and Sarn").
# spaCy reads those names as people and companies — on the exercise corpus it
# typed none of forty vessels a Ship — and the model does it often enough.

_HULL_NUMBER = re.compile(r"\b([A-Z][a-z][\w'-]*(?:\s[A-Z][a-z][\w'-]*){0,2})\s\(([A-Z]{1,3}-\d{2,4})\)")
# Bracketed references that look like hull numbers and are not.
_NOT_VESSELS = frozenset({
    "annex", "appendix", "form", "figure", "table", "exhibit", "section", "route",
    "grid", "highway", "road", "item", "page", "paragraph", "serial",
})
_VESSEL_NOUN = (
    r"(?i:vessels?|ships?|tankers?|freighters?|trawlers?|ferry|ferries|frigates?|corvettes?"
    r"|destroyers?|cruisers?|submarines?|tugs?|barges?|yachts?|cutters?|dhows?|boats?"
    r"|(?:bulk|ore|container|lng|lpg|aircraft|vehicle|car)\s+carriers?)"
)
# A capitalised name of up to three words. All-capitals words are not part of
# it, so "fishing vessel Ekhaven AIS gap" names Ekhaven, not "Ekhaven AIS".
_VESSEL_NAME = r"[A-Z][a-z][\w'-]*(?:\s[A-Z][a-z][\w'-]*){0,2}"
_VESSEL_AFTER_NOUN = re.compile(
    rf"\b{_VESSEL_NOUN}\s+({_VESSEL_NAME}(?:\s*(?:,\s*and|,|and)\s+{_VESSEL_NAME})*)"
)
_VESSEL_LIST_SPLIT = re.compile(r"\s*(?:,\s*and|,|\band)\s+")
# Types the vessel evidence may replace; never a specific one the model chose.
_VESSEL_OVERRIDABLE = frozenset({
    "", "Person", "Organization", "Location", "Custom", "Technology", "Vehicle", "Product",
    "Equipment", "EquipmentType", "Facility", "Hardware",
})


# A unit or body written with its designator ("Combined Task Force (CTF-150)")
# has the same shape as a hull number; its own name says what it is.
_UNIT_WORDS = frozenset({
    "force", "group", "command", "authority", "regiment", "battalion", "brigade", "division",
    "squadron", "agency", "ministry", "service", "unit", "wing", "fleet", "detachment", "corps",
    "army", "navy", "council", "committee",
})


def _hull_numbers(text: str) -> list[tuple[str, str]]:
    """(name, hull number) for every "Name (A-411)" in the text."""
    return [
        (m.group(1), m.group(2)) for m in _HULL_NUMBER.finditer(text or "")
        if m.group(1).lower() not in _NOT_VESSELS
        and not _UNIT_WORDS.intersection(m.group(1).lower().split())
    ]


def _vessel_names(text: str) -> set[str]:
    """Lower-cased names the text marks as vessels."""
    names = {name.lower() for name, _ in _hull_numbers(text)}
    for m in _VESSEL_AFTER_NOUN.finditer(text or ""):
        names.update(n.lower() for n in _VESSEL_LIST_SPLIT.split(m.group(1)) if n)
    return names


def _apply_vessel_hints(entities: list[dict], text: str) -> list[dict]:
    """Type as a Ship every entity the text itself marks as a vessel."""
    names = _vessel_names(text)
    if names:
        for ent in entities:
            if (ent.get("entity_type") or "") in _VESSEL_OVERRIDABLE \
                    and (ent.get("name") or "").strip().lower() in names:
                ent["entity_type"] = "Ship"
    return entities


# ── Software and hardware ────────────────────────────────────────────────────
# spaCy has no label for either, so a product reached the graph as whatever it
# guessed: "built-in Windows tools" made Windows a Location (LOC) and "A Netgear
# ProSAFE router" made the router line an Organization. The noun the name
# modifies is the evidence, and it is in the sentence.

# Windows system binaries and admin tools reported as living-off-the-land
# tooling. Matched as whole words, so "netshell" and "shellcode" are not tools.
_KNOWN_SOFTWARE = (
    "netsh", "ntdsutil", "wmic", "powershell", "psexec", "rundll32", "regsvr32",
    "certutil", "bitsadmin", "vssadmin", "mshta", "schtasks", "wevtutil", "nltest",
    "dsquery", "ldifde", "procdump", "plink", "cmd.exe",
)
_KNOWN_SOFTWARE_ALT = "|".join(re.escape(s) for s in _KNOWN_SOFTWARE)
_KNOWN_SOFTWARE_RE = re.compile(rf"(?<![\w.-])(?:{_KNOWN_SOFTWARE_ALT})(?:\.exe)?(?![\w-])", re.IGNORECASE)
_KNOWN_SOFTWARE_NAME = re.compile(rf"(?:{_KNOWN_SOFTWARE_ALT})(?:\.exe)?", re.IGNORECASE)

# Head nouns that make the name modifying them a product of that kind.
_HARDWARE_NOUNS = frozenset({
    "router", "device", "firewall", "appliance", "modem", "gateway", "camera", "switch", "nas",
})
_SOFTWARE_NOUNS = frozenset({
    "tool", "software", "application", "binary", "utility", "browser", "plugin", "library", "script",
})

# Vendors named on their own are companies. spaCy calls Cisco a GPE; and a
# vendor followed by a product noun must still not become the product.
_KNOWN_VENDORS = frozenset({
    "microsoft", "cisco", "netgear", "fortinet", "asus", "juniper", "ivanti", "citrix",
    "vmware", "sonicwall", "zyxel", "mikrotik", "tp-link", "d-link", "ubiquiti", "draytek",
    "hikvision", "dahua", "huawei", "zte", "palo alto networks", "f5", "solarwinds",
    "jetbrains", "atlassian", "progress", "kaseya", "barracuda", "sophos",
})


# "the Falcon Peak exercise", "the Red Sands exercise": the noun says it is an event.
_EVENT_NOUNS = frozenset({"exercise", "operation", "mission", "summit", "drill", "wargame"})


def _product_type(ent) -> str:
    """"Hardware", "Software" or "Event" when the noun this name modifies says so, else ""."""
    if ent.text.strip().lower() in _KNOWN_VENDORS:
        return ""
    root = ent.root
    head = root.head
    noun = ""
    if head.i >= ent.end and head.pos_ in ("NOUN", "PROPN") and root.dep_ in ("compound", "amod", "nmod"):
        noun = head.lemma_.lower()
    elif ent.end < len(ent.doc) and ent.doc[ent.end].pos_ == "NOUN":
        # The parse sometimes leaves the name heading its own phrase; the noun
        # written straight after it is still what the name is.
        noun = ent.doc[ent.end].lemma_.lower()
    if noun in _HARDWARE_NOUNS:
        return "Hardware"
    if noun in _SOFTWARE_NOUNS:
        return "Software"
    if noun in _EVENT_NOUNS and ent.label_ in ("ORG", "GPE", "LOC", "FAC", "PERSON", "EVENT", "PRODUCT"):
        return "Event"
    return ""


# What the model writes for a relationship the vocabulary already has. Only
# same-direction synonyms: "COMMANDS" is COMMANDED_BY reversed, and reversing
# an edge on a guess is worse than not storing it.
_REL_TYPE_SYNONYMS = {
    "LOCATED_AT": (
        "LOCATED_IN", "BASED_AT", "BASED_IN", "HEADQUARTERED_AT", "HEADQUARTERED_IN",
        "BERTHS_AT", "BERTHED_AT", "DOCKED_AT", "MOORED_AT", "POSITIONED_AT", "OCCURRED_AT", "OCCURRED_IN",
    ),
    "DEPLOYED_AT": ("DEPLOYED_TO", "DEPLOYED_IN", "STATIONED_AT", "STATIONED_IN"),
    "TARGETS": ("TARGETED", "ATTACKS", "ATTACKED", "COMPROMISED", "COMPROMISES", "BREACHED", "STRUCK"),
    "USES": ("USED", "EMPLOYS", "EMPLOYED", "LEVERAGES", "LEVERAGED", "OPERATES", "OPERATED", "DEPLOYS"),
    "EXPLOITS": ("EXPLOITED", "EXPLOITING"),
    "BELONGS_TO": ("MEMBER_OF", "PART_OF", "SUBORDINATE_TO", "ASSIGNED_TO", "UNIT_OF"),
    "ATTRIBUTED_TO": ("ATTRIBUTED", "LINKED_TO"),
    "COMMUNICATES_WITH": ("CONNECTS_TO", "CONNECTED_TO", "BEACONS_TO", "CONTACTED"),
    "RESOLVES_TO": ("RESOLVED_TO", "POINTS_TO"),
    "COMMANDED_BY": ("LED_BY",),
    "FUNDED_BY": ("FINANCED_BY", "SPONSORED_BY"),
    "SUPPLIED_BY": ("PROVIDED_BY",),
}
_REL_TYPE_CANON = {syn: canon for canon, syns in _REL_TYPE_SYNONYMS.items() for syn in syns}

# Types that state something about the reporting, not a relationship between
# the two entities: "Source REPORTED Ostravik", "Imagery DOES_NOT_ESTABLISH
# Intent", "Identities BASED_ON Berth assignment". 41 of the 43 off-vocabulary
# edges in the corpus baseline were of this kind.
_REPORTING_REL = re.compile(
    r"^(?:REPORT|OBSERV|IDENTIF|ESTABLISH|DOES_NOT_|DID_NOT_|NOT_|UNABLE_|CANNOT_|INDICAT|CORROBORAT"
    r"|CONFIRM|PUBLISH|BASED_ON|DENIE|REQUESTED)"
)


def _normalize_rel_type(raw: str) -> str | None:
    """The vocabulary type a model relationship type means, or None.

    A synonym keeps its type: "BERTHS_AT" is LOCATED_AT, and collapsing it to
    ASSOCIATED_WITH threw away the one thing the sentence said. A statement
    about the reporting ("REPORTED", "DOES_NOT_ESTABLISH") returns None:
    storing it as ASSOCIATED_WITH asserted an association the model never
    made. Any other unlisted type ("PARTNERS_WITH") is still a relationship
    between the two, and stays the generic association it always was.
    """
    rt = re.sub(r"[\s-]+", "_", (raw or "").strip().upper())
    if rt in _VALID_REL_TYPES:
        return rt
    if rt in _REL_TYPE_CANON:
        return _REL_TYPE_CANON[rt]
    if _REPORTING_REL.match(rt):
        return None
    return "ASSOCIATED_WITH"


def _resolve_endpoints(
    entities: list[dict], relationships: list[dict], *,
    pool: list[dict] | None = None, renamed: dict[str, str] | None = None,
) -> tuple[list[dict], dict[str, int], list[dict]]:
    """Point every relationship at a listed entity, or drop it.

    An endpoint resolves when it is an entity's name, or the same name or one
    of its aliases written differently (``_merge_key``: case and surrounding
    space, the rule the hybrid merge matches by). In hybrid, ``renamed`` maps
    an NLP name to the model entity it merged into, and ``pool`` is the NLP
    entities: an endpoint the model named without listing but NLP extracted is
    that entity, which joins ``entities`` (and is returned) so the edge has
    both ends. Anything else is a name the model never listed ("Ukrainian
    forces", "31 larger amphibious ships"); the graph build used to drop those
    edges as unknown endpoints, after the eval had counted them.

    Returns the kept relationships, the drops by reason (``unlisted_endpoint``,
    ``same_entity`` when both ends resolve to one entity) and the pool
    entities added.
    """
    names = {e.get("name") for e in entities}
    lookup: dict[str, str] = {}
    for e in entities:
        lookup.setdefault(_merge_key(e.get("name", "")), e["name"])
    for e in entities:
        for alias in e.get("aliases") or []:
            if isinstance(alias, str) and alias.strip():
                lookup.setdefault(_merge_key(alias), e["name"])
    pool_by_key: dict[str, dict] = {}
    for e in pool or []:
        pool_by_key.setdefault(_merge_key(e.get("name", "")), e)
    for e in pool or []:
        for alias in e.get("aliases") or []:
            if isinstance(alias, str) and alias.strip():
                pool_by_key.setdefault(_merge_key(alias), e)
    added: list[dict] = []

    def resolve(name: str) -> str | None:
        if name in names:
            return name
        if renamed and renamed.get(name) in names:
            return renamed[name]
        key = _merge_key(name)
        if not key:
            return None
        if key in lookup:
            return lookup[key]
        found = pool_by_key.get(key)
        if found is None:
            return None
        if found.get("name") not in names:
            entities.append(found)
            added.append(found)
            names.add(found["name"])
            lookup.setdefault(_merge_key(found["name"]), found["name"])
        return found["name"]

    kept: list[dict] = []
    dropped = {"unlisted_endpoint": 0, "same_entity": 0}
    for r in relationships:
        src = resolve(r.get("source_name") or "")
        tgt = resolve(r.get("target_name") or "")
        if src is None or tgt is None:
            dropped["unlisted_endpoint"] += 1
            continue
        if src == tgt:
            dropped["same_entity"] += 1
            continue
        if (src, tgt) != (r.get("source_name"), r.get("target_name")):
            r = {**r, "source_name": src, "target_name": tgt}
        kept.append(r)
    if dropped["unlisted_endpoint"]:
        logger.info("Extraction dropped %d relationship(s) naming an entity that was not listed",
                    dropped["unlisted_endpoint"])
    return kept, dropped, added


# ── A country and its government are one entity ─────────────────────────────
# data/governments.yaml lists each country's names, its government forms and
# its capital. A capital stands for the state only where the text uses it as
# an actor; these are the dependency positions that say which.

# Nouns that make a capital in a phrase with them the state: "the regimes in
# Minsk and Moscow", "the Tehran government".
_GOVERNMENT_NOUNS = frozenset({
    "government", "regime", "leadership", "authority", "official", "administration", "embassy",
})
# Nouns that make a capital possessing them a place: "Tehran's streets".
_PLACE_NOUNS = frozenset({
    "street", "airport", "resident", "population", "mayor", "outskirt", "suburb", "centre", "center",
    "university", "bazaar", "district", "neighborhood", "neighbourhood", "metro", "skyline", "province",
    "hotel", "port", "harbour", "harbor", "square", "skies", "sky", "residents",
})
# Prepositions whose object is somewhere ("talks in Tehran", "flew from
# Beijing", "visits to Beijing") or someone ("talks with Tehran").
_PLACE_PREPOSITIONS = frozenset({
    "in", "at", "near", "from", "to", "into", "inside", "outside", "around", "across", "throughout", "via",
    "through", "over", "within", "toward", "towards",
})
_ACTOR_PREPOSITIONS = frozenset({"with", "against", "between"})
# Verbs whose object is a place: "visited Beijing", "struck Kyiv".
_PLACE_VERBS = frozenset({
    "visit", "leave", "reach", "enter", "tour", "flee", "evacuate", "arrive", "return", "fly", "travel",
    "bomb", "strike", "shell", "capture", "besiege", "surround", "approach", "host",
})


def _capital_use(token, depth: int = 0) -> str:
    """"actor", "place" or "" for one mention of a capital, from its parse."""
    dep = token.dep_
    head = token.head
    if dep in ("nsubj", "nsubjpass", "agent", "csubj"):
        return "actor"
    if dep == "poss":
        return "place" if head.lemma_.lower() in _PLACE_NOUNS else "actor"
    if dep == "compound":
        return "actor" if head.lemma_.lower() in _GOVERNMENT_NOUNS else "place"
    if dep == "pobj":
        prep = head.lower_
        if head.head.lemma_.lower() in _GOVERNMENT_NOUNS:
            return "actor"
        if prep in _ACTOR_PREPOSITIONS:
            return "actor"
        if prep in _PLACE_PREPOSITIONS:
            return "place"
        return ""
    if dep == "dobj":
        return "place" if head.lemma_.lower() in _PLACE_VERBS else "actor"
    if dep in ("conj", "appos") and depth < 3 and head is not token:
        # "the regimes in Minsk and Moscow": Moscow is used as Minsk is.
        return _capital_use(head, depth + 1)
    return ""


def _capital_metonyms(text: str, doc=None) -> set[str]:
    """The table's capitals this text uses for their state more often than as a place.

    "Tehran asserts its enrichment program ...", "Beijing's insistence on
    unification" and "the regimes in Minsk and Moscow" are the state;
    "discussions in Tehran" and "two secret visits to Beijing" are the city.
    Counted over every mention, so a text that does both resolves to the use
    it makes most; a tie stays a place. Parses the text when the caller has no
    parse of it, and only when it names a capital.
    """
    from intel_platform.services.text_utils import capital_names

    capitals = [c for c in capital_names() if re.search(r"(?<!\w)" + re.escape(c) + r"(?!\w)", text or "")]
    if not capitals:
        return set()
    try:
        if doc is None:
            doc = _get_nlp()(text)
    except Exception:
        # Without a parse the capital stays a place: the safe reading.
        logger.warning("Could not parse the text to read how it uses a capital", exc_info=True)
        return set()
    found: set[str] = set()
    for capital in capitals:
        uses = {"actor": 0, "place": 0}
        for m in re.finditer(r"(?<!\w)" + re.escape(capital) + r"(?!\w)", doc.text):
            span = doc.char_span(m.start(), m.end(), alignment_mode="expand")
            use = _capital_use(span.root) if span is not None else ""
            if use:
                uses[use] += 1
        if uses["actor"] > uses["place"]:
            found.add(capital)
    return found


def _country_name_in_text(country: str, text: str) -> str:
    """The name the text itself gives the country, else the table's."""
    from intel_platform.services.text_utils import country_names

    for name in country_names(country):
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text or ""):
            return name
    return country


def _add_alias(entity: dict, alias: str) -> None:
    if not alias or alias == entity.get("name"):
        return
    aliases = list(entity.get("aliases") or [])
    if alias not in aliases:
        aliases.append(alias)
    entity["aliases"] = aliases


def _resolve_countries(
    entities: list[dict], relationships: list[dict], text: str, doc=None,
) -> tuple[list[dict], list[dict], int]:
    """One entity per state: its names, its government forms and a capital acting for it.

    The model named "PRC government" where NLP named "China" and "PRC"; the
    graph got a node for each, and the gold makes them one. Every Location or
    Organization entity the table resolves to a country joins that country's
    entity: the first one named as the country itself, or, when only a form
    is named, the first form, renamed to the country as the text names it.
    The others become its aliases, the entity is a Location (as the gold
    types countries), and edges follow it. A capital joins only when the text
    uses it as the state (``_capital_metonyms``).

    Returns the entities, the relationships, and how many edges were dropped
    because both ends became the one entity.
    """
    from intel_platform.services.text_utils import country_of

    metonyms: set[str] | None = None
    groups: dict[str, list[tuple[dict, str]]] = {}
    for e in entities:
        _, parent = normalize_entity_type(e.get("entity_type") or "")
        if parent not in ("Location", "Organization"):
            continue
        hit = country_of(e.get("name") or "")
        if hit is None:
            continue
        country, kind = hit
        if kind == "capital":
            if metonyms is None:
                metonyms = {c.lower() for c in _capital_metonyms(text, doc)}
            if (e.get("name") or "").strip().lower() not in metonyms:
                continue
        groups.setdefault(country, []).append((e, kind))
    if not groups:
        return entities, relationships, 0

    renamed: dict[str, str] = {}
    gone: set[int] = set()
    for country, members in groups.items():
        named = [e for e, kind in members if kind == "name"]
        keep = named[0] if named else members[0][0]
        if not named:
            written = keep["name"]
            keep["name"] = _country_name_in_text(country, text)
            _add_alias(keep, written)
            renamed[written] = keep["name"]
        keep["entity_type"] = "Location"
        for e, _ in members:
            if e is keep:
                continue
            for alias in [e.get("name", ""), *(e.get("aliases") or [])]:
                if isinstance(alias, str):
                    _add_alias(keep, alias)
            keep["confidence"] = max(keep.get("confidence", 0) or 0, e.get("confidence", 0) or 0)
            _merge_attributes(keep, e)
            renamed[e.get("name", "")] = keep["name"]
            gone.add(id(e))
    if gone:
        logger.debug("Resolved %d government form(s) and name(s) to their country", len(gone))
    entities = [e for e in entities if id(e) not in gone]

    kept: list[dict] = []
    same = 0
    for r in relationships:
        src = renamed.get(r.get("source_name"), r.get("source_name"))
        tgt = renamed.get(r.get("target_name"), r.get("target_name"))
        if src == tgt:
            same += 1
            continue
        if (src, tgt) != (r.get("source_name"), r.get("target_name")):
            r = {**r, "source_name": src, "target_name": tgt}
        kept.append(r)
    return entities, kept, same


def _drop_generic_on_typed_pairs(relationships: list[dict]) -> tuple[list[dict], int]:
    """Drop each ASSOCIATED_WITH on a pair that an asserted typed relation links.

    A generic association says two things are related without saying how; next
    to an edge that says how, it adds nothing. The model returned Iran TARGETS
    and ASSOCIATED_WITH the Strait of Hormuz; hybrid kept the model's Russia
    ASSOCIATED_WITH Ukraine beside NLP's TARGETS for "Russia's 2022 invasion of
    Ukraine". Direction does not matter; a denied typed relation does not rule
    an association out. Returns the kept edges and how many were dropped.
    """
    typed = {
        frozenset((r.get("source_name"), r.get("target_name"))) for r in relationships
        if r.get("rel_type") != "ASSOCIATED_WITH" and r.get("polarity", "asserts") != "denies"
    }
    kept = [
        r for r in relationships
        if r.get("rel_type") != "ASSOCIATED_WITH"
        or frozenset((r.get("source_name"), r.get("target_name"))) not in typed
    ]
    return kept, len(relationships) - len(kept)


def _clean_evidence(sentence: str, name_a: str, name_b: str, pad: int = 45, max_len: int = 300) -> str:
    """Tighten a relationship's source text to the in-context span linking the pair.

    spaCy sentence boundaries are noisy on intelligence docs (headers without
    terminal punctuation get glued onto the first real sentence), so the raw
    `sent.text` is often a multi-line boilerplate blob. Collapse whitespace and,
    when both entity names are present, clip to a window around them so "Show
    Evidence" surfaces the actual related reference, not a page of preamble.
    """
    s = re.sub(r"\s+", " ", sentence or "").strip()
    if not s:
        return ""
    lo = s.lower()
    ia, ib = lo.find(name_a.lower()), lo.find(name_b.lower())
    if ia != -1 and ib != -1:
        start = max(0, min(ia, ib) - pad)
        end = min(len(s), max(ia + len(name_a), ib + len(name_b)) + pad)
        clip = ("..." if start > 0 else "") + s[start:end] + ("..." if end < len(s) else "")
        return clip
    return s if len(s) <= max_len else s[:max_len] + "..."

# Known intelligence-domain locations that spaCy commonly misclassifies
KNOWN_LOCATIONS = {
    "caspian sea", "black sea", "red sea", "mediterranean", "south china sea",
    "east china sea", "persian gulf", "gulf of aden", "indian ocean", "pacific ocean",
    "atlantic ocean", "arctic ocean", "strait of hormuz", "strait of malacca",
    "bab el-mandeb", "suez canal", "panama canal",
    # Countries commonly misclassified
    "iran", "iraq", "syria", "yemen", "libya", "sudan", "somalia",
    "azerbaijan", "georgia", "armenia", "kazakhstan", "uzbekistan",
    "tajikistan", "turkmenistan", "kyrgyzstan", "belarus", "moldova",
    # Cities commonly misclassified
    "alabuga", "astrakhan", "voronezh", "mozdok", "sevastopol",
    "mariupol", "kherson", "dnipro", "odesa", "zaporizhzhia",
    "isfahan", "tehran", "bandar anzali", "bandar abbas",
    "tartus", "latakia", "aleppo", "homs",
    "tatarstan", "north ossetia", "dagestan", "chechnya",
    "mozdok", "mozdok airbase", "naha air base",
    "kyiv", "kharkiv", "odesa", "lviv", "donetsk", "luhansk",
}

# Keywords that indicate an entity is a location, not a person
LOCATION_KEYWORDS = [
    "Airbase", "Air Base", "Port", "Island", "Islands", "Reef",
    "Strait", "Gulf", "Sea", "Ocean", "Bay", "Province", "Region",
    "District", "Base", "Camp",
]

# Known intelligence-domain organizations that spaCy commonly misclassifies
KNOWN_ORGANIZATIONS = {
    "irgc", "fsb", "gru", "svr", "cia", "nsa", "fbi", "mi6", "mi5",
    "mossad", "dgse", "bnd", "isi", "raw", "asis",
    "nato", "aukus", "five eyes", "quad",
    "united nations", "african union", "european union", "asean",
    "plan", "pla", "plaaf",
}

# Keywords that indicate an entity is an organization, not a person
ORG_KEYWORDS = [
    "Force", "Ministry", "Guard", "Corps", "Command", "Agency", "Bureau",
    "Department", "Institute", "University", "Company", "Corp", "Inc",
    "Committee", "Council", "Union", "Alliance", "Coalition",
    "Industries", "Aviation", "Fleet", "Navy", "Army", "Air Force",
    "Brigade", "Division", "Regiment", "Battalion",
]

# Known intelligence-domain person names that spaCy commonly misclassifies
KNOWN_PERSONS = {
    "vasily nebenzya", "sergei lavrov", "vladimir putin", "joe biden",
    "volodymyr zelensky", "xi jinping", "kim jong un", "ali khamenei",
    "benjamin netanyahu", "antonio guterres", "jens stoltenberg",
}

# Words that spaCy commonly misidentifies as entities
KNOWN_ACRONYMS = {
    "NATO", "AUKUS", "ASEAN", "IRGC", "PLAN", "PLAAF", "ISIS",
    "IAEA", "OPEC", "BRICS", "CSIS", "RAND", "CISA", "NSA", "CIA", "FBI",
    "GRU", "FSB", "SVR", "MI6", "MI5", "DIA", "NGA", "GCHQ",
}

NOISE_WORDS = {
    "NETWORK", "INFRASTRUCTURE", "ASSESSMENT", "ANALYSIS", "REPORT",
    "NOTE", "SUBJECT", "SUMMARY", "FINDINGS", "GAPS", "KEY",
    "Backup C2", "Primary", "Secondary", "Administrative", "Sea",
    "Bitcoin", "Monero", "Ethereum", "Cryptocurrency",
    "VPS", "CDN", "API", "HTTP", "HTTPS", "DNS", "TCP", "UDP",
    "IP", "URL", "PDF", "CSV", "JSON", "XML",
    "LIKELY", "UNLIKELY", "VERY LIKELY", "ALMOST CERTAIN", "ROUGHLY EVEN CHANCE",
    "VERY UNLIKELY", "ALMOST NO CHANCE",
    "Defense", "INTELLIGENCE", "OPEN SOURCE", "TECHNICAL",
    "EXECUTIVE", "FINANCIAL", "DIPLOMATIC",
}


def _get_nlp():
    global _nlp
    if _nlp is None:
        from intel_platform.config import settings
        model_name = settings.spacy_model
        try:
            _nlp = spacy.load(model_name)
        except OSError:
            # Fallback to small model if configured model not installed
            _nlp = spacy.load("en_core_web_sm")
    return _nlp


# Co-occurrence is a last-resort guess, not the default: cap how many
# trailing neighbors in a sentence's entity list each entity pairs with, so a
# dense sentence (many named entities) produces O(n) fallback edges instead
# of the full O(n^2) cross-product. This still keeps every entity in a
# sentence connected via the resulting chain (useful for graph traversal)
# without the quadratic edge count that was flooding the graph with noise
# (eval: 45 predicted vs 15 expected relationships on cyber_threat_report_1,
# driven by this blowup). 2 was chosen over a stricter window of 1 because it
# was the smallest value that didn't drop any true positives across the eval
# fixture set — some genuine ASSOCIATED_WITH pairs (e.g. two officials named
# together with an intervening Date/Location mention) are 2 apart, not 1.
COOCCURRENCE_WINDOW = 2

HASH_CONTEXT_KEYWORDS = re.compile(
    r'\b(?:hash|md5|sha1|sha256|sha-1|sha-256|checksum|ioc|indicator|malware|sample|binary|payload|artifact)\b',
    re.IGNORECASE,
)

# UUID pattern to exclude from hash matching
UUID_PATTERN = re.compile(r'[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}')


def _has_hash_context(text: str, match_start: int, match_end: int) -> bool:
    """Check if a hash match has contextual keywords nearby (within ~200 chars)."""
    window_start = max(0, match_start - 200)
    window_end = min(len(text), match_end + 200)
    window = text[window_start:window_end]
    return bool(HASH_CONTEXT_KEYWORDS.search(window))


#: A defang marker — every form ``enrichment.observables.refang`` reverses:
#: a bracketed, parenthesised or braced dot, at or colon (``[.] (.) {.} [dot]
#: (dot) [at] (at) [@] [:] (:)``), or an ``hxxp`` scheme. Listing fewer than
#: refang handles meant ``evil{.}com`` or ``ops(at)evil(dot)com`` were refanged
#: into indicators but not counted as defanged.
_DEFANG_MARKER = re.compile(
    r"[\[\(\{]\s*(?:\.|dot|@|at|:)\s*[\]\)\}]|h[x]{2}ps?(?::|[\[\(\{]\s*:\s*[\]\)\}])//",
    re.IGNORECASE,
)
_NON_SPACE_RUN = re.compile(r"\S+")
#: Trailing punctuation that ends a URL match rather than belonging to it.
_URL_TRAILING = ".,;:!?)]}'\""


def _defanged_values(raw_text: str) -> set[str]:
    """Values the author defanged, refanged and normalised for comparison.

    Works on the whole whitespace-delimited token carrying a marker, so a
    defanged host inside an otherwise ordinary URL (``http://evil[.]com/gate.php``)
    records the URL as well as the host — the old detector stopped at the host,
    and the URL was then discarded as an undefanged citation. Values are read
    back out of the refanged token with the same patterns the extractor uses,
    so what is recorded here compares equal to what is extracted there.
    """
    found: set[str] = set()
    for run in _NON_SPACE_RUN.finditer(raw_text or ""):
        token = run.group()
        if not _DEFANG_MARKER.search(token):
            continue
        value = refang(token)
        for m in URL_PATTERN.finditer(value):
            found.add(m.group().rstrip(_URL_TRAILING).lower())
        for m in EMAIL_PATTERN.finditer(value):
            found.add(m.group().lower())
        # Hosts, including the host of every URL and address above, so the
        # Domain check sees the assertion made about them.
        for m in _get_domain_pattern().finditer(value):
            found.add(m.group().lower())
        for m in IP_PATTERN.finditer(value):
            found.add(m.group())
    return found


def _is_sourcing_not_content(name: str, start: int, url_spans: list[tuple[int, int]],
                             defanged: set[str]) -> bool:
    """Whether this host is where the document came from rather than what it is about.

    A hostname inside a hyperlink is provenance: the citation, the nav bar, the
    cookie banner, the "share on" link. Minting an entity for it is what filled
    one project with 2,653 URL nodes — 98% of them isolated — and put bbc.com
    and apps.apple.com in a threat-indicator table.

    A hostname standing alone in prose is the opposite: something the author
    wrote out because the document is *about* it. Every Domain in the labelled
    fixtures is of this kind — all 8 standalone, none inside a URL — so this
    distinction costs no recall on the cases we have ground truth for.

    Defanging overrides both: an author who writes ``evil[.]com`` has asserted
    that it is an indicator, wherever it appears.
    """
    if name in defanged:
        return False
    return any(s <= start < e for s, e in url_spans)


def _drop_model_sourcing(entities: list[dict], raw_text: str) -> list[dict]:
    """Apply the sourcing rule above to the model's Domain and URL entities.

    The regex pass has always declined to mint a host that only appears inside
    a hyperlink, or an undefanged URL; the model, reading the same citation,
    minted both. Here the same rule judges what it returns:

    - a URL survives only if the author defanged it;
    - a host survives if it is defanged, or appears at least once outside a
      link. A host the text never states is not judged — the model may have
      normalised it — and is kept.
    """
    if not any(e.get("entity_type") in ("Domain", "URL") for e in entities):
        return entities
    defanged = _defanged_values(raw_text)
    text = refang(raw_text or "").lower()
    url_spans = [m.span() for m in URL_PATTERN.finditer(text)]

    def _only_inside_links(host: str) -> bool:
        # A dot may precede the host (so bbc.com is found in www.bbc.com); a
        # label character may not (so evil.com is not found in notevil.com).
        pattern = re.compile(r"(?<![a-z0-9-])" + re.escape(host) + r"(?![a-z0-9-])")
        starts = [m.start() for m in pattern.finditer(text)]
        return bool(starts) and all(any(s <= p < e for s, e in url_spans) for p in starts)

    kept = []
    for e in entities:
        etype = e.get("entity_type")
        value = refang(str(e.get("name", ""))).strip().lower()
        if etype == "URL" and value.rstrip(_URL_TRAILING) not in defanged:
            logger.debug("Dropping model URL %r: an undefanged link is provenance", e.get("name"))
            continue
        if etype == "Domain" and value not in defanged and _only_inside_links(value):
            logger.debug("Dropping model Domain %r: it appears only inside links", e.get("name"))
            continue
        kept.append(e)
    return kept


_INDICATOR_TYPES = frozenset({"Domain", "URL", "IPAddress", "EmailAddress"})


def _refang_model_indicators(entities: list[dict], relationships: list[dict]) -> None:
    """Store a model-returned indicator under its canonical, refanged value.

    The model returns "evil-c2[.]com" as the text wrote it. The regex pass
    stores "evil-c2.com", so the two never merged; and graph_builder's host
    check raised on the bracket, failing the whole build. The written form is
    kept as an alias and the relationships are renamed with it.
    """
    renamed: dict[str, str] = {}
    for e in entities:
        if e.get("entity_type") not in _INDICATOR_TYPES:
            continue
        name = e.get("name") or ""
        canonical = refang(name).strip()
        if canonical and canonical != name:
            renamed[name] = canonical
            e["name"] = canonical
            aliases = list(e.get("aliases") or [])
            if name not in aliases:
                aliases.append(name)
            e["aliases"] = aliases
    if renamed:
        for r in relationships:
            r["source_name"] = renamed.get(r.get("source_name"), r.get("source_name"))
            r["target_name"] = renamed.get(r.get("target_name"), r.get("target_name"))


def _extract_cyber_entities(text: str, doc_id: str, raw_text: str | None = None) -> list[dict]:
    """Extract cyber-specific entities using regex patterns.

    ``raw_text`` is the text before refang, when the caller has it.
    ``extract_entities_nlp`` refangs up front so spaCy and the relationship
    matcher see canonical text, which erases the defang markers this function
    needs; it therefore passes the original. Callers that hand over untouched
    text can omit it.
    """
    # Which values the author deliberately obfuscated, captured *before* refang
    # destroys the evidence. Defanging is a positive assertion that a value is
    # an indicator, and it is the only such signal the text carries.
    deliberately_defanged = _defanged_values(raw_text if raw_text is not None else text)

    # Reverse common defang notation (evil[.]com, hxxp://, a[at]b[.]com) first so
    # the patterns below catch IOCs that threat-intel text deliberately obfuscates.
    text = refang(text)

    # Where the document cites its sources. A host inside a hyperlink is how the
    # document was assembled, not something it is reporting on — see
    # _is_sourcing_not_content below.
    url_spans = [m.span() for m in URL_PATTERN.finditer(text)]

    cyber_entities = []
    seen = set()

    # Collect SHA-256 matches first (longest hashes) so shorter matches can be skipped
    sha256_spans = set()

    for match in IP_PATTERN.finditer(text):
        ip = match.group()
        # Validate octets
        octets = ip.split(".")
        if all(0 <= int(o) <= 255 for o in octets) and ip not in seen:
            seen.add(ip)
            cyber_entities.append({
                "name": ip, "entity_type": "IPAddress",
                "source": doc_id, "method": "regex", "confidence": 0.95,
            })

    for match in _get_domain_pattern().finditer(text):
        domain = _strip_percent_prefix(match.group().lower(), text, match.start())
        if not domain or domain in seen or "." not in domain:
            continue
        if _is_sourcing_not_content(domain, match.start(), url_spans, deliberately_defanged):
            continue
        seen.add(domain)
        cyber_entities.append({
            "name": domain, "entity_type": "Domain",
            "source": doc_id, "method": "regex",
            # A defanged host was asserted to be an indicator; a bare one in
            # prose is inferred to be. Say which, rather than calling both 0.9.
            "confidence": 0.95 if domain in deliberately_defanged else 0.9,
        })

    # URLs are minted only when defanged. An ordinary http(s) link is where the
    # document came from — a citation, a footer, a "read more" — and the labelled
    # fixtures agree: across all twelve, the expected URL count is zero. A
    # defanged one (hxxps://evil[.]com/gate.php) is the exception, because
    # writing it that way is an assertion that it is an indicator.
    for match in URL_PATTERN.finditer(text):
        url = match.group().rstrip(_URL_TRAILING)
        if not url or url in seen or url.lower() not in deliberately_defanged:
            continue
        seen.add(url)
        cyber_entities.append({
            "name": url, "entity_type": "URL",
            "source": doc_id, "method": "regex", "confidence": 0.95,
        })

    for match in EMAIL_PATTERN.finditer(text):
        email = match.group().lower()
        if email not in seen:
            seen.add(email)
            cyber_entities.append({
                "name": email, "entity_type": "EmailAddress",
                "source": doc_id, "method": "regex", "confidence": 0.9,
            })

    for match in HASH_SHA256.finditer(text):
        h = match.group().lower()
        if h not in seen:
            seen.add(h)
            sha256_spans.add((match.start(), match.end()))
            confidence = 0.95 if _has_hash_context(text, match.start(), match.end()) else 0.7
            cyber_entities.append({
                "name": h, "entity_type": "Hash",
                "source": doc_id, "method": "regex", "confidence": confidence,
                "attributes": {"hash_type": "SHA-256"},
            })

    for match in HASH_SHA1.finditer(text):
        h = match.group().lower()
        if h not in seen and len(h) == 40:
            # Skip if this is a substring of a SHA-256 match
            if any(match.start() >= s and match.end() <= e for s, e in sha256_spans):
                continue
            seen.add(h)
            confidence = 0.9 if _has_hash_context(text, match.start(), match.end()) else 0.6
            cyber_entities.append({
                "name": h, "entity_type": "Hash",
                "source": doc_id, "method": "regex", "confidence": confidence,
                "attributes": {"hash_type": "SHA-1"},
            })

    # Extract MD5 hashes (32 hex chars) — exclude UUIDs and substrings of longer hashes
    # Strip UUIDs from text first to avoid matching their hex segments
    uuid_positions = set()
    for uuid_match in UUID_PATTERN.finditer(text):
        stripped = uuid_match.group().replace("-", "")
        uuid_positions.add(stripped.lower())
    for match in HASH_MD5.finditer(text):
        h = match.group().lower()
        if h not in seen and h not in uuid_positions:
            # Skip if this is a substring of a SHA-1 or SHA-256 match
            if any(match.start() >= s and match.end() <= e for s, e in sha256_spans):
                continue
            seen.add(h)
            confidence = 0.9 if _has_hash_context(text, match.start(), match.end()) else 0.6
            cyber_entities.append({
                "name": h, "entity_type": "Hash",
                "source": doc_id, "method": "regex", "confidence": confidence,
                "attributes": {"hash_type": "MD5"},
            })

    for match in CVE_PATTERN.finditer(text):
        cve = match.group()
        if cve not in seen:
            seen.add(cve)
            cyber_entities.append({
                "name": cve, "entity_type": "Vulnerability",
                "source": doc_id, "method": "regex", "confidence": 0.95,
            })

    for match in MITRE_PATTERN.finditer(text):
        ttp = match.group()
        if ttp not in seen:
            seen.add(ttp)
            cyber_entities.append({
                "name": ttp, "entity_type": "TTP",
                "source": doc_id, "method": "regex", "confidence": 0.9,
            })

    # Vessels named with their hull number ("Hallgrim (A-425)"). spaCy tags the
    # hull number, as a nationality, and often not the name at all.
    for name, hull in _hull_numbers(text):
        if name not in seen:
            seen.add(name)
            cyber_entities.append({
                "name": name, "entity_type": "Ship", "aliases": [f"{name} ({hull})", hull],
                "source": doc_id, "method": "regex", "confidence": 0.9,
            })

    # System binaries named as tooling ("techniques including netsh, ntdsutil
    # and wmic"). spaCy tags none of them: lower-case words, no entity shape.
    for match in _KNOWN_SOFTWARE_RE.finditer(text):
        tool = match.group()
        if tool.lower() not in {s.lower() for s in seen}:
            seen.add(tool)
            cyber_entities.append({
                "name": tool, "entity_type": "Software",
                "source": doc_id, "method": "regex", "confidence": 0.85,
            })

    # Named legal instruments spaCy reads as dates or misses: "Executive Order
    # (E.O.) 14186", "E.O. 13871", "the FY2026 NDAA".
    # An executive order is one document however it is written: the first form
    # is its name and every way of writing its number is an alias, which is
    # also what lets hybrid match it to the model's "Executive Order 14347".
    orders: dict[str, dict] = {}
    for match in _DOCUMENT_REF.finditer(text):
        ref = match.group().strip()
        number = ref.rsplit(None, 1)[-1] if ref[-1].isdigit() else ""
        if number in orders:
            entity = orders[number]
            if ref != entity["name"] and ref not in entity["aliases"]:
                entity["aliases"].append(ref)
            continue
        if ref not in seen:
            seen.add(ref)
            entity = {
                "name": ref, "entity_type": "Document",
                "source": doc_id, "method": "regex", "confidence": 0.85,
            }
            if number:
                written = [f"Executive Order {number}", f"E.O. {number}"]
                entity["aliases"] = [form for form in written if form != ref]
                orders[number] = entity
            cyber_entities.append(entity)

    # Military hardware designations (e.g. "Type 075", "Type 052D") — spaCy
    # misses these entirely, so extract them as EquipmentType directly.
    for match in re.finditer(r'\bType[- ]?\d{2,4}[A-Z]?\b', text):
        desig = match.group().strip()
        if desig not in seen and len(desig) >= 6:
            seen.add(desig)
            cyber_entities.append({
                "name": desig, "entity_type": "EquipmentType",
                "source": doc_id, "method": "regex", "confidence": 0.85,
            })

    # Date extraction
    date_spans: list[tuple[int, int]] = []
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            date_str = match.group().strip()
            if any(s <= match.start() and match.end() <= e for s, e in date_spans):
                continue  # part of a fuller date already taken
            date_spans.append(match.span())
            if date_str not in seen and len(date_str) >= 4:
                seen.add(date_str)
                cyber_entities.append({
                    "name": date_str, "entity_type": "Date",
                    "source": doc_id, "method": "regex", "confidence": 0.95,
                })

    # Coordinates (MGRS / DMS / decimal-with-hemisphere) → placeable Location
    # points carrying lat/lng, so a stated coordinate maps without a gazetteer.
    for coord in parse_coordinates(text):
        name = coord["raw"]
        if name not in seen:
            seen.add(name)
            cyber_entities.append({
                "name": name, "entity_type": "Location",
                "source": doc_id, "method": "regex", "confidence": 0.9,
                "attributes": {
                    "latitude": coord["lat"], "longitude": coord["lng"],
                    "location_type": "coordinate",
                },
            })

    return cyber_entities


# Intelligence-report boilerplate spaCy sometimes tags as entities (title-cased,
# so the all-caps header filter misses them).
REPORT_BOILERPLATE = {
    "handling caveat", "source reliability", "executive summary", "key findings",
    "key judgments", "key judgements", "for official use only", "distribution",
    "classification", "prepared by", "background", "outlook", "recommendations",
    "annex", "appendix", "table of contents", "confidence level",
    "bottom line up front", "scope note", "this assessment",
}

# Bare nationality/regional demonyms — noise as standalone entities (spaCy tags
# them NORP -> Organization). Multi-word orgs ("American Airlines") never match.
DEMONYMS = {
    "european", "american", "british", "french", "german", "russian", "chinese",
    "iranian", "israeli", "ukrainian", "japanese", "korean", "north korean",
    "south korean", "indian", "pakistani", "turkish", "syrian", "iraqi", "saudi",
    "arab", "african", "asian", "western", "eastern", "afghan", "chechen",
}

# Threat-actor naming: APT-NN, Mandiant clusters (UNC2452, FIN7), CrowdStrike-
# style "<Adjective> <Animal>" handles (Cozy Bear, Wicked Panda) and Microsoft's
# weather families (Volt Typhoon, Midnight Blizzard, Storm-0558). The live run
# stored Volt Typhoon as an Organization for want of the last. Capitalization is
# required, and "Super"/"Tropical"/"Eurofighter" excluded, so a storm report
# stays a storm and the aircraft an aircraft.
_THREAT_ACTOR_RE = re.compile(
    r"^(?:APT[- ]?\d+|UNC\d{3,4}|FIN\d{1,2}|Storm-\d{4}"
    r"|(?!Super |Tropical |Eurofighter )[A-Z][A-Za-z]+ "
    r"(?:Panda|Bear|Kitten|Spider|Chollima|Jackal|Buffalo|Tiger|Crane|Lynx|Leopard|Ocelot|Dragon|Hawk"
    r"|Typhoon|Blizzard|Sandstorm|Sleet|Tempest|Tsunami|Hail|Cyclone))$"
)
# Military hardware designations: "Type 052", "Type 075D" -> EquipmentType.
_MIL_EQUIP_RE = re.compile(r"^Type[- ]?\d{2,4}[A-Z]?$", re.IGNORECASE)
# Well-known malware families spaCy tends to tag Organization/Person.
KNOWN_MALWARE = {
    "mimikatz", "plugx", "shadowpad", "wellmess", "wellmail", "cobalt strike",
    "emotet", "trickbot", "qakbot", "wannacry", "notpetya", "sunburst",
    "china chopper", "graphicalneutrino", "gootloader", "bruteratel",
}


_LEADING_DETERMINER = re.compile(r"^(?:the|a|an)\s+", re.IGNORECASE)


def _strip_determiner(name: str) -> str:
    return _LEADING_DETERMINER.sub("", name).strip()


# Below this length a name is matched with its case: "US" must not match "us".
_CASELESS_MIN = 4


@lru_cache(maxsize=4096)
def _name_pattern(name: str) -> re.Pattern:
    flags = re.IGNORECASE if len(name) >= _CASELESS_MIN else 0
    return re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", flags)


def _mention_spans(sent_text: str, entities: list[dict]) -> list[tuple[int, int, dict]]:
    """Where each entity is mentioned in the sentence, as (start, end, entity).

    Case-insensitive for names of four characters or more: reporting writes a
    name in lower case mid-sentence ("shows that hallgrim (A-425) arrives
    Torvik") and the entity extracted from its capitalised mention elsewhere is
    still the one meant.
    """
    spans = []
    for e in entities:
        for name in [e.get("name") or "", *(e.get("aliases") or [])]:
            if not name:
                continue
            for m in _name_pattern(name).finditer(sent_text):
                spans.append((m.start(), m.end(), e))
    return spans


_BRACKETED = r"\s*\(([A-Z][A-Za-z0-9&.\-]{1,11})\)"


def _merge_bracketed_acronyms(entities: list[dict], text: str) -> list[dict]:
    """"Office of Foreign Assets Control (OFAC)": the acronym is an alias, not a second entity.

    Reporting defines an acronym once and then uses it; extracting both made
    two nodes for one body, and an edge read off a sentence that uses the
    acronym ("Within DOD, the Army ...") went to the second. Only an
    all-capitals token, or a shortening of the name ("Russian Federation
    (Russia)"), counts — "Israel (Tel Aviv)" is not an acronym.
    """
    by_name = {e["name"]: e for e in entities}
    drop: set[str] = set()
    for e in entities:
        name = e.get("name") or ""
        if " " not in name or e.get("entity_type") in _INDICATOR_TYPES:
            continue
        for m in re.finditer(re.escape(name) + _BRACKETED, text):
            acr = m.group(1)
            letters = re.sub(r"[^A-Za-z]", "", acr)
            if acr == name or not (letters.isupper() or acr.lower() in name.lower()):
                continue
            aliases = list(e.get("aliases") or [])
            if acr not in aliases:
                aliases.append(acr)
            e["aliases"] = aliases
            other = by_name.get(acr)
            if other is not None and other is not e and other.get("method") != "regex":
                drop.add(acr)
    return [e for e in entities if e["name"] not in drop]


def _entity_at(token, sent, spans: list[tuple[int, int, dict]]) -> dict | None:
    """The entity whose mention contains this token, or None."""
    offset = token.idx - sent.start_char
    containing = [s for s in spans if s[0] <= offset < s[1]]
    if containing:
        return max(containing, key=lambda s: s[1] - s[0])[2]
    return None


def _entity_for_token(token, sent, spans: list[tuple[int, int, dict]]) -> dict | None:
    """The entity a dependency token refers to, or None.

    The token must be part of an entity mention ("Service" in "Russian Foreign
    Intelligence Service"), or head a phrase containing one ("Hackers from
    APT29", "by APT29"). Substring tests are not enough: ``"it" in "Citrix"``
    bound a pronoun subject to Citrix.

    When the phrase holds several, a named threat actor is the one meant: in
    "The People's Republic of China state-sponsored cyber actor known as Volt
    Typhoon", the actor is Volt Typhoon, not the country it is attributed to.
    """
    found = _entity_at(token, sent, spans)
    if found is not None:
        return found
    # The name compounded with the head noun is what the phrase is about:
    # "Iran-backed Houthi movement" is the Houthi movement, not its backer.
    for child in token.children:
        if child.dep_ == "compound":
            found = _entity_at(child, sent, spans)
            if found is not None:
                return found
    lo = token.left_edge.idx - sent.start_char
    hi = token.right_edge.idx + len(token.right_edge.text) - sent.start_char
    inside = sorted((s for s in spans if lo <= s[0] and s[1] <= hi), key=lambda s: s[0])
    if not inside:
        return None
    actors = [s for s in inside if s[2].get("entity_type") == "ThreatActor"]
    return (actors or inside)[0][2]


# Nouns a report uses to refer back to the actor it is about: "Microsoft
# reported the group used ... CVE-2023-27997". Resolved only to a ThreatActor
# named earlier in the same text, and only with a definite determiner.
_ACTOR_ANAPHORS = frozenset({"group", "actor", "attacker", "adversary", "operator", "intruder"})

# For a verb with no direct object, the prepositions that carry its relation:
# "attributed to China", "relies on netsh", "berth at quay 4". Any other
# preposition ("targeted ... in 2023") is circumstance, not the object.
_REL_PREPOSITIONS = {
    "ATTRIBUTED_TO": frozenset({"to"}),
    "BELONGS_TO": frozenset({"to"}),
    "LOCATED_AT": frozenset({"at", "in", "near"}),
    "DEPLOYED_AT": frozenset({"at", "in", "to"}),
    "COMMUNICATES_WITH": frozenset({"with"}),
    "USES": frozenset({"on"}),
    "TARGETS": frozenset({"against", "on"}),
}


def _phrase_entities(token, sent, spans: list[tuple[int, int, dict]]) -> list[dict]:
    """The entities a noun phrase names, in the order the parse gives them.

    For the head and each conjunct: the entity it is part of, else an
    appositive ("the Fortinet vulnerability CVE-2023-27997" names the CVE, not
    the vendor), else a modifier ("built-in Windows tools"). Only when none of
    those names anything does the whole phrase count, and then a list inside it
    ("techniques including netsh, ntdsutil and wmic") yields every member.
    """
    found: list[dict] = []
    for head in (token, *token.conjuncts):
        ent = _entity_at(head, sent, spans)
        for deps in (("appos",), ("compound", "amod", "nmod")):
            if ent is not None:
                break
            for child in head.children:
                if child.dep_ in deps:
                    ent = _entity_at(child, sent, spans)
                    if ent is not None:
                        break
        if ent is not None and ent not in found:
            found.append(ent)
    if found:
        return found
    first = _entity_for_token(token, sent, spans)
    if first is None:
        return []
    found.append(first)
    for t in token.subtree:
        if _entity_at(t, sent, spans) is first:
            for conj in t.conjuncts:
                other = _entity_at(conj, sent, spans)
                if other is not None and other not in found:
                    found.append(other)
            break
    return found


def _verb_subject(token, sent, spans, resolve_anaphor, depth: int = 0) -> dict | None:
    """The entity acting as this verb's subject, or None.

    Beyond an explicit subject: a participle modifying a noun takes that noun
    ("Volt Typhoon, a ... actor attributed to China"), and a coordinated or
    adverbial verb shares its head verb's subject ("The group avoided malware,
    instead abusing built-in Windows tools").
    """
    subject_children = [c for c in token.children if c.dep_ in ("nsubj", "nsubjpass", "agent")]
    for child in subject_children:
        ent = _entity_for_token(child, sent, spans)
        if ent is not None:
            return ent
    if subject_children:
        return resolve_anaphor(subject_children[0])
    if token.dep_ in ("acl", "relcl"):
        head = token.head
        ent = _entity_at(head, sent, spans)
        if ent is None and head.dep_ == "appos":
            ent = _entity_at(head.head, sent, spans)
        return ent
    if depth < 3 and token.dep_ in ("conj", "advcl", "xcomp") and token.head.pos_ in ("VERB", "AUX"):
        return _verb_subject(token.head, sent, spans, resolve_anaphor, depth + 1)
    return None


# When the direct object names nothing, where it was can still be the target:
# "has compromised critical infrastructure networks in Guam".
_PLACE_PREPOSITIONS = frozenset({"in", "at"})
_PLACE_RELATIONS = frozenset({"TARGETS", "LOCATED_AT", "DEPLOYED_AT"})


def _verb_objects(token, rel_type: str, sent, spans) -> list[dict]:
    """The entities this verb's relation points at."""
    direct = [c for c in token.children if c.dep_ in ("dobj", "pobj", "attr")]
    found: list[dict] = []
    for child in direct:
        for ent in _phrase_entities(child, sent, spans):
            if ent not in found:
                found.append(ent)
    if found:
        return found
    if direct:
        # "linked the campaign to ...": the object is the campaign, and the
        # preposition says what it was linked to, not what the subject did.
        if rel_type not in _PLACE_RELATIONS:
            return []
        preps = _PLACE_PREPOSITIONS
    else:
        preps = _REL_PREPOSITIONS.get(rel_type, frozenset())
    for prep in token.children:
        if prep.dep_ == "prep" and prep.lower_ in preps:
            for pobj in prep.children:
                if pobj.dep_ == "pobj":
                    for ent in _phrase_entities(pobj, sent, spans):
                        if ent not in found:
                            found.append(ent)
    return found


def _refine_rel_type(rel_type: str, target: dict) -> str:
    """Using a vulnerability is exploiting it ("used ... CVE-2023-27997")."""
    if rel_type == "USES" and target.get("entity_type") == "Vulnerability":
        return "EXPLOITS"
    return rel_type


# Relations named from the receiving end: "Iran supplied Russia" is Russia
# SUPPLIED_BY Iran. The verb map pairs these verbs with them, so in the active
# voice the edge runs from what the verb acts on back to its subject.
_REVERSED_RELATIONS = frozenset({"SUPPLIED_BY", "FUNDED_BY", "COMMANDED_BY"})


def _verb_edges(token, rel_type: str, sent, spans, resolve_anaphor) -> list[tuple[dict, dict]]:
    """(source, target) entity pairs the mapped verb states, in the relation's direction."""
    passive_subj = [c for c in token.children if c.dep_ == "nsubjpass"]
    agent = [c for c in token.children if c.dep_ == "agent"]
    if passive_subj and agent:
        # "Hezbollah is funded by Iran", "Ukraine was attacked by Russia".
        patient = _entity_for_token(passive_subj[0], sent, spans) or resolve_anaphor(passive_subj[0])
        actors = [e for p in agent[0].children if p.dep_ == "pobj" for e in _phrase_entities(p, sent, spans)]
        if patient is None:
            return []
        return [(patient, a) if rel_type in _REVERSED_RELATIONS else (a, patient) for a in actors]

    subj = _verb_subject(token, sent, spans, resolve_anaphor)
    if subj is None:
        return []
    if rel_type not in _REVERSED_RELATIONS:
        return [(subj, o) for o in _verb_objects(token, rel_type, sent, spans)]
    # Active voice, receiving-end relation: the recipient is the indirect
    # object ("provided the Houthis with components", "to Russia").
    recipients: list[dict] = []
    for child in token.children:
        if child.dep_ == "dative":
            recipients += _phrase_entities(child, sent, spans)
        elif child.dep_ == "prep" and child.lower_ == "to":
            recipients += [e for p in child.children if p.dep_ == "pobj" for e in _phrase_entities(p, sent, spans)]
    if not recipients:
        with_prep = any(c.dep_ == "prep" and c.lower_ == "with" for c in token.children)
        if with_prep or rel_type != "SUPPLIED_BY":
            # The direct object is the recipient when what was given follows
            # "with", or for funding and command ("Iran funds Hezbollah").
            recipients = [e for c in token.children if c.dep_ == "dobj" for e in _phrase_entities(c, sent, spans)]
    return [(r, subj) for r in recipients]


# ── Relations stated without a verb ──────────────────────────────────────────
# Analytic prose states most of its relations as a possessive ("Poland's
# Internal Security Agency"), a title ("Russian President Vladimir Putin",
# "Commander of U.S. European Command") or an action noun ("Russia's invasion
# of Ukraine", "its military presence in the Arctic").

# Adjective -> the country it names, used only when that country is itself an
# entity of the text.
_DEMONYMS = {
    "russian": "russia", "iranian": "iran", "israeli": "israel", "syrian": "syria", "chinese": "china",
    "ukrainian": "ukraine", "japanese": "japan", "taiwanese": "taiwan", "turkish": "turkey", "polish": "poland",
    "french": "france", "german": "germany", "british": "united kingdom", "american": "united states",
    "u.s.": "united states", "saudi": "saudi arabia", "iraqi": "iraq", "pakistani": "pakistan",
    "indian": "india", "north korean": "north korea", "south korean": "south korea", "lebanese": "lebanon",
    "yemeni": "yemen", "egyptian": "egypt", "belarusian": "belarus", "georgian": "georgia",
    "venezuelan": "venezuela", "cuban": "cuba", "afghan": "afghanistan", "qatari": "qatar",
}
_DEMONYM_ALT = "|".join(sorted((re.escape(d) for d in _DEMONYMS), key=len, reverse=True))
_TITLE = (
    r"(?:President|Vice President|Prime Minister|Premier|[Ll]eader|Supreme Leader|General|Gen\.|Admiral|"
    r"Ambassador|(?:Foreign |Defen[cs]e |Oil )?Minister|Secretary(?: of State| of Defense)?|Chancellor|"
    r"[Cc]ommander|[Dd]irector|[Cc]hief|[Hh]ead|Chairman|High Representative|[Ss]pokes(?:man|person))"
)
_TITLE_RUN = rf"(?:(?:[Ff]ormer|[Tt]hen-|now\s+deceased)\s*)?{_TITLE}(?:\s+{_TITLE}){{0,2}}"
_GAP_TITLE_BEFORE = re.compile(rf"^\s+{_TITLE_RUN}\s+$")
_GAP_TITLE_AFTER = re.compile(
    rf"^,\s+(?:the\s+)?{_TITLE_RUN}(?:\s+[A-Z][a-z]+){{0,3}}\s+of\s+(?:the\s+)?"
    r"(?:[A-Z][\w.]*(?:\s[A-Z][\w.]*)*['’]s\s+)?$"
)
_TITLE_OF_BEFORE = re.compile(rf"\b{_TITLE_RUN}\s+of\s+(?:the\s+)?$")
_DEMONYM_TITLE_BEFORE = re.compile(rf"(?:^|\s)(?:[Tt]hen-|[Ff]ormer\s+)?({_DEMONYM_ALT})\s+{_TITLE_RUN}\s+$", re.I)
_GAP_POSSESSIVE = re.compile(r"^['’]s(?:\s+[a-z][\w-]*){0,2}\s+$")
_BACKED = re.compile(r"(?:^|[\s(])([A-Z][\w.]*)-(?:backed|sponsored|funded)\s+$")

_HOLDERS = frozenset({"Organization", "Location", "ThreatActor"})
_MEMBERS = frozenset({"Organization", "Person", "ThreatActor"})

# Action nouns and the prepositions that name what they are against.
_ATTACK_NOUNS = {
    "invasion": {"of"}, "attack": {"on", "against"}, "strike": {"on", "against"}, "airstrike": {"on", "against"},
    "war": {"against", "on"}, "offensive": {"against"}, "aggression": {"against"}, "operation": {"against"},
    "campaign": {"against"}, "threat": {"against"}, "warfare": {"against"}, "activity": {"against"},
}


def _country_entity(word: str, entities_by_name: dict[str, dict]) -> dict | None:
    target = _DEMONYMS.get(word.lower())
    return entities_by_name.get(target) if target else None


def _phrase_relations(sent, spans, entities_by_name, resolve_anaphor) -> list[tuple[dict, str, dict]]:
    """Possessive, title and action-noun relations in one sentence."""
    out: list[tuple[dict, str, dict]] = []
    text = sent.text
    ordered = sorted(spans, key=lambda s: (s[0], -(s[1] - s[0])))
    # Keep the longest mention at each position: "U.S. European Command", not "U.S.".
    mentions = []
    for s in ordered:
        if mentions and s[0] < mentions[-1][1]:
            continue
        mentions.append(s)

    for i, (a_start, a_end, a) in enumerate(mentions):
        a_type = a.get("entity_type")
        for b_start, b_end, b in mentions[i + 1:]:
            gap = text[a_end:b_start]
            if len(gap) > 120:
                break
            b_type = b.get("entity_type")
            # "Poland's Internal Security Agency": B belongs to A.
            if _GAP_POSSESSIVE.match(gap) and a_type in _HOLDERS and b_type in _MEMBERS:
                out.append((b, "BELONGS_TO", a))
            # "European Commission President Ursula von der Leyen".
            elif _GAP_TITLE_BEFORE.match(gap) and a_type in _HOLDERS and b_type == "Person":
                rel = "COMMANDED_BY" if re.search(r"[Cc]ommander", gap) else "BELONGS_TO"
                out.append((a, rel, b) if rel == "COMMANDED_BY" else (b, rel, a))
            # "Kaja Kallas, High Representative of the European Union".
            elif _GAP_TITLE_AFTER.match(gap) and a_type == "Person" and b_type in _HOLDERS:
                rel = "COMMANDED_BY" if re.search(r"[Cc]ommander", gap) else "BELONGS_TO"
                out.append((b, rel, a) if rel == "COMMANDED_BY" else (a, rel, b))
            # "head of Hezbollah, Hassan Nasrallah".
            elif re.fullmatch(r",\s+", gap) and a_type in _HOLDERS and b_type == "Person" \
                    and _TITLE_OF_BEFORE.search(text[max(0, a_start - 60):a_start]):
                out.append((b, "BELONGS_TO", a))

        # "Russian President Vladimir Putin": the country is an adjective.
        if a_type == "Person":
            m = _DEMONYM_TITLE_BEFORE.search(text[max(0, a_start - 80):a_start])
            country = _country_entity(m.group(1), entities_by_name) if m else None
            if country is not None:
                out.append((a, "BELONGS_TO", country))
        # "Iran-backed Houthi movement".
        m = _BACKED.search(text[max(0, a_start - 40):a_start])
        if m:
            backer = entities_by_name.get(m.group(1).lower())
            if backer is not None and backer is not a:
                out.append((a, "FUNDED_BY", backer))

    def actor_for(noun) -> dict | None:
        for child in noun.children:
            if child.dep_ == "poss":
                ent = _entity_at(child, sent, spans)
                if ent is not None:
                    return ent
            if child.dep_ in ("amod", "compound"):
                ent = _country_entity(child.text, entities_by_name) or _entity_at(child, sent, spans)
                if ent is not None and ent.get("entity_type") in _HOLDERS:
                    return ent
        if noun.dep_ in ("dobj", "attr", "pobj") and noun.head.pos_ in ("VERB", "AUX"):
            return _verb_subject(noun.head, sent, spans, resolve_anaphor)
        return None

    for token in sent:
        lemma = token.lemma_.lower()
        if token.pos_ != "NOUN" or (lemma not in _ATTACK_NOUNS and lemma != "presence"):
            continue
        preps = {"in"} if lemma == "presence" else _ATTACK_NOUNS[lemma]
        holders = [token]
        if token.dep_ == "dobj":
            # The parse often hangs the phrase on the verb: "increasing its
            # military presence in the Arctic".
            holders.append(token.head)
        targets = [e for h in holders for c in h.children if c.dep_ == "prep" and c.lower_ in preps
                   for p in c.children if p.dep_ == "pobj" for e in _phrase_entities(p, sent, spans)]
        if not targets:
            continue
        actor = actor_for(token)
        if actor is None:
            continue
        rel = "DEPLOYED_AT" if lemma == "presence" else "TARGETS"
        out.extend((actor, rel, t) for t in targets)
    return [(s, r, t) for s, r, t in out
            if s is not t and s["name"] != t["name"] and "Date" not in (s.get("entity_type"), t.get("entity_type"))]


def _postprocess_entities(entities: list[dict]) -> list[dict]:
    """Fix common spaCy misclassifications for intelligence documents."""
    # Load from YAML (with fallback to hardcoded module constants)
    known_locs = get_known_locations() or KNOWN_LOCATIONS
    known_orgs = get_known_organizations() or KNOWN_ORGANIZATIONS
    known_pers = get_known_persons() or KNOWN_PERSONS
    known_acro = get_known_acronyms() or KNOWN_ACRONYMS
    loc_kws = get_location_keywords() or LOCATION_KEYWORDS
    org_kws = get_org_keywords() or ORG_KEYWORDS

    corrected = []
    for e in entities:
        name = e["name"]
        name_lower = name.lower().strip()

        # Preserve regex-extracted entities (cyber entities should never be filtered)
        if e.get("method") == "regex":
            corrected.append(e)
            continue

        # Strip leading determiners spaCy glues onto ORG/LOC spans ("the Russian
        # Foreign Intelligence Service" -> "Russian Foreign Intelligence Service")
        # — inflates false positives and breaks dedup against the canonical name.
        stripped = _strip_determiner(name)
        # ...and the possessive it sometimes swallows: "Department of the
        # Treasury's" is the Department of the Treasury.
        stripped = re.sub(r"['’]s$", "", stripped).strip()
        if stripped and stripped != name:
            name = stripped
            e["name"] = name
            name_lower = name.lower().strip()

        # Drop report boilerplate and bare nationality demonyms — high-frequency
        # false positives, not analytic entities.
        if name_lower in REPORT_BOILERPLATE or name_lower in DEMONYMS:
            continue

        # Skip all-caps headers (document section headings), but keep acronyms.
        # A heading is several words ("BOTTOM LINE UP FRONT") or a heading
        # word; a single all-caps token spaCy calls an organization is an
        # acronym — NORTHCOM, GCHQ, OFAC were all dropped as headings.
        # Only a plain letters-only token counts: "U.S.", "P.L.", "FY2026" and
        # "C-UAS" are abbreviations and labels, not organizations.
        if name.isupper() and len(name) > 3 and name not in known_acro and (
                not name.isalpha() or name in _HEADING_WORDS):
            continue
        if _DOCUMENT_NAME.search(name) and e.get("entity_type") in _DOCUMENT_OVERRIDABLE:
            # "Worldwide Threat Assessment", "IRONDOME Act": a named document,
            # which spaCy reads as an organization or a place.
            e["entity_type"] = "Document"
            corrected.append(e)
            continue

        # Fix trailing parenthetical fragments
        if "(" in name and ")" not in name:
            name = name.split("(")[0].strip()
            e["name"] = name
            if not name:
                continue

        # Force MITRE ATT&CK IDs to TTP type
        mitre_re = re.compile(r'^T\d{4}(?:\.\d{3})?$')
        if mitre_re.match(name):
            e["entity_type"] = "TTP"

        # Domain typing that spaCy misses: threat actors, military hardware,
        # known malware (else they leak in as Organization/Person/Location).
        if _THREAT_ACTOR_RE.match(name):
            e["entity_type"] = "ThreatActor"
        elif _MIL_EQUIP_RE.match(name):
            e["entity_type"] = "EquipmentType"
        elif name_lower in KNOWN_MALWARE:
            e["entity_type"] = "Malware"

        # A product typed from the noun it modifies ("Windows tools", "ProSAFE
        # router") keeps that type: the keyword heuristics below read only the
        # name, and the name alone is what misled spaCy in the first place.
        if e.get("entity_type") in ("Software", "Hardware", "Event"):
            corrected.append(e)
            continue
        if name_lower in _KNOWN_VENDORS:
            e["entity_type"] = "Organization"

        # Force known persons
        if name_lower in known_pers:
            e["entity_type"] = "Person"
        # Force known locations
        elif name_lower in known_locs:
            e["entity_type"] = "Location"
        # Force known organizations
        elif name_lower in known_orgs:
            e["entity_type"] = "Organization"
        # The head word decides first: "Kuwait Gulf Oil Company" and "Gulf
        # Cooperation Council" are organizations although they hold "Gulf";
        # "Hypersonic Cruise Missile" is a weapon.
        elif _WEAPON_HEAD.search(name):
            e["entity_type"] = "Weapon"
        elif any(name.endswith(kw) for kw in org_kws) or _ORG_HEAD.search(name):
            e["entity_type"] = "Organization"
        # Heuristic: location keywords (Airbase, Port, Island, etc.)
        elif any(kw in name for kw in loc_kws):
            e["entity_type"] = "Location"
        # Heuristic: org keywords
        elif any(kw in name for kw in org_kws):
            e["entity_type"] = "Organization"

        corrected.append(e)
    return corrected


def _apply_coreference(doc, entities: list[dict]) -> list[dict]:
    """Apply coreference resolution to merge entity mentions referring to the same entity.

    Requires the 'coreferee' spaCy extension to be installed and the model to
    support it. Falls back gracefully if not available.
    """
    try:
        if not doc._.has("coref_chains") or not doc._.coref_chains:
            return entities
    except Exception:
        return entities

    # Build a map from token index → entity
    token_to_entity: dict[int, dict] = {}
    for ent in doc.ents:
        for token in ent:
            for e in entities:
                if e["name"] == ent.text.strip():
                    token_to_entity[token.i] = e

    # For each coreference chain, find the "head" (longest named mention)
    # and merge shorter mentions/pronouns into it
    entities_to_remove = set()
    for chain in doc._.coref_chains:
        chain_entities = []
        for mention in chain:
            for token_idx in mention:
                if token_idx in token_to_entity:
                    chain_entities.append(token_to_entity[token_idx])
                    break

        if len(chain_entities) < 2:
            continue

        # Head = entity with the longest name (most complete reference)
        head = max(chain_entities, key=lambda e: len(e["name"]))
        for e in chain_entities:
            if e["name"] != head["name"]:
                # Add as alias and mark for removal
                if "aliases" not in head:
                    head["aliases"] = []
                if e["name"] not in head["aliases"]:
                    head["aliases"].append(e["name"])
                entities_to_remove.add(e["name"])

    if entities_to_remove:
        entities = [e for e in entities if e["name"] not in entities_to_remove]

    return entities


def extract_entities_nlp(text: str, doc_id: str) -> ExtractionResult:
    if not text.strip():
        return ExtractionResult([], [], method="nlp")

    # Refang defanged IOCs (evil[.]com, hxxp://, a[at]b[.]com) up front so spaCy,
    # the cyber regex pass, and the sentence-matching that builds relationships all
    # operate on the same canonical text. Doing this only inside
    # _extract_cyber_entities left spaCy tagging the raw literal as a junk node and
    # orphaned the IOC from relationships (its refanged name was not a substring of
    # the raw sentence text). refang is idempotent, so the inner call is harmless.
    #
    # Keep the original, though: whether a value was defanged is the one signal
    # the text carries that it is an indicator rather than a citation, and
    # refang is precisely the operation that erases it.
    raw_text = text
    text = refang(text)

    nlp = _get_nlp()
    doc = nlp(text)

    seen_names: dict[str, dict] = {}
    entities = []

    # 1. Extract cyber entities via regex first
    cyber_entities = _extract_cyber_entities(text, doc_id, raw_text=raw_text)
    for ce in cyber_entities:
        if ce["name"] not in seen_names:
            seen_names[ce["name"]] = ce
            entities.append(ce)

    # Known multi-word places, as written. spaCy splits some of them — "the
    # Strait of" (LOC) and "Hormuz" (PERSON) — so where one is found, any span
    # overlapping it is not taken from spaCy.
    gazetteer_spans: list[tuple[int, int]] = []
    for place in sorted((p for p in (get_known_locations() or KNOWN_LOCATIONS) if " " in p), key=len, reverse=True):
        for m in re.finditer(r"(?<!\w)" + re.escape(place) + r"(?!\w)", text, re.IGNORECASE):
            if any(s < m.end() and m.start() < e for s, e in gazetteer_spans):
                continue
            gazetteer_spans.append(m.span())
            name = m.group()
            if name not in seen_names:
                ent = {"name": name, "entity_type": "Location", "source": doc_id,
                       "method": "regex", "confidence": 0.9}
                seen_names[name] = ent
                entities.append(ent)

    # 2. Count entity mention frequency for confidence scoring
    name_freq: dict[str, int] = {}
    for ent in doc.ents:
        name = ent.text.strip().strip("'\"")
        if name:
            name_freq[name] = name_freq.get(name, 0) + 1

    # Load known entities from YAML (with fallback)
    known_locs = get_known_locations() or KNOWN_LOCATIONS
    known_orgs = get_known_organizations() or KNOWN_ORGANIZATIONS
    known_pers = get_known_persons() or KNOWN_PERSONS
    known_acro = get_known_acronyms() or KNOWN_ACRONYMS
    noise = get_noise_words() or NOISE_WORDS
    _all_known = known_locs | known_orgs | known_pers

    hull_numbers = {hull for _, hull in _hull_numbers(text)}

    # 3. Extract NLP entities with context-aware confidence
    for ent in doc.ents:
        entity_type = SPACY_TO_ENTITY_TYPE.get(ent.label_)
        if not entity_type:
            continue
        name = ent.text.strip().strip("'\"")
        if not name or len(name) < 2:
            continue
        if name in noise:
            continue
        if name in seen_names:
            continue
        if any(s < ent.end_char and ent.start_char < e for s, e in gazetteer_spans):
            continue
        if entity_type == "Date" and not _is_datable(name):
            continue
        # A nationality used as an adjective — "Valdorian naval liaison",
        # "Ravenskan hydrographic survey" — names no organization. A group
        # named in front of its members ("Taliban fighters") is a proper noun
        # in compound, not an adjective, and is kept.
        if len(ent) == 1 and ent.root.pos_ == "ADJ" and ent.root.dep_ == "amod":
            continue
        # spaCy tags the odd lower-case common noun ("liaison", "quay 4") as a
        # person or a facility. A name is capitalised; extracted lower-case
        # values (tools, indicators) come from the regex pass, not here.
        # Amounts and quantities are not names and are left alone.
        if ent.label_ in _NAME_LABELS and name.islower():
            continue
        if name in _TECHNICAL_ACRONYMS or name in hull_numbers:
            # A hull number ("A-425") is the vessel's alias, not another entity.
            continue

        # Context-aware confidence scoring
        confidence = 0.7  # base
        name_lower = name.lower().strip()
        if name_lower in _all_known or name in known_acro:
            confidence = 0.85  # known entity match
        elif name_freq.get(name, 0) > 1:
            confidence = 0.8  # appears multiple times
        elif len(name) <= 3 and name not in known_acro:
            confidence = 0.5  # short ambiguous entity

        entity = {
            "name": name, "entity_type": _product_type(ent) or entity_type,
            "source": doc_id, "method": "nlp", "confidence": confidence,
        }
        seen_names[name] = entity
        entities.append(entity)

    # 4. Postprocess to fix misclassifications
    entities = _apply_vessel_hints(_apply_type_hints(_postprocess_entities(entities)), text)
    # Postprocessing renames ("Kalvar (A-417" -> "Kalvar"), which can land on
    # a name already taken; the first, regex-extracted one is kept.
    unique: dict[str, dict] = {}
    for e in entities:
        unique.setdefault(e["name"], e)
    entities = _merge_bracketed_acronyms(list(unique.values()), text)

    # 5. Optional coreference resolution
    from intel_platform.config import settings
    if settings.coreference_enabled:
        entities = _apply_coreference(doc, entities)

    # Rebuild seen_names after postprocessing (names may have changed)
    seen_names = {e["name"]: e for e in entities}

    # ── Relationship extraction ────────────────────────────────────────────
    # Load verb-to-relationship mappings from YAML
    from intel_platform.data import get_verb_mappings
    verb_map = get_verb_mappings()

    relationships = []
    seen_rel_keys: set[tuple[str, str, str]] = set()
    # Tracks every pair that already has *some* relationship (any type, from
    # any stage), so the co-occurrence fallback below never piles a blanket
    # ASSOCIATED_WITH on top of a pair a typed/pattern relation already links.
    linked_pairs: set[frozenset[str]] = set()

    def _add_rel(src_name: str, tgt_name: str, rel_type: str, confidence: float, evidence: str = "") -> None:
        key = (src_name, tgt_name, rel_type)
        if key not in seen_rel_keys:
            seen_rel_keys.add(key)
            linked_pairs.add(frozenset((src_name, tgt_name)))
            relationships.append({
                "source_name": src_name, "target_name": tgt_name,
                "rel_type": rel_type, "confidence": confidence,
                "source": doc_id, "method": "nlp",
                # The in-context span this relation was read from — surfaced as evidence.
                "evidence": _clean_evidence(evidence, src_name, tgt_name),
            })

    # Where each threat actor is named, so "the group" can be read as the last
    # one named before it. Nothing is resolved when no actor has been named.
    actor_mentions = sorted(
        ((m.start(), e)
         for e in entities if e.get("entity_type") == "ThreatActor"
         for m in _name_pattern(e["name"]).finditer(text)),
        key=lambda pair: pair[0],
    )

    # Lower-cased name -> entity, for the countries a demonym names and the
    # backer an "X-backed" names.
    entities_by_name: dict[str, dict] = {}
    for e in entities:
        for n in [e["name"], *(e.get("aliases") or [])]:
            entities_by_name.setdefault(str(n).lower(), e)

    def _resolve_anaphor(tok) -> dict | None:
        if tok.lemma_.lower() not in _ACTOR_ANAPHORS:
            return None
        if not any(c.dep_ == "det" and c.lower_ in ("the", "this", "that") for c in tok.children):
            return None
        earlier = [e for start, e in actor_mentions if start < tok.idx]
        return earlier[-1] if earlier else None

    # Generic co-occurrence edges wait until every sentence has been read: a
    # typed relation stated later in the text still rules one out.
    generic_candidates: list[tuple[str, str, str]] = []

    for sent in doc.sents:
        sent_text = sent.text
        sent_entities_list = []
        # Which paragraphs of the sentence each entity is named in. spaCy joins
        # a heading to the sentence under it ("China" over "In addition, South
        # Korea ..."); a sentence never really crosses a paragraph break.
        paragraphs: dict[int, set[int]] = {}
        breaks = [m.start() for m in _PARAGRAPH_BREAK.finditer(sent_text)]

        def _paragraph(offset: int) -> int:
            return sum(1 for b in breaks if b < offset)

        # spaCy-detected entities in this sentence. Looked up by the name the
        # entity ended up with: postprocessing strips determiners and quotes,
        # and a lookup by the raw span text missed every entity it renamed.
        for ent in sent.ents:
            name = ent.text.strip()
            match = seen_names.get(name) or seen_names.get(_strip_determiner(name.strip("'\"")))
            if match is not None:
                paragraphs.setdefault(id(match), set()).add(_paragraph(ent.start_char - sent.start_char))
                if match not in sent_entities_list:
                    sent_entities_list.append(match)

        # Regex-extracted entities that appear in this sentence text
        for e in entities:
            if e.get("method") == "regex" and e["name"] in sent_text and e not in sent_entities_list:
                sent_entities_list.append(e)
                paragraphs[id(e)] = {_paragraph(m.start()) for m in re.finditer(re.escape(e["name"]), sent_text)}

        # The typed stage also sees entities spaCy did not tag in this sentence
        # but which were extracted elsewhere in the text: its NER is not
        # consistent across sentences, and a lower-cased "hallgrim" is still
        # Hallgrim. The co-occurrence fallback below keeps to tagged mentions.
        typed_candidates = list(sent_entities_list)
        for e in entities:
            if e not in typed_candidates and any(
                    len(n) >= _CASELESS_MIN and _name_pattern(n).search(sent_text)
                    for n in [e["name"], *(e.get("aliases") or [])]):
                typed_candidates.append(e)
        mention_spans = _mention_spans(sent_text, typed_candidates)

        # ── Stage A: Dependency-parse relationship extraction ──
        # A mapped verb, its subject and each entity it points at.
        for token in sent:
            if token.pos_ != "VERB":
                continue
            verb_lemma = token.lemma_.lower()
            rel_type_from_verb = verb_map.get(verb_lemma)
            if not rel_type_from_verb:
                continue

            for src_ent, tgt_ent in _verb_edges(token, rel_type_from_verb, sent, mention_spans, _resolve_anaphor):
                if src_ent["name"] == tgt_ent["name"] or "Date" in (
                        src_ent.get("entity_type"), tgt_ent.get("entity_type")):
                    # A date is when, not what: it is never a node to point at.
                    continue
                _add_rel(src_ent["name"], tgt_ent["name"],
                         _refine_rel_type(rel_type_from_verb, tgt_ent), 0.7, sent_text)

        # ── Stage A2: relations stated as a possessive, a title or an action noun ──
        for src_ent, rel_type, tgt_ent in _phrase_relations(sent, mention_spans, entities_by_name, _resolve_anaphor):
            _add_rel(src_ent["name"], tgt_ent["name"], rel_type, 0.7, sent_text)

        # ── Stage B: Co-occurrence relationships (fallback) ──
        # Bounded to nearby entities (COOCCURRENCE_WINDOW), not the full
        # cross-product, and skipped wherever Stage A (or an earlier
        # sentence) already linked the pair with a real relationship —
        # ASSOCIATED_WITH only fires when nothing better connects the two.
        for i, e1 in enumerate(sent_entities_list):
            for j in range(i + 1, len(sent_entities_list)):
                e2 = sent_entities_list[j]
                e1_is_date = e1.get("entity_type") == "Date"
                e2_is_date = e2.get("entity_type") == "Date"
                # Event<->Date gets the typed, load-bearing OCCURRED_ON across the
                # FULL sentence (it populates Event.event_datetime for the
                # timeline — see _link_event_dates). Crucially this fires ONLY when
                # the non-Date side is an Event: a Date sitting next to a Person /
                # Org / Location is not an "occurred on" and would just be noise,
                # so it falls through to the ordinary windowed co-occurrence rule.
                if e1_is_date != e2_is_date:
                    date_ent, other = (e1, e2) if e1_is_date else (e2, e1)
                    _, parent_category = normalize_entity_type(other.get("entity_type", ""))
                    if parent_category == "Event":
                        _add_rel(other["name"], date_ent["name"], "OCCURRED_ON", 0.7, sent_text)
                    # Otherwise no edge at all. Dates are not graph nodes, so a
                    # generic edge to one is dropped at build and counted as a
                    # loss: five of the six edges the live run built from one
                    # document went that way. The date still dates its event
                    # through OCCURRED_ON above.
                    continue
                if e1_is_date and e2_is_date:
                    continue
                # ASSOCIATED_WITH is noise — only a candidate within the window,
                # when both are named in one paragraph of the sentence, and
                # emitted below only if no typed relation links the pair.
                if (j - i) <= COOCCURRENCE_WINDOW and paragraphs.get(id(e1), {0}) & paragraphs.get(id(e2), {0}):
                    generic_candidates.append((e1["name"], e2["name"], sent_text))

    # "torvald (A-430) of 2nd Naval Auxiliary Group": a vessel of a unit
    # belongs to it. Read off the text, since the parse attaches the unit to the
    # hull number as often as to the name.
    ships = {e["name"].lower(): e["name"] for e in entities if e.get("entity_type") == "Ship"}
    orgs = sorted((e["name"] for e in entities if e.get("entity_type") == "Organization"), key=len, reverse=True)
    if ships and orgs:
        for m in _SHIP_OF_UNIT.finditer(text):
            words = m.group(1).split()
            ship = next((ships[" ".join(words[k:]).lower()] for k in range(len(words))
                         if " ".join(words[k:]).lower() in ships), None)
            after = text[m.end():].lower()
            unit = next((o for o in orgs if after.startswith(o.lower())), None)
            if ship and unit:
                _add_rel(ship, unit, "BELONGS_TO", 0.7, text[max(0, m.start() - 60):m.end() + len(unit) + 60])

    # A generic association only where nothing typed links the pair anywhere
    # in the text. Before, the check ran sentence by sentence, so a pair
    # related later ("torvald (A-430) of 2nd Naval Auxiliary Group", read after
    # the loop) kept the association from an earlier sentence as well.
    for a_name, b_name, sentence in generic_candidates:
        if frozenset((a_name, b_name)) not in linked_pairs:
            _add_rel(a_name, b_name, "ASSOCIATED_WITH", 0.5, sentence)

    entities, relationships, same_entity = _resolve_countries(entities, relationships, text, doc)

    # Resolve event_datetime on Event entities from their OCCURRED_ON Date links
    _link_event_dates(entities, relationships)

    return ExtractionResult(entities, relationships, method="nlp",
                            relationships_dropped_by_reason={"same_entity": same_entity} if same_entity else None)


# A blank line: the end of a paragraph or a heading, which no sentence crosses.
_PARAGRAPH_BREAK = re.compile(r"\n[ \t]*\n")

# "<name> (<hull>) of [the] " — what follows is checked against extracted units.
_SHIP_OF_UNIT = re.compile(
    r"\b([A-Za-z][\w'-]*(?:\s[A-Za-z][\w'-]*){0,2})\s\([A-Z]{1,3}-\d{2,4}\)\s+of\s+(?:the\s+)?"
)


def _confidence(raw, default: float) -> float:
    """A model-supplied confidence as a float; raises on "high" and the like."""
    return default if raw is None else float(raw)


def _llm_entity(e, doc_id: str) -> dict:
    """One model entity as an extraction dict. Raises on a malformed item."""
    if not isinstance(e, dict):
        raise TypeError(f"entity is {type(e).__name__}, not an object")
    name = e.get("name", "")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("entity has no name")
    entity = {
        "name": name,
        "entity_type": _normalize_llm_entity_type(e.get("entity_type", "Person")),
        "source": doc_id,
        "method": "llm",
        "confidence": _confidence(e.get("confidence"), 0.85),
        "aliases": e.get("aliases", []),
    }
    # Pass through entity attributes from LLM. Only an object is attributes;
    # graph_builder validates the fields themselves.
    attrs = e.get("attributes", {})
    if attrs and isinstance(attrs, dict):
        entity["attributes"] = attrs
    return entity


def _llm_relationship(r, doc_id: str) -> dict:
    """One model relationship as an extraction dict. Raises on a malformed item."""
    if not isinstance(r, dict):
        raise TypeError(f"relationship is {type(r).__name__}, not an object")
    src_name = r.get("source_entity", r.get("source", ""))
    tgt_name = r.get("target_entity", r.get("target", ""))
    return {
        "source_name": src_name,
        "target_name": tgt_name,
        "rel_type": _normalize_rel_type(r.get("relationship_type", r.get("rel_type", ""))),
        "confidence": _confidence(r.get("confidence"), 0.7),
        "source": doc_id,
        "method": "llm",
        "evidence": _clean_evidence(r.get("evidence", ""), src_name, tgt_name),
        # Carry the model's polarity through. Without this a denial is
        # indistinguishable from an assertion by the time it reaches the
        # graph, and contradicting reporting counts as corroboration.
        "polarity": (
            "denies"
            if str(r.get("polarity", "")).strip().lower() in ("denies", "deny", "negated", "false")
            else "asserts"
        ),
    }


def _describe_failure(exc: BaseException) -> str:
    # The type, not the message: the message can carry provider URLs or key
    # fragments, and this string is meant to be shown.
    return f"provider error ({type(exc).__name__})"


async def _extract_with_llm(
    text: str, doc_id: str, *, resolve_endpoints: bool = True,
) -> tuple[list[dict], list[dict], int, dict[str, int]]:
    """The LLM half alone: (entities, relationships, skipped_items, relationships dropped by reason).

    Raises ``_LLMExtractionFailed`` with a reason when the model produced
    nothing usable. The callers decide what the fallback is. Hybrid passes
    ``resolve_endpoints=False`` and resolves endpoints (and countries) after
    the merge, when the NLP entities can resolve an endpoint too.
    """
    # Use the extraction-specific provider selection (routes to local Ollama
    # when extraction_llm_provider=ollama; respects runtime overrides otherwise).
    # Resolved inside the failure boundary: the lookup reads the key store, and
    # a failure there escaped as a 500 from /ingest.
    from intel_platform.llm.providers import _get_extraction_provider
    from intel_platform.services.llm_output import json_array_items, json_object

    try:
        provider = await _get_extraction_provider()
    except Exception as exc:
        logger.warning("Extraction provider lookup failed for doc %s", doc_id, exc_info=True)
        raise _LLMExtractionFailed(f"provider lookup failed ({type(exc).__name__})") from exc
    if not provider:
        raise _LLMExtractionFailed("no LLM provider configured")

    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    system = loader.get_system_prompt("entity_extraction", include_foundation=True) or ""

    try:
        result = await provider.generate(
            messages=[{"role": "user", "content": f"Extract entities and relationships from this text:\n\n{text}"}],
            system=system,
            temperature=0.2,
            max_tokens=8192,
        )
    except Exception as exc:
        logger.warning("LLM entity extraction call failed for doc %s", doc_id, exc_info=True)
        raise _LLMExtractionFailed(_describe_failure(exc)) from exc

    # The first JSON object anywhere in the reply — fenced, prose-led or bold-
    # labelled. `{}` means nothing parsed.
    content = result.content or ""
    # A repeated key ("relationships": [], "entities": [] after the full lists)
    # must not empty the reply; see llm_output.json_object.
    data = json_object(content, merge_duplicate_lists=True)
    if "entities" not in data and "relationships" not in data:
        # A reply that ran past the token limit is not JSON at all, but its
        # complete items are; reading none of them threw away a long report's
        # whole extraction.
        salvaged = {k: json_array_items(content, k) for k in ("entities", "relationships")}
        if salvaged["entities"] or salvaged["relationships"]:
            logger.warning("LLM extraction reply for doc %s was cut off; kept %d entities and %d relationships",
                           doc_id, len(salvaged["entities"]), len(salvaged["relationships"]))
            data = salvaged
    if not data:
        raise _LLMExtractionFailed("reply contained no JSON object")
    if "entities" not in data and "relationships" not in data:
        # Typically a list where an object was asked for: json_object then finds
        # the first *entity* inside it, which has neither key. Reading that as
        # the reply would be zero entities presented as a success.
        raise _LLMExtractionFailed("reply had no entities or relationships list")
    raw_entities = data.get("entities") or []
    raw_rels = data.get("relationships") or []
    if not isinstance(raw_entities, list) or not isinstance(raw_rels, list):
        raise _LLMExtractionFailed("reply's entities or relationships was not a list")

    skipped = 0
    entities: list[dict] = []
    for e in raw_entities:
        try:
            entities.append(_llm_entity(e, doc_id))
        except (TypeError, ValueError, AttributeError):
            skipped += 1
    relationships: list[dict] = []
    untyped: dict[str, int] = {}
    for r in raw_rels:
        try:
            rel = _llm_relationship(r, doc_id)
        except (TypeError, ValueError, AttributeError):
            skipped += 1
            continue
        if rel["rel_type"] is None:
            # Well-formed, but it states something about the reporting
            # ("REPORTED", "DOES_NOT_ESTABLISH"), not a relationship between
            # entities. Not malformed, so not a skipped item; counted here so
            # the loss is visible.
            raw_type = str(r.get("relationship_type", r.get("rel_type", "")))[:40]
            untyped[raw_type] = untyped.get(raw_type, 0) + 1
            continue
        relationships.append(rel)
    if skipped:
        logger.warning("LLM extraction for doc %s skipped %d malformed item(s)", doc_id, skipped)
    if untyped:
        logger.info("LLM extraction for doc %s dropped %d relationship(s) about the reporting rather than the entities: %s",
                    doc_id, sum(untyped.values()), untyped)

    # The same provenance rule the regex pass applies (G-8): a citation link
    # is not an indicator because the model, rather than a regex, read it.
    entities = _drop_model_sourcing(entities, text)
    _refang_model_indicators(entities, relationships)
    entities, relationships = _drop_undatable_dates(entities, relationships)
    entities, relationships = _drop_abstract_types(entities, relationships)
    _apply_vessel_hints(_apply_type_hints(entities), text)
    # Events named only in their date link are minted here, before endpoints
    # are checked: the timeline depends on them.
    _link_event_dates(entities, relationships)
    dropped = {"unlisted_endpoint": 0, "same_entity": 0}
    if resolve_endpoints:
        relationships, dropped, _ = _resolve_endpoints(entities, relationships)
        entities, relationships, same_entity = _resolve_countries(entities, relationships, text)
        dropped["same_entity"] += same_entity
    relationships, generic_dropped = _drop_generic_on_typed_pairs(relationships)
    return entities, relationships, skipped, {**dropped, "generic_on_typed_pair": generic_dropped}


async def extract_entities_llm(text: str, doc_id: str) -> ExtractionResult:
    """Extract entities using LLM. Returns (entities, relationships) with a record.

    ANY failure degrades to NLP — not just an unparseable reply but a provider
    that's unreachable/rate-limited/erroring (Ollama down, cloud 429/401/5xx).
    hybrid is the DEFAULT mode, so a provider hiccup must never 500 the ingest
    path (which creates the Document first). The degradation is now recorded on
    the result rather than only in the log.
    """
    try:
        entities, relationships, skipped, dropped = await _extract_with_llm(text, doc_id)
    except Exception as exc:
        reason = exc.reason if isinstance(exc, _LLMExtractionFailed) else f"extraction failed ({type(exc).__name__})"
        if not isinstance(exc, _LLMExtractionFailed):
            logger.warning("LLM entity extraction failed for doc %s", doc_id, exc_info=True)
        logger.warning("LLM extraction degraded to NLP for doc %s: %s", doc_id, reason)
        ents, rels = extract_entities_nlp(text, doc_id)
        return ExtractionResult(ents, rels, method="nlp", degraded=True, reason=reason)
    return ExtractionResult(entities, relationships, method="llm", skipped_items=skipped,
                            relationships_dropped_by_reason=dropped)


# Indicator types that are only ever the same entity when the value is the same.
# A copy of EXACT_MATCH_TYPES in graph_builder.resolve_entity_name, where it is a
# function local and so cannot be imported — keep the two in step.
_EXACT_MATCH_TYPES = frozenset({
    "IPAddress", "Domain", "URL", "EmailAddress", "Hash", "Vulnerability", "TTP",
})


def _merge_key(name: str) -> str:
    """The normalised value two extractions of one entity share."""
    return (name or "").strip().lower()


def _exact_match_only(entity: dict) -> bool:
    """Whether an entity may merge only on an identical value, never a fuzzy one.

    Regex output is a literal value lifted from the text (an address, a hash,
    a CVE id, a designation); a near-identical one is a different value.
    """
    return entity.get("method") == "regex" or entity.get("entity_type") in _EXACT_MATCH_TYPES


async def extract_entities_hybrid(text: str, doc_id: str) -> ExtractionResult:
    """Run both NLP and LLM extraction, merge results. LLM results take priority.

    When the LLM half fails the chunk is the NLP result, marked ``degraded``
    with the reason — it used to be the same NLP result with nothing to say so.
    """
    import jellyfish

    nlp_entities, nlp_rels = extract_entities_nlp(text, doc_id)
    try:
        llm_entities, llm_rels, skipped, dropped = await _extract_with_llm(text, doc_id, resolve_endpoints=False)
    except Exception as exc:
        reason = exc.reason if isinstance(exc, _LLMExtractionFailed) else f"extraction failed ({type(exc).__name__})"
        if not isinstance(exc, _LLMExtractionFailed):
            logger.warning("LLM half of hybrid extraction failed for doc %s", doc_id, exc_info=True)
        logger.warning("Hybrid extraction degraded to NLP for doc %s: %s", doc_id, reason)
        return ExtractionResult(nlp_entities, nlp_rels, method="nlp", degraded=True, reason=reason)

    # ── Entities ──────────────────────────────────────────────────────────
    # LLM entities are primary (semantic, well-typed, lean). From NLP add only
    # the deterministic REGEX entities (IPs/domains/hashes/CVEs/TTPs/equipment
    # designations) the LLM missed — NLP's spaCy entities over-extract and the
    # LLM already covers the semantic ones, so unioning them back in just
    # re-introduces the precision-killing noise the NLP-only pass fought.
    merged_entities = list(llm_entities)
    # Exact lookup over every LLM entity; fuzzy lookup only over LLM entities
    # whose type tolerates it. Indicators are matched by value or not at all:
    # 185.220.101.42/.43 score 0.971 Jaro-Winkler, CVE-2024-3400/3401 0.969 and
    # T1566.001/.002 0.956, all above the threshold that suits semantic names.
    llm_by_key: dict[str, dict] = {}
    fuzzy_pool: list[tuple[str, dict]] = []
    for llm_e in llm_entities:
        key = _merge_key(llm_e.get("name", ""))
        llm_by_key.setdefault(key, llm_e)
        if not _exact_match_only(llm_e):
            fuzzy_pool.append((key, llm_e))
    # A name the model gave as an alias is that entity too ("U.S. Navy" /
    # "Navy", "Department of Defense" / "DOD"); without this NLP's "Navy" was
    # kept as a second node. Names first, so an alias never displaces a name.
    for llm_e in llm_entities:
        for alias in llm_e.get("aliases") or []:
            if isinstance(alias, str) and alias.strip():
                llm_by_key.setdefault(_merge_key(alias), llm_e)
    # NLP names already kept. Deliberately *not* part of the fuzzy pool: adding
    # them there is what let each sibling indicator match the one kept before it.
    kept_nlp_keys: set[str] = set()
    # NLP name -> the model entity it merged into, when the two differ.
    merged_into: dict[str, str] = {}

    for e in nlp_entities:
        key = _merge_key(e.get("name", ""))
        match = llm_by_key.get(key)
        if match is None:
            # A vessel read from its hull number carries the written form as an
            # alias ("Hallgrim" / "Hallgrim (A-425)"), which is the name the
            # model usually returns; without this both were kept.
            match = next((llm_by_key[k] for k in map(_merge_key, e.get("aliases") or []) if k in llm_by_key), None)
        if match is None and not _exact_match_only(e):
            for pool_key, candidate in fuzzy_pool:
                if jellyfish.jaro_winkler_similarity(key, pool_key) >= 0.92:
                    match = candidate
                    break
        if match is not None:
            # Found by both — merge NLP attributes/confidence into the LLM entity.
            match["confidence"] = max(match.get("confidence", 0), e.get("confidence", 0))
            _merge_attributes(match, e)
            if match.get("name") != e.get("name"):
                merged_into[e.get("name", "")] = match["name"]
            continue
        if key in kept_nlp_keys:
            continue
        # Unmatched NLP entity: keep deterministic regex IOCs, plus high-signal
        # spaCy entities the LLM missed — known-list matches or repeated mentions
        # (confidence >= 0.8). This recovers real entities without re-admitting
        # the one-off spaCy over-extraction (base confidence 0.7 / short 0.5).
        if e.get("method") == "regex" or e.get("confidence", 0) >= 0.8:
            merged_entities.append(e)
            kept_nlp_keys.add(key)

    # ── Relationships ─────────────────────────────────────────────────────
    # A model edge must name listed entities: here a name of the merged set,
    # one of their aliases, an NLP name that merged into a model entity, or an
    # entity NLP extracted (which joins the merged set with it).
    llm_rels, endpoint_dropped, added = _resolve_endpoints(
        merged_entities, llm_rels, pool=nlp_entities, renamed=merged_into)
    kept_nlp_keys.update(_merge_key(e.get("name", "")) for e in added)
    for reason, n in endpoint_dropped.items():
        dropped[reason] = dropped.get(reason, 0) + n

    # LLM relations are typed + evidence-backed — primary. From NLP keep only
    # TYPED relations (verb-derived, OCCURRED_ON, regex RESOLVES_TO) the LLM
    # missed; drop blanket ASSOCIATED_WITH co-occurrence entirely — the LLM now
    # supplies the real relationships, so co-occurrence is pure noise.
    seen_rels = {(r["source_name"], r["target_name"], r["rel_type"]) for r in llm_rels}
    merged_rels = list(llm_rels)
    nlp_by_name = {e.get("name", ""): e for e in nlp_entities}
    for r in nlp_rels:
        if r["rel_type"] == "ASSOCIATED_WITH":
            continue
        # An endpoint whose entity merged into a differently named model entity
        # is renamed with it; otherwise the edge names an entity that is no
        # longer extracted and the graph build drops it.
        src = merged_into.get(r["source_name"], r["source_name"])
        tgt = merged_into.get(r["target_name"], r["target_name"])
        if src == tgt:
            continue
        if (src, tgt) != (r["source_name"], r["target_name"]):
            r = {**r, "source_name": src, "target_name": tgt}
        key = (r["source_name"], r["target_name"], r["rel_type"])
        if key not in seen_rels:
            seen_rels.add(key)
            merged_rels.append(r)
            # A typed edge read from the sentence is evidence for both ends. An
            # NLP endpoint below the keep threshold above ("U.S. Space Force",
            # named once) is kept with it; without it the graph build drops
            # the edge as naming an entity that was never extracted.
            for end in (r["source_name"], r["target_name"]):
                end_key = _merge_key(end)
                if end_key not in kept_nlp_keys and end_key not in llm_by_key and end in nlp_by_name:
                    merged_entities.append(nlp_by_name[end])
                    kept_nlp_keys.add(end_key)

    # One entity per state, over both halves: the model's "PRC government"
    # and NLP's "China" are the same node.
    merged_entities, merged_rels, same_entity = _resolve_countries(merged_entities, merged_rels, text)
    dropped["same_entity"] = dropped.get("same_entity", 0) + same_entity

    # A model association on a pair NLP read a typed relation for goes here,
    # once both halves are in.
    merged_rels, generic_dropped = _drop_generic_on_typed_pairs(merged_rels)
    dropped["generic_on_typed_pair"] = dropped.get("generic_on_typed_pair", 0) + generic_dropped

    # Re-resolve event_datetime over the merged set — catches cases where the
    # Event came from one method and its OCCURRED_ON Date from the other.
    _link_event_dates(merged_entities, merged_rels)

    # Naming-convention re-typing runs last, over the merged set: applying it
    # inside the LLM branch alone was ineffective, because an NLP entity of the
    # same name could still carry the generic type into the merge.
    _apply_vessel_hints(_apply_type_hints(merged_entities), text)

    return ExtractionResult(merged_entities, merged_rels, method="hybrid", skipped_items=skipped,
                            relationships_dropped_by_reason=dropped)
