from __future__ import annotations

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
