from __future__ import annotations

import json

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


def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def extract_entities_nlp(text: str, doc_id: str) -> tuple[list[dict], list[dict]]:
    if not text.strip():
        return [], []

    nlp = _get_nlp()
    doc = nlp(text)

    seen_names: dict[str, dict] = {}
    entities = []

    for ent in doc.ents:
        entity_type = SPACY_TO_ENTITY_TYPE.get(ent.label_)
        if not entity_type:
            continue
        name = ent.text.strip()
        if not name or len(name) < 2:
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
