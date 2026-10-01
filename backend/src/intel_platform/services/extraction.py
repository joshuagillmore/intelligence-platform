from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

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
    """

    method: str
    degraded: bool
    reason: str
    skipped_items: int

    def __new__(cls, entities: list[dict], relationships: list[dict], *, method: str,
                degraded: bool = False, reason: str = "", skipped_items: int = 0):
        self = super().__new__(cls, (entities, relationships))
        self.method = method
        self.degraded = degraded
        self.reason = reason
        self.skipped_items = skipped_items
        return self

    def __getnewargs_ex__(self):
        # copy and pickle rebuild a tuple subclass from tuple(self); without
        # this they call __new__ with one argument and fail.
        return (self[0], self[1]), {
            "method": self.method, "degraded": self.degraded,
            "reason": self.reason, "skipped_items": self.skipped_items,
        }

    @property
    def meta(self) -> dict:
        return {
            "method": self.method,
            "degraded": self.degraded,
            "reason": self.reason,
            "skipped_items": self.skipped_items,
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
    # "May 7, 2021" or "May 2021"
    re.compile(rf'\b{MONTH_NAMES}\s+\d{{1,2}},?\s+\d{{4}}\b'),
    re.compile(rf'\b{MONTH_NAMES}\s+\d{{4}}\b'),
    # "2021-05-07" ISO format
    re.compile(r'\b\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b'),
    # "Q1 2026", "Q3 2021"
    re.compile(r'\bQ[1-4]\s+\d{4}\b'),
]

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


def _product_type(ent) -> str:
    """"Hardware" or "Software" when the noun this name modifies says so, else ""."""
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
    return ""


def _normalize_rel_type(raw: str) -> str:
    """Collapse an unrecognized LLM relationship type to ASSOCIATED_WITH."""
    rt = (raw or "").strip().upper()
    return rt if rt in _VALID_REL_TYPES else "ASSOCIATED_WITH"


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
    for pattern in DATE_PATTERNS:
        for match in pattern.finditer(text):
            date_str = match.group().strip()
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
        name = e.get("name") or ""
        if not name:
            continue
        for m in _name_pattern(name).finditer(sent_text):
            spans.append((m.start(), m.end(), e))
    return spans


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
        if stripped and stripped != name:
            name = stripped
            e["name"] = name
            name_lower = name.lower().strip()

        # Drop report boilerplate and bare nationality demonyms — high-frequency
        # false positives, not analytic entities.
        if name_lower in REPORT_BOILERPLATE or name_lower in DEMONYMS:
            continue

        # Skip all-caps headers (likely document section headings), but keep known acronyms
        if name.isupper() and len(name) > 3 and name not in known_acro:
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
        if e.get("entity_type") in ("Software", "Hardware"):
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
    entities = _apply_type_hints(_postprocess_entities(entities))

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

    def _resolve_anaphor(tok) -> dict | None:
        if tok.lemma_.lower() not in _ACTOR_ANAPHORS:
            return None
        if not any(c.dep_ == "det" and c.lower_ in ("the", "this", "that") for c in tok.children):
            return None
        earlier = [e for start, e in actor_mentions if start < tok.idx]
        return earlier[-1] if earlier else None

    for sent in doc.sents:
        sent_text = sent.text
        sent_entities_list = []

        # spaCy-detected entities in this sentence. Looked up by the name the
        # entity ended up with: postprocessing strips determiners and quotes,
        # and a lookup by the raw span text missed every entity it renamed.
        for ent in sent.ents:
            name = ent.text.strip()
            match = seen_names.get(name) or seen_names.get(_strip_determiner(name.strip("'\"")))
            if match is not None and match not in sent_entities_list:
                sent_entities_list.append(match)

        # Regex-extracted entities that appear in this sentence text
        for e in entities:
            if e.get("method") == "regex" and e["name"] in sent_text and e not in sent_entities_list:
                sent_entities_list.append(e)

        # The typed stage also sees entities spaCy did not tag in this sentence
        # but which were extracted elsewhere in the text: its NER is not
        # consistent across sentences, and a lower-cased "hallgrim" is still
        # Hallgrim. The co-occurrence fallback below keeps to tagged mentions.
        typed_candidates = list(sent_entities_list)
        for e in entities:
            if e not in typed_candidates and len(e["name"]) >= _CASELESS_MIN \
                    and _name_pattern(e["name"]).search(sent_text):
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

            subj_ent = _verb_subject(token, sent, mention_spans, _resolve_anaphor)
            if subj_ent is None:
                continue
            for obj_ent in _verb_objects(token, rel_type_from_verb, sent, mention_spans):
                if obj_ent["name"] == subj_ent["name"] or obj_ent.get("entity_type") == "Date":
                    # A date is when, not what: it is never a node to point at.
                    continue
                _add_rel(subj_ent["name"], obj_ent["name"],
                         _refine_rel_type(rel_type_from_verb, obj_ent), 0.7, sent_text)

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
                # ASSOCIATED_WITH is noise — only emit within the window, and never
                # on top of a pair a typed/pattern relation already links.
                if (j - i) <= COOCCURRENCE_WINDOW and frozenset((e1["name"], e2["name"])) not in linked_pairs:
                    _add_rel(e1["name"], e2["name"], "ASSOCIATED_WITH", 0.5, sent_text)

    # Resolve event_datetime on Event entities from their OCCURRED_ON Date links
    _link_event_dates(entities, relationships)

    return ExtractionResult(entities, relationships, method="nlp")


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


async def _extract_with_llm(text: str, doc_id: str) -> tuple[list[dict], list[dict], int]:
    """The LLM half alone: (entities, relationships, skipped_items).

    Raises ``_LLMExtractionFailed`` with a reason when the model produced
    nothing usable. The callers decide what the fallback is.
    """
    # Use the extraction-specific provider selection (routes to local Ollama
    # when extraction_llm_provider=ollama; respects runtime overrides otherwise).
    # Resolved inside the failure boundary: the lookup reads the key store, and
    # a failure there escaped as a 500 from /ingest.
    from intel_platform.llm.providers import _get_extraction_provider
    from intel_platform.services.llm_output import json_object

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
    data = json_object(result.content or "")
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
    for r in raw_rels:
        try:
            relationships.append(_llm_relationship(r, doc_id))
        except (TypeError, ValueError, AttributeError):
            skipped += 1
    if skipped:
        logger.warning("LLM extraction for doc %s skipped %d malformed item(s)", doc_id, skipped)

    # The same provenance rule the regex pass applies (G-8): a citation link
    # is not an indicator because the model, rather than a regex, read it.
    entities = _drop_model_sourcing(entities, text)
    _apply_type_hints(entities)
    _link_event_dates(entities, relationships)
    return entities, relationships, skipped


async def extract_entities_llm(text: str, doc_id: str) -> ExtractionResult:
    """Extract entities using LLM. Returns (entities, relationships) with a record.

    ANY failure degrades to NLP — not just an unparseable reply but a provider
    that's unreachable/rate-limited/erroring (Ollama down, cloud 429/401/5xx).
    hybrid is the DEFAULT mode, so a provider hiccup must never 500 the ingest
    path (which creates the Document first). The degradation is now recorded on
    the result rather than only in the log.
    """
    try:
        entities, relationships, skipped = await _extract_with_llm(text, doc_id)
    except Exception as exc:
        reason = exc.reason if isinstance(exc, _LLMExtractionFailed) else f"extraction failed ({type(exc).__name__})"
        if not isinstance(exc, _LLMExtractionFailed):
            logger.warning("LLM entity extraction failed for doc %s", doc_id, exc_info=True)
        logger.warning("LLM extraction degraded to NLP for doc %s: %s", doc_id, reason)
        ents, rels = extract_entities_nlp(text, doc_id)
        return ExtractionResult(ents, rels, method="nlp", degraded=True, reason=reason)
    return ExtractionResult(entities, relationships, method="llm", skipped_items=skipped)


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
        llm_entities, llm_rels, skipped = await _extract_with_llm(text, doc_id)
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
    # NLP names already kept. Deliberately *not* part of the fuzzy pool: adding
    # them there is what let each sibling indicator match the one kept before it.
    kept_nlp_keys: set[str] = set()

    for e in nlp_entities:
        key = _merge_key(e.get("name", ""))
        match = llm_by_key.get(key)
        if match is None and not _exact_match_only(e):
            for pool_key, candidate in fuzzy_pool:
                if jellyfish.jaro_winkler_similarity(key, pool_key) >= 0.92:
                    match = candidate
                    break
        if match is not None:
            # Found by both — merge NLP attributes/confidence into the LLM entity.
            match["confidence"] = max(match.get("confidence", 0), e.get("confidence", 0))
            _merge_attributes(match, e)
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
    # LLM relations are typed + evidence-backed — primary. From NLP keep only
    # TYPED relations (verb-derived, OCCURRED_ON, regex RESOLVES_TO) the LLM
    # missed; drop blanket ASSOCIATED_WITH co-occurrence entirely — the LLM now
    # supplies the real relationships, so co-occurrence is pure noise.
    seen_rels = {(r["source_name"], r["target_name"], r["rel_type"]) for r in llm_rels}
    merged_rels = list(llm_rels)
    for r in nlp_rels:
        if r["rel_type"] == "ASSOCIATED_WITH":
            continue
        key = (r["source_name"], r["target_name"], r["rel_type"])
        if key not in seen_rels:
            seen_rels.add(key)
            merged_rels.append(r)

    # Re-resolve event_datetime over the merged set — catches cases where the
    # Event came from one method and its OCCURRED_ON Date from the other.
    _link_event_dates(merged_entities, merged_rels)

    # Naming-convention re-typing runs last, over the merged set: applying it
    # inside the LLM branch alone was ineffective, because an NLP entity of the
    # same name could still carry the generic type into the merge.
    _apply_type_hints(merged_entities)

    return ExtractionResult(merged_entities, merged_rels, method="hybrid", skipped_items=skipped)
