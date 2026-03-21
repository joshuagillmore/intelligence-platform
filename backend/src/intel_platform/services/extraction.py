from __future__ import annotations

import json
import re

import spacy

_nlp = None

SPACY_TO_ENTITY_TYPE = {
    "PERSON": "Person",
    "ORG": "Organization",
    "GPE": "Location",
    "LOC": "Location",
    "FAC": "Location",
    "EVENT": "Event",
    "NORP": "Organization",
}

# Regex patterns for cyber-specific entities
IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
DOMAIN_PATTERN = re.compile(r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+(?:com|org|net|io|gov|mil|edu|info|onion|ru|uk|de|nl|fr|ua|cn)\b')
HASH_MD5 = re.compile(r'\b[a-fA-F0-9]{32}\b')
HASH_SHA1 = re.compile(r'\b[a-fA-F0-9]{40}\b')
HASH_SHA256 = re.compile(r'\b[a-fA-F0-9]{64}\b')
CVE_PATTERN = re.compile(r'\bCVE-\d{4}-\d{4,}\b')
MITRE_PATTERN = re.compile(r'\bT\d{4}(?:\.\d{3})?\b')
BTC_PATTERN = re.compile(r'\b(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,39}\b')

# Words that spaCy commonly misidentifies as entities
NOISE_WORDS = {
    "NETWORK", "INFRASTRUCTURE", "ASSESSMENT", "ANALYSIS", "REPORT",
    "NOTE", "SUBJECT", "SUMMARY", "FINDINGS", "GAPS", "KEY",
    "Backup C2", "Primary", "Secondary", "Administrative",
    "LIKELY", "UNLIKELY", "VERY LIKELY", "ALMOST CERTAIN", "ROUGHLY EVEN CHANCE",
    "VERY UNLIKELY", "ALMOST NO CHANCE",
    "Defense", "INTELLIGENCE", "OPEN SOURCE", "TECHNICAL",
    "EXECUTIVE", "FINANCIAL", "DIPLOMATIC",
}


def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def _extract_cyber_entities(text: str, doc_id: str) -> list[dict]:
    """Extract cyber-specific entities using regex patterns."""
    cyber_entities = []
    seen = set()

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

    for match in DOMAIN_PATTERN.finditer(text):
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
            cyber_entities.append({
                "name": h, "entity_type": "Hash",
                "source": doc_id, "method": "regex", "confidence": 0.95,
            })

    for match in HASH_SHA1.finditer(text):
        h = match.group().lower()
        if h not in seen and len(h) == 40:
            seen.add(h)
            cyber_entities.append({
                "name": h, "entity_type": "Hash",
                "source": doc_id, "method": "regex", "confidence": 0.9,
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

    return cyber_entities


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

    # 2. Extract NLP entities
    for ent in doc.ents:
        entity_type = SPACY_TO_ENTITY_TYPE.get(ent.label_)
        if not entity_type:
            continue
        name = ent.text.strip().strip("'\"")
        if not name or len(name) < 2:
            continue
        if name in NOISE_WORDS:
            continue
        if name in seen_names:
            continue
        entity = {
            "name": name, "entity_type": entity_type,
            "source": doc_id, "method": "nlp", "confidence": 0.7,
        }
        seen_names[name] = entity
        entities.append(entity)

    relationships = []
    for sent in doc.sents:
        sent_entities = [
            seen_names[ent.text.strip()]
            for ent in sent.ents
            if ent.text.strip() in seen_names
        ]
        for i, e1 in enumerate(sent_entities):
            for e2 in sent_entities[i + 1:]:
                relationships.append({
                    "source_name": e1["name"], "target_name": e2["name"],
                    "rel_type": "ASSOCIATED_WITH", "confidence": 0.5,
                    "source": doc_id, "method": "nlp",
                })

    return entities, relationships


async def extract_entities_llm(text: str, doc_id: str) -> tuple[list[dict], list[dict]]:
    """Extract entities using LLM. Returns (entities, relationships)."""
    from intel_platform.config import settings

    provider = None
    if settings.cohere_api_key:
        from intel_platform.llm.cohere_provider import CohereProvider
        provider = CohereProvider(api_key=settings.cohere_api_key)
    elif settings.anthropic_api_key:
        from intel_platform.llm.anthropic import AnthropicProvider
        provider = AnthropicProvider(api_key=settings.anthropic_api_key)
    elif settings.openai_api_key:
        from intel_platform.llm.openai_provider import OpenAIProvider
        provider = OpenAIProvider(api_key=settings.openai_api_key)

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
            entities.append({
                "name": e.get("name", ""),
                "entity_type": e.get("entity_type", "Person"),
                "source": doc_id,
                "method": "llm",
                "confidence": float(e.get("confidence", 0.85)),
                "aliases": e.get("aliases", []),
            })

        relationships = []
        for r in data.get("relationships", []):
            relationships.append({
                "source_name": r.get("source_entity", r.get("source", "")),
                "target_name": r.get("target_entity", r.get("target", "")),
                "rel_type": r.get("relationship_type", r.get("rel_type", "ASSOCIATED_WITH")),
                "confidence": float(r.get("confidence", 0.7)),
                "source": doc_id,
                "method": "llm",
            })

        return entities, relationships
    except (json.JSONDecodeError, KeyError, ValueError):
        # If LLM response isn't valid JSON, fall back to NLP
        return extract_entities_nlp(text, doc_id)


async def extract_entities_hybrid(text: str, doc_id: str) -> tuple[list[dict], list[dict]]:
    """Run both NLP and LLM extraction, merge results. LLM results take priority."""
    nlp_entities, nlp_rels = extract_entities_nlp(text, doc_id)
    llm_entities, llm_rels = await extract_entities_llm(text, doc_id)

    # LLM entities are primary
    seen_names = {e["name"].lower() for e in llm_entities}

    # Add NLP entities not found by LLM
    merged_entities = list(llm_entities)
    for e in nlp_entities:
        if e["name"].lower() not in seen_names:
            merged_entities.append(e)
            seen_names.add(e["name"].lower())

    # Merge relationships, dedup by source+target+type
    seen_rels = {(r["source_name"], r["target_name"], r["rel_type"]) for r in llm_rels}
    merged_rels = list(llm_rels)
    for r in nlp_rels:
        key = (r["source_name"], r["target_name"], r["rel_type"])
        if key not in seen_rels:
            merged_rels.append(r)

    return merged_entities, merged_rels
