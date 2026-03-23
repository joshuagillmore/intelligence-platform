from __future__ import annotations

import json
import logging
import re

import spacy

from intel_platform.data import (
    get_known_locations, get_known_organizations, get_known_persons,
    get_known_acronyms, get_noise_words, get_location_keywords,
    get_org_keywords, get_tlds,
)

logger = logging.getLogger(__name__)

_nlp = None

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


def _extract_cyber_entities(text: str, doc_id: str) -> list[dict]:
    """Extract cyber-specific entities using regex patterns."""
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
        domain = match.group().lower()
        if domain not in seen and "." in domain:
            seen.add(domain)
            cyber_entities.append({
                "name": domain, "entity_type": "Domain",
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

    return cyber_entities


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


def extract_entities_nlp(text: str, doc_id: str) -> tuple[list[dict], list[dict]]:
    if not text.strip():
        return [], []

    nlp = _get_nlp()
    doc = nlp(text)

    seen_names: dict[str, dict] = {}
    entities = []

    # 1. Extract cyber entities via regex first
    cyber_entities = _extract_cyber_entities(text, doc_id)
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
            "name": name, "entity_type": entity_type,
            "source": doc_id, "method": "nlp", "confidence": confidence,
        }
        seen_names[name] = entity
        entities.append(entity)

    # 4. Postprocess to fix misclassifications
    entities = _postprocess_entities(entities)

    # 5. Optional coreference resolution
    from intel_platform.config import settings
    if settings.coreference_enabled:
        entities = _apply_coreference(doc, entities)

    # Rebuild seen_names after postprocessing (names may have changed)
    seen_names = {e["name"]: e for e in entities}

    # ── Relationship extraction ────────────────────────────────────────────
    # Load verb-to-relationship mappings from YAML
    from intel_platform.data import get_verb_mappings, get_discourse_markers
    verb_map = get_verb_mappings()
    discourse_markers = get_discourse_markers()

    relationships = []
    seen_rel_keys: set[tuple[str, str, str]] = set()

    def _add_rel(src_name: str, tgt_name: str, rel_type: str, confidence: float) -> None:
        key = (src_name, tgt_name, rel_type)
        if key not in seen_rel_keys:
            seen_rel_keys.add(key)
            relationships.append({
                "source_name": src_name, "target_name": tgt_name,
                "rel_type": rel_type, "confidence": confidence,
                "source": doc_id, "method": "nlp",
            })

    prev_sent_entities: list[dict] = []

    for sent in doc.sents:
        sent_text = sent.text
        sent_entities_list = []

        # spaCy-detected entities in this sentence
        for ent in sent.ents:
            name = ent.text.strip()
            if name in seen_names:
                sent_entities_list.append(seen_names[name])

        # Regex-extracted entities that appear in this sentence text
        for e in entities:
            if e.get("method") == "regex" and e["name"] in sent_text and e not in sent_entities_list:
                sent_entities_list.append(e)

        # ── Stage A: Dependency-parse relationship extraction ──
        # Find the root verb and its subject/object via dependency labels
        for token in sent:
            if token.pos_ != "VERB":
                continue
            verb_lemma = token.lemma_.lower()
            rel_type_from_verb = verb_map.get(verb_lemma)
            if not rel_type_from_verb:
                continue

            # Find subject and object spans
            subj_ent = None
            obj_ent = None
            for child in token.children:
                if child.dep_ in ("nsubj", "nsubjpass", "agent") and not subj_ent:
                    # Find which entity this token belongs to
                    for e in sent_entities_list:
                        if child.text in e["name"] or e["name"] in sent_text[child.idx - sent.start_char:child.idx - sent.start_char + len(e["name"]) + 20]:
                            subj_ent = e
                            break
                elif child.dep_ in ("dobj", "pobj", "attr") and not obj_ent:
                    for e in sent_entities_list:
                        if child.text in e["name"] or e["name"] in sent_text[child.idx - sent.start_char:child.idx - sent.start_char + len(e["name"]) + 20]:
                            obj_ent = e
                            break

            if subj_ent and obj_ent and subj_ent["name"] != obj_ent["name"]:
                _add_rel(subj_ent["name"], obj_ent["name"], rel_type_from_verb, 0.7)

        # ── Stage B: Co-occurrence relationships (fallback) ──
        for i, e1 in enumerate(sent_entities_list):
            for e2 in sent_entities_list[i + 1:]:
                if e1.get("entity_type") == "Date" or e2.get("entity_type") == "Date":
                    if e1.get("entity_type") == "Date":
                        src, tgt = e2, e1
                    else:
                        src, tgt = e1, e2
                    _add_rel(src["name"], tgt["name"], "OCCURRED_ON", 0.7)
                else:
                    _add_rel(e1["name"], e2["name"], "ASSOCIATED_WITH", 0.5)

        # ── Stage C: Cross-sentence relationship detection ──
        if prev_sent_entities and sent_entities_list:
            sent_lower = sent_text.lower()
            has_discourse_marker = any(marker in sent_lower for marker in discourse_markers)
            if has_discourse_marker:
                for prev_e in prev_sent_entities:
                    for curr_e in sent_entities_list:
                        if prev_e["name"] != curr_e["name"]:
                            _add_rel(prev_e["name"], curr_e["name"], "ASSOCIATED_WITH", 0.4)

        prev_sent_entities = sent_entities_list

    return entities, relationships


async def extract_entities_llm(text: str, doc_id: str) -> tuple[list[dict], list[dict]]:
    """Extract entities using LLM. Returns (entities, relationships)."""
    from intel_platform.config import settings

    # Use the centralized provider selection (respects runtime overrides)
    from intel_platform.api.routes.llm import _get_provider
    provider = _get_provider()

    if not provider:
        # Fallback to NLP if no LLM configured
        return extract_entities_nlp(text, doc_id)

    from intel_platform.llm.skills.loader import SkillsLoader
    loader = SkillsLoader()
    system = loader.get_system_prompt("entity_extraction", include_foundation=True) or ""

    result = await provider.generate(
        messages=[{"role": "user", "content": f"Extract entities and relationships from this text:\n\n{text}"}],
        system=system,
        temperature=0.2,
        max_tokens=8192,
    )

    try:
        # Try to parse JSON from response
        content = result.content
        # Find JSON in response (may be wrapped in markdown code blocks)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        data = json.loads(content.strip())

        entities = []
        for e in data.get("entities", []):
            entity = {
                "name": e.get("name", ""),
                "entity_type": e.get("entity_type", "Person"),
                "source": doc_id,
                "method": "llm",
                "confidence": float(e.get("confidence", 0.85)),
                "aliases": e.get("aliases", []),
            }
            # Pass through entity attributes from LLM
            attrs = e.get("attributes", {})
            if attrs:
                entity["attributes"] = attrs
            entities.append(entity)

        relationships = []
        for r in data.get("relationships", []):
            relationships.append({
                "source_name": r.get("source_entity", r.get("source", "")),
                "target_name": r.get("target_entity", r.get("target", "")),
                "rel_type": r.get("relationship_type", r.get("rel_type", "ASSOCIATED_WITH")),
                "confidence": float(r.get("confidence", 0.7)),
                "source": doc_id,
                "method": "llm",
                "evidence": r.get("evidence", ""),
            })

        return entities, relationships
    except (json.JSONDecodeError, KeyError, ValueError):
        # Log failure for debugging, fall back to NLP
        logger.warning("LLM entity extraction returned invalid JSON for doc %s, falling back to NLP", doc_id)
        return extract_entities_nlp(text, doc_id)


async def extract_entities_hybrid(text: str, doc_id: str) -> tuple[list[dict], list[dict]]:
    """Run both NLP and LLM extraction, merge results. LLM results take priority."""
    import jellyfish

    nlp_entities, nlp_rels = extract_entities_nlp(text, doc_id)
    llm_entities, llm_rels = await extract_entities_llm(text, doc_id)

    # LLM entities are primary; build a name lookup for fuzzy matching
    merged_entities = list(llm_entities)
    llm_name_list = [e["name"].lower() for e in llm_entities]

    # Add NLP entities not found by LLM (using fuzzy matching)
    for e in nlp_entities:
        e_lower = e["name"].lower()
        # Check exact match first
        if e_lower in llm_name_list:
            # Entity found by both methods — boost confidence on LLM version
            for llm_e in merged_entities:
                if llm_e["name"].lower() == e_lower:
                    llm_e["confidence"] = max(llm_e["confidence"], e["confidence"])
                    break
            continue
        # Check fuzzy match
        matched = False
        for llm_name in llm_name_list:
            if jellyfish.jaro_winkler_similarity(e_lower, llm_name) >= 0.90:
                matched = True
                break
        if not matched:
            merged_entities.append(e)
            llm_name_list.append(e_lower)

    # Merge relationships, dedup by source+target+type
    seen_rels = {(r["source_name"], r["target_name"], r["rel_type"]) for r in llm_rels}
    merged_rels = list(llm_rels)
    for r in nlp_rels:
        key = (r["source_name"], r["target_name"], r["rel_type"])
        if key not in seen_rels:
            merged_rels.append(r)

    return merged_entities, merged_rels
