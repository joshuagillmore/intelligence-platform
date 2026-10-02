"""A relationship is kept only with a verbatim quote that names both ends.

The model asserted relationships the text does not state: typed relationship
precision in llm and hybrid modes was 0.13-0.17 on the eval corpus, and one
recorded reply carried the prompt's own Gerasimov/Mozdok example into a
document that never mentions either. The prompt now asks for the exact
sentence; the parser checks it. An edge is kept only when its evidence,
whitespace-normalised and case-insensitive, is a substring of the chunk text
and names both endpoints (by name, a listed alias, or a known form of a
country). The kept edge carries the chunk's own text as ``evidence`` and its
character offset as ``evidence_offset``. NLP edges are read from a sentence,
so they record that sentence and its offset the same way.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from intel_platform.llm.base import LLMResponse
from intel_platform.services.extraction import (
    _locate_evidence,
    extract_entities_hybrid,
    extract_entities_llm,
    extract_entities_nlp,
)

TEXT = (
    "Weekly maritime summary.\n\n"
    "The Kalvik Coast Guard received two radar sets\nfrom Ostrava Shipping in March 2026. "
    "Its commander, Admiral Petra Lund, inspected the sets at Port Selma. "
    "OSC is a subsidiary of Varn Holdings.\n\n"
    "Analysts expect further deliveries."
)
FIRST = "The Kalvik Coast Guard received two radar sets\nfrom Ostrava Shipping in March 2026."
SECOND = "Its commander, Admiral Petra Lund, inspected the sets at Port Selma."
THIRD = "OSC is a subsidiary of Varn Holdings."

ENTITIES = [
    {"name": "Kalvik Coast Guard", "entity_type": "Organization", "confidence": 0.95},
    {"name": "Ostrava Shipping", "entity_type": "Organization", "aliases": ["OSC"], "confidence": 0.95},
    {"name": "Petra Lund", "entity_type": "Person", "aliases": ["Admiral Lund"], "confidence": 0.95},
    {"name": "Port Selma", "entity_type": "Location", "confidence": 0.95},
    {"name": "Varn Holdings", "entity_type": "Organization", "confidence": 0.95},
    {"name": "March 2026", "entity_type": "Date", "confidence": 0.95},
    {"name": "Kalvik radar delivery", "entity_type": "Event", "confidence": 0.85},
]


def _rel(src: str, tgt: str, rel_type: str, evidence: str | None) -> dict:
    r = {"source_entity": src, "target_entity": tgt, "relationship_type": rel_type, "confidence": 0.9}
    if evidence is not None:
        r["evidence"] = evidence
    return r


class _Canned:
    def __init__(self, content: str):
        self._content = content

    def name(self) -> str:
        return "canned"

    async def generate(self, **_kw) -> LLMResponse:
        return LLMResponse(content=self._content, model="canned")


async def _llm(relationships: list[dict], text: str = TEXT, mode: str = "llm"):
    reply = json.dumps({"entities": ENTITIES, "relationships": relationships})
    fn = extract_entities_llm if mode == "llm" else extract_entities_hybrid
    with patch("intel_platform.llm.providers._get_extraction_provider",
               new=AsyncMock(return_value=_Canned(reply))):
        return await fn(text, "doc-evidence")


def _edge(rels: list[dict], src: str, tgt: str, rel_type: str) -> dict | None:
    return next((r for r in rels if (r["source_name"], r["target_name"], r["rel_type"]) == (src, tgt, rel_type)),
                None)


# ── Locating a quote in the chunk ───────────────────────────────────────────


def test_a_quote_is_located_at_its_offset_in_the_chunk():
    start, end = _locate_evidence(TEXT, SECOND)
    assert start == TEXT.index(SECOND)
    assert TEXT[start:end] == SECOND


def test_whitespace_and_case_differences_are_tolerated():
    """The model writes a line break as a space and may change the case."""
    quote = "the kalvik coast guard received two radar   sets from ostrava shipping in march 2026."
    start, end = _locate_evidence(TEXT, quote)
    assert TEXT[start:end] == FIRST


def test_typographic_quotes_and_dashes_match_their_plain_forms():
    text = "The board said the “Kestrel” programme — not Osprey — was cancelled."
    start, end = _locate_evidence(text, 'the "Kestrel" programme - not Osprey - was cancelled')
    assert text[start:end] == "the “Kestrel” programme — not Osprey — was cancelled"


def test_a_quote_wrapped_in_quotation_marks_is_unwrapped():
    start, end = _locate_evidence(TEXT, f'"{THIRD}"')
    assert TEXT[start:end] == THIRD


def test_a_paraphrase_is_not_located():
    assert _locate_evidence(TEXT, "Petra Lund commands the Kalvik Coast Guard.") is None
    assert _locate_evidence(TEXT, "") is None
    assert _locate_evidence("", SECOND) is None


def test_an_elided_quote_is_not_verbatim():
    assert _locate_evidence(TEXT, "The Kalvik Coast Guard received ... from Ostrava Shipping") is None


# ── The LLM relationship path ───────────────────────────────────────────────


async def test_an_edge_with_verbatim_evidence_is_kept_with_its_span_and_offset():
    result = await _llm([_rel("Kalvik Coast Guard", "Ostrava Shipping", "SUPPLIED_BY", FIRST.replace("\n", " "))])
    _, rels = result
    edge = _edge(rels, "Kalvik Coast Guard", "Ostrava Shipping", "SUPPLIED_BY")
    assert edge is not None
    # The chunk's own text, line break included, so offset + length locate it.
    assert edge["evidence"] == FIRST
    assert edge["evidence_offset"] == TEXT.index(FIRST)
    assert TEXT[edge["evidence_offset"]:edge["evidence_offset"] + len(edge["evidence"])] == edge["evidence"]
    assert "evidence_not_verbatim" not in result.relationships_dropped_by_reason or (
        result.relationships_dropped_by_reason["evidence_not_verbatim"] == 0)


async def test_paraphrased_evidence_is_dropped_and_counted():
    result = await _llm([_rel("Kalvik Coast Guard", "Petra Lund", "COMMANDED_BY",
                              "Petra Lund commands the Kalvik Coast Guard")])
    _, rels = result
    assert _edge(rels, "Kalvik Coast Guard", "Petra Lund", "COMMANDED_BY") is None
    assert result.relationships_dropped_by_reason["evidence_not_verbatim"] == 1


async def test_an_edge_without_evidence_is_dropped():
    result = await _llm([_rel("Kalvik Coast Guard", "Petra Lund", "COMMANDED_BY", None)])
    assert result[1] == []
    assert result.relationships_dropped_by_reason["evidence_not_verbatim"] == 1


async def test_evidence_naming_only_one_endpoint_is_dropped_and_counted():
    """Verbatim, but the sentence never names the coast guard."""
    result = await _llm([_rel("Kalvik Coast Guard", "Port Selma", "LOCATED_AT", SECOND)])
    _, rels = result
    assert _edge(rels, "Kalvik Coast Guard", "Port Selma", "LOCATED_AT") is None
    assert result.relationships_dropped_by_reason["evidence_missing_endpoint"] == 1


async def test_an_endpoint_named_in_the_evidence_by_a_listed_alias_counts():
    result = await _llm([_rel("Ostrava Shipping", "Varn Holdings", "BELONGS_TO", THIRD)])
    edge = _edge(result[1], "Ostrava Shipping", "Varn Holdings", "BELONGS_TO")
    assert edge is not None
    assert edge["evidence_offset"] == TEXT.index(THIRD)


async def test_a_person_named_by_surname_counts():
    text = "Admiral Petra Lund took command in May. Lund then moved the flotilla to Port Selma."
    quote = "Lund then moved the flotilla to Port Selma."
    result = await _llm([_rel("Petra Lund", "Port Selma", "LOCATED_AT", quote)], text=text)
    edge = _edge(result[1], "Petra Lund", "Port Selma", "LOCATED_AT")
    assert edge is not None
    assert edge["evidence_offset"] == text.index(quote)


async def test_a_country_named_by_its_government_form_counts():
    text = "The Kremlin supplied the radar sets to the Kalvik Coast Guard."
    reply_entities = [
        {"name": "Russia", "entity_type": "Location", "confidence": 0.9},
        {"name": "Kalvik Coast Guard", "entity_type": "Organization", "confidence": 0.9},
    ]
    reply = json.dumps({"entities": reply_entities, "relationships": [
        _rel("Kalvik Coast Guard", "Russia", "SUPPLIED_BY", text)]})
    with patch("intel_platform.llm.providers._get_extraction_provider",
               new=AsyncMock(return_value=_Canned(reply))):
        _, rels = await extract_entities_llm(text, "doc-kremlin")
    edge = _edge(rels, "Kalvik Coast Guard", "Russia", "SUPPLIED_BY")
    assert edge is not None
    assert edge["evidence_offset"] == 0


async def test_a_date_link_needs_the_date_in_the_evidence_but_not_the_event_name():
    """An event the model names itself ("Kalvik radar delivery") is not in the
    text; the date that dates it must be."""
    result = await _llm([
        _rel("Kalvik radar delivery", "March 2026", "OCCURRED_ON", FIRST),
        _rel("Kalvik radar delivery", "March 2026", "OCCURRED_ON", SECOND),
    ])
    _, rels = result
    kept = [r for r in rels if r["rel_type"] == "OCCURRED_ON"]
    assert len(kept) == 1
    assert kept[0]["evidence"] == FIRST
    assert result.relationships_dropped_by_reason["evidence_missing_endpoint"] == 1


async def test_an_unverified_date_link_does_not_date_the_event():
    result = await _llm([_rel("Kalvik radar delivery", "March 2026", "OCCURRED_ON",
                              "The delivery happened in March 2026")])
    ents, _ = result
    event = next(e for e in ents if e["name"] == "Kalvik radar delivery")
    assert not (event.get("attributes") or {}).get("event_datetime")


async def test_a_quote_from_another_text_is_dropped():
    """The recorded reply that repeated the prompt's own example."""
    result = await _llm([_rel("Kalvik Coast Guard", "Port Selma", "DEPLOYED_AT",
                              "General Valery Gerasimov ordered the deployment of the 76th Guards Air Assault "
                              "Division to the Mozdok Airbase")])
    assert result[1] == []
    assert result.relationships_dropped_by_reason["evidence_not_verbatim"] == 1


async def test_hybrid_applies_the_rule_to_the_model_edges():
    result = await _llm([
        _rel("Kalvik Coast Guard", "Ostrava Shipping", "SUPPLIED_BY", FIRST),
        _rel("Kalvik Coast Guard", "Petra Lund", "COMMANDED_BY", "Lund leads the coast guard"),
    ], mode="hybrid")
    _, rels = result
    assert result.method == "hybrid"
    assert _edge(rels, "Kalvik Coast Guard", "Ostrava Shipping", "SUPPLIED_BY")["evidence_offset"] == TEXT.index(FIRST)
    assert _edge(rels, "Kalvik Coast Guard", "Petra Lund", "COMMANDED_BY") is None
    assert result.relationships_dropped_by_reason["evidence_not_verbatim"] == 1
    for r in rels:
        off = r.get("evidence_offset", -1)
        if off >= 0:
            assert TEXT[off:off + len(r["evidence"])] == r["evidence"], r


# ── NLP relationships record their sentence the same way ───────────────────

NLP_TEXT = (
    "Situation report.\n\n"
    "Weather in the region was poor. Iran transferred missiles to Russia in May 2024.\n\n"
    "Further reporting is expected."
)


def test_nlp_relationships_record_their_sentence_and_offset():
    _, rels = extract_entities_nlp(NLP_TEXT, "doc-nlp")
    edge = _edge(rels, "Russia", "Iran", "SUPPLIED_BY")
    assert edge is not None, rels
    sentence = "Iran transferred missiles to Russia in May 2024."
    assert edge["evidence"] == sentence
    assert edge["evidence_offset"] == NLP_TEXT.index(sentence)


def test_every_nlp_evidence_is_the_chunk_text_at_its_offset():
    text = (
        "The Kalvik Coast Guard received two radar sets from Ostrava Shipping. "
        "Ostrava Shipping is headquartered in Port Selma.\n"
        "Admiral Petra Lund, commander of the Kalvik Coast Guard, visited Port Selma."
    )
    _, rels = extract_entities_nlp(text, "doc-nlp-2")
    assert rels
    for r in rels:
        off = r["evidence_offset"]
        assert off >= 0, r
        assert text[off:off + len(r["evidence"])] == r["evidence"], r


def test_a_heading_glued_to_a_sentence_is_left_out_of_the_evidence():
    """spaCy joins a heading to the sentence under it; the evidence is the
    paragraph that names both ends, not the heading."""
    text = "Russia\n\nIran transferred missiles to Russia in May 2024."
    _, rels = extract_entities_nlp(text, "doc-nlp-3")
    edge = _edge(rels, "Russia", "Iran", "SUPPLIED_BY")
    assert edge is not None, rels
    assert edge["evidence"] == "Iran transferred missiles to Russia in May 2024."
    assert edge["evidence_offset"] == text.index("Iran transferred")


def test_a_defanged_chunk_keeps_offsets_into_the_original_text():
    text = "Intro line.\n\nThe actor Volt Typhoon used evil-c2[.]com for command and control."
    _, rels = extract_entities_nlp(text, "doc-nlp-4")
    for r in rels:
        off = r["evidence_offset"]
        if off >= 0:
            assert text[off:off + len(r["evidence"])] == r["evidence"], r


@pytest.mark.parametrize("bad", [None, 7, ["a", "b"]])
async def test_evidence_that_is_not_a_string_is_not_verbatim(bad):
    r = _rel("Kalvik Coast Guard", "Ostrava Shipping", "SUPPLIED_BY", None)
    r["evidence"] = bad
    result = await _llm([r])
    assert result[1] == []


# ── A threat actor referred back to ("the group") ──────────────────────────
# The rule NLP applies (_ACTOR_ANAPHORS): "the group" or "the actor" is the
# last threat actor the text named before it.

ACTOR_TEXT = "Volt Typhoon targeted Guam in 2023. The group relies on netsh and wmic."
ACTOR_ENTITIES = [
    {"name": "Volt Typhoon", "entity_type": "ThreatActor", "confidence": 0.95},
    {"name": "netsh", "entity_type": "Software", "confidence": 0.9},
    {"name": "Guam", "entity_type": "Location", "confidence": 0.9},
    {"name": "Kalvik Coast Guard", "entity_type": "Organization", "confidence": 0.9},
]


async def _actor(relationships: list[dict], text: str = ACTOR_TEXT):
    reply = json.dumps({"entities": ACTOR_ENTITIES, "relationships": relationships})
    with patch("intel_platform.llm.providers._get_extraction_provider",
               new=AsyncMock(return_value=_Canned(reply))):
        return await extract_entities_llm(text, "doc-actor")


async def test_a_threat_actor_referred_back_to_as_the_group_counts():
    quote = "The group relies on netsh and wmic."
    result = await _actor([_rel("Volt Typhoon", "netsh", "USES", quote)])
    edge = _edge(result[1], "Volt Typhoon", "netsh", "USES")
    assert edge is not None
    assert edge["evidence_offset"] == ACTOR_TEXT.index(quote)


async def test_the_group_is_never_an_actor_named_only_after_it():
    text = "The group relies on netsh and wmic. Volt Typhoon targeted Guam in 2023."
    result = await _actor([_rel("Volt Typhoon", "netsh", "USES", "The group relies on netsh and wmic.")], text=text)
    assert result[1] == []
    assert result.relationships_dropped_by_reason["evidence_missing_endpoint"] == 1


async def test_the_group_is_only_a_threat_actor():
    text = "The Kalvik Coast Guard ran the exercise. The group relies on netsh and wmic."
    result = await _actor([_rel("Kalvik Coast Guard", "netsh", "USES", "The group relies on netsh and wmic.")],
                          text=text)
    assert result[1] == []


# ── The prompt asks for what the parser checks ─────────────────────────────


def _prompt() -> str:
    from intel_platform.llm.skills.loader import SkillsLoader

    return SkillsLoader().get_system_prompt("entity_extraction") or ""


def test_the_prompt_asks_for_the_verbatim_sentence_and_to_omit_what_it_cannot_quote():
    prompt = _prompt()
    assert "the exact sentence (verbatim, copied from the text) that states this relationship" in prompt
    assert "omit the relationship" in prompt
    assert "Omit a relationship you cannot quote" in prompt
    assert "brief quote or paraphrase" not in prompt


def test_every_example_in_the_prompt_quotes_its_input_verbatim():
    """An example whose evidence the parser would drop teaches the model to
    write evidence that is dropped."""
    import re

    from intel_platform.services.extraction import _llm_entity, _llm_relationship, _verify_evidence

    prompt = _prompt()
    examples = re.findall(r'Input: "(.*?)"\s*\n\s*Output:\s*\n\s*```json\n(\{.*?\})\n\s*```', prompt, re.S)
    assert len(examples) >= 2
    for text, block in examples:
        data = json.loads(block)
        entities = [_llm_entity(e, "prompt") for e in data["entities"]]
        rels = [_llm_relationship(r, "prompt") for r in data["relationships"]]
        kept, dropped = _verify_evidence(entities, rels, text)
        assert len(kept) == len(rels), (dropped, text)
        for r in kept:
            assert re.fullmatch(r"[A-Z].*\.", r["evidence"]), r["evidence"]
    dating = re.search(r'Text: "(Houthi forces[^"]*)".*?"evidence": "([^"]*)"', prompt, re.S)
    assert dating and dating.group(2) == dating.group(1)


# ── A quote marked as partial; a reply that loops ──────────────────────────


def test_an_ellipsis_at_either_end_of_a_quote_is_let_go():
    """The model marks a partial quote with "..."; what it quotes must still be verbatim."""
    start, end = _locate_evidence(TEXT, "...inspected the sets at Port Selma...")
    assert TEXT[start:end] == "inspected the sets at Port Selma"
    start, end = _locate_evidence(TEXT, "…OSC is a subsidiary of Varn Holdings.")
    assert TEXT[start:end] == THIRD
    assert _locate_evidence(TEXT, "...inspected the sets at Port Calvera...") is None


async def test_a_relationship_the_reply_repeats_is_one_edge():
    """A looping reply named one edge 108 times; the graph build merges the
    repeats into one edge, so the extraction keeps one too."""
    rel = _rel("Kalvik Coast Guard", "Ostrava Shipping", "SUPPLIED_BY", FIRST)
    result = await _llm([rel, dict(rel), dict(rel)])
    assert len([r for r in result[1] if r["rel_type"] == "SUPPLIED_BY"]) == 1
    assert result.relationships_dropped_by_reason["repeated"] == 2


async def test_hybrid_keeps_a_repeated_relationship_once():
    rel = _rel("Kalvik Coast Guard", "Ostrava Shipping", "SUPPLIED_BY", FIRST)
    result = await _llm([rel, dict(rel)], mode="hybrid")
    assert len([r for r in result[1] if r["rel_type"] == "SUPPLIED_BY"]) == 1
    assert result.relationships_dropped_by_reason["repeated"] == 1


async def test_an_assertion_and_a_denial_of_one_edge_are_both_kept():
    asserted = _rel("Kalvik Coast Guard", "Ostrava Shipping", "SUPPLIED_BY", FIRST)
    denied = {**asserted, "polarity": "denies"}
    result = await _llm([asserted, denied])
    assert sorted(r["polarity"] for r in result[1] if r["rel_type"] == "SUPPLIED_BY") == ["asserts", "denies"]


# ── A verbatim fragment is read in its sentence ────────────────────────────
# The rule is that the sentence containing the evidence names both ends. The
# model sometimes quotes only part of it ("led by Senate-confirmed U.S. Space
# Force General Michael A. Guetlein"), leaving the subject out.

GOLDEN = ("Heading line\n"
          "In May 2025, DOD established the Office of Golden Dome for America, led by Senate-confirmed "
          "U.S. Space Force General Michael A. Guetlein. The office reports to the Deputy Secretary.\n"
          "Petra Lund is unrelated.")
GOLDEN_SENTENCE = ("In May 2025, DOD established the Office of Golden Dome for America, led by Senate-confirmed "
                   "U.S. Space Force General Michael A. Guetlein.")


async def _golden(quote: str):
    ents = [{"name": "Office of Golden Dome for America", "entity_type": "Organization"},
            {"name": "Michael A. Guetlein", "entity_type": "Person"},
            {"name": "Petra Lund", "entity_type": "Person"}]
    reply = json.dumps({"entities": ents, "relationships": [
        _rel("Office of Golden Dome for America", "Michael A. Guetlein", "COMMANDED_BY", quote)]})
    with patch("intel_platform.llm.providers._get_extraction_provider",
               new=AsyncMock(return_value=_Canned(reply))):
        return await extract_entities_llm(GOLDEN, "doc-golden")


async def test_a_fragment_is_kept_when_its_sentence_names_both_ends():
    result = await _golden("led by Senate-confirmed U.S. Space Force General Michael A. Guetlein")
    (edge,) = result[1]
    assert edge["evidence"] == GOLDEN_SENTENCE
    assert edge["evidence_offset"] == GOLDEN.index(GOLDEN_SENTENCE)


async def test_a_fragment_whose_sentence_does_not_name_both_ends_is_dropped():
    result = await _golden("The office reports to the Deputy Secretary.")
    assert result[1] == []
    assert result.relationships_dropped_by_reason["evidence_missing_endpoint"] == 1


async def test_a_fragment_is_never_widened_past_its_line():
    """A name on another line (a heading, a list item) is not the sentence's."""
    text = "Office of Golden Dome for America\nIt is led by General Michael A. Guetlein."
    ents = [{"name": "Office of Golden Dome for America", "entity_type": "Organization"},
            {"name": "Michael A. Guetlein", "entity_type": "Person"}]
    reply = json.dumps({"entities": ents, "relationships": [
        _rel("Office of Golden Dome for America", "Michael A. Guetlein", "COMMANDED_BY", "led by General Michael A. Guetlein")]})
    with patch("intel_platform.llm.providers._get_extraction_provider",
               new=AsyncMock(return_value=_Canned(reply))):
        result = await extract_entities_llm(text, "doc-golden-2")
    assert result[1] == []
