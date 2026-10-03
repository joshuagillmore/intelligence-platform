"""G-5: reading the extraction model's reply, and saying when it could not.

The LLM half of extraction split on ``` fences and ran json.loads on what was
left, so a reply that led with a sentence, or labelled the object in bold,
parsed as nothing. Worse, every failure — a 429, a timeout, one entity whose
confidence was "high", a list where an object was asked for — degraded the
whole chunk to NLP with no marker, so a run that extracted nothing with the
model was indistinguishable from one that did. Provider lookup also sat
outside the try, so a failing key lookup escaped as a 500.

Each chunk's result now says how it was extracted (``method``), whether that
was a degradation (``degraded`` + ``reason``), and how many individual items
the model got wrong (``skipped_items``). It is still a 2-tuple, so existing
``ents, rels = ...`` callers are untouched.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from intel_platform.llm.base import LLMProviderError, LLMResponse
from intel_platform.services import extraction

TEXT = "APT29 used SUNBURST against SolarWinds in December 2020."

GOOD = {
    "entities": [
        {"name": "APT29", "entity_type": "ThreatActor", "confidence": 0.95},
        {"name": "SUNBURST", "entity_type": "Malware", "confidence": 0.9},
        {"name": "SolarWinds", "entity_type": "Organization", "confidence": 0.9},
    ],
    "relationships": [
        {"source_entity": "APT29", "target_entity": "SUNBURST",
         "relationship_type": "USES", "confidence": 0.9, "evidence": TEXT},
    ],
}


class _Reply:
    def __init__(self, content: str):
        self._content = content

    def name(self) -> str:
        return "fake:model"

    async def generate(self, **_kw) -> LLMResponse:
        return LLMResponse(content=self._content, model="fake")


class _Raises:
    def __init__(self, exc: Exception):
        self._exc = exc

    def name(self) -> str:
        return "fake:model"

    async def generate(self, **_kw):
        raise self._exc


def _with(provider):
    return patch(
        "intel_platform.llm.providers._get_extraction_provider",
        new=AsyncMock(return_value=provider),
    )


async def _llm(content: str):
    with _with(_Reply(content)):
        return await extraction.extract_entities_llm(TEXT, "doc-g5")


def _names(entities: list[dict]) -> set[str]:
    return {e["name"] for e in entities}


# ---------------------------------------------------------------------------
# The reply shapes models actually produce
# ---------------------------------------------------------------------------

REPLY_SHAPES = {
    "bare": json.dumps(GOOD),
    "prose-prefixed": "Here are the entities and relationships I found:\n\n" + json.dumps(GOOD, indent=2),
    "fenced-with-trailing-prose": "```json\n" + json.dumps(GOOD) + "\n```\nLet me know if you need more.",
    "untagged-fence-after-prose": "Sure.\n```\n" + json.dumps(GOOD) + "\n```",
    "bold-label": "**Extraction result:**\n" + json.dumps(GOOD),
    "numbered-preamble": (
        "1. I read the passage.\n2. I identified three entities.\n3. Output follows:\n"
        + json.dumps(GOOD)
    ),
}


@pytest.mark.parametrize("shape", sorted(REPLY_SHAPES))
async def test_the_object_is_found_whatever_surrounds_it(shape):
    result = await _llm(REPLY_SHAPES[shape])
    ents, rels = result
    assert result.method == "llm", result.meta
    assert result.degraded is False
    assert {"APT29", "SUNBURST", "SolarWinds"} <= _names(ents)
    assert any(r["rel_type"] == "USES" for r in rels)


# ---------------------------------------------------------------------------
# Replies that are not usable must say so
# ---------------------------------------------------------------------------

async def test_a_markdown_table_instead_of_json_is_a_marked_degradation():
    table = (
        "| Entity | Type |\n|---|---|\n| APT29 | ThreatActor |\n| SUNBURST | Malware |\n"
    )
    result = await _llm(table)
    assert result.degraded is True
    assert result.method == "nlp"
    assert result.reason
    ents, _ = result
    assert ents, "the NLP fallback still has to produce entities"


async def test_a_list_where_an_object_was_asked_for_is_a_marked_degradation():
    """json_object would find the first *entity* dict inside the list; reading
    that as the reply would yield zero entities and look like success."""
    result = await _llm(json.dumps(GOOD["entities"]))
    assert result.degraded is True
    assert result.method == "nlp"
    assert "entities" in result.reason


async def test_prose_with_no_json_at_all_is_a_marked_degradation():
    result = await _llm("I could not find any entities in this text.")
    assert result.degraded is True
    assert result.reason


# ---------------------------------------------------------------------------
# One bad item costs that item, not the chunk
# ---------------------------------------------------------------------------

async def test_a_string_confidence_skips_that_entity_only():
    reply = json.loads(json.dumps(GOOD))
    reply["entities"][1]["confidence"] = "high"
    reply["relationships"].append({"source_entity": "APT29", "target_entity": "SolarWinds",
                                   "relationship_type": "TARGETS", "confidence": 0.9, "evidence": TEXT})
    result = await _llm(json.dumps(reply))
    ents, rels = result
    assert result.degraded is False and result.method == "llm"
    assert result.skipped_items == 1
    assert _names(ents) >= {"APT29", "SolarWinds"}
    assert "SUNBURST" not in {e["name"] for e in ents if e.get("method") == "llm"}
    # Relationships from the same reply survive; the one naming the skipped
    # entity no longer has a listed endpoint, and is counted as such.
    assert [(r["source_name"], r["rel_type"]) for r in rels] == [("APT29", "TARGETS")]
    assert result.relationships_dropped_by_reason["unlisted_endpoint"] == 1


async def test_a_numeric_string_confidence_is_read_as_a_number():
    reply = json.loads(json.dumps(GOOD))
    reply["entities"][0]["confidence"] = "0.6"
    result = await _llm(json.dumps(reply))
    apt = next(e for e in result[0] if e["name"] == "APT29")
    assert apt["confidence"] == pytest.approx(0.6)
    assert result.skipped_items == 0


async def test_a_bad_relationship_is_skipped_alone():
    reply = json.loads(json.dumps(GOOD))
    reply["relationships"].append("APT29 -> SolarWinds")  # a string, not an object
    reply["relationships"].append({"source_entity": "APT29", "target_entity": "SolarWinds",
                                   "relationship_type": "TARGETS", "confidence": "very",
                                   "evidence": TEXT})
    result = await _llm(json.dumps(reply))
    assert result.degraded is False
    assert result.skipped_items == 2
    assert [r["rel_type"] for r in result[1]] == ["USES"]


async def test_non_object_entities_and_attributes_do_not_sink_the_chunk():
    reply = json.loads(json.dumps(GOOD))
    reply["entities"].append("just a name")
    reply["entities"][0]["attributes"] = ["not", "a", "dict"]
    result = await _llm(json.dumps(reply))
    assert result.degraded is False
    assert result.skipped_items == 1
    apt = next(e for e in result[0] if e["name"] == "APT29")
    assert "attributes" not in apt


# ---------------------------------------------------------------------------
# Provider failures
# ---------------------------------------------------------------------------

async def test_a_provider_error_is_a_marked_degradation():
    with _with(_Raises(LLMProviderError("model not found", provider="ollama:x", status_code=404))):
        result = await extraction.extract_entities_llm(TEXT, "doc-g5")
    assert result.degraded is True and result.method == "nlp"
    assert "LLMProviderError" in result.reason
    assert result[0], "NLP fallback still extracts"


async def test_provider_lookup_failure_degrades_rather_than_raising():
    with patch(
        "intel_platform.llm.providers._get_extraction_provider",
        new=AsyncMock(side_effect=RuntimeError("key store unreachable")),
    ):
        result = await extraction.extract_entities_llm(TEXT, "doc-g5")
    assert result.degraded is True
    assert result[0]


async def test_no_provider_is_a_marked_degradation():
    with _with(None):
        result = await extraction.extract_entities_llm(TEXT, "doc-g5")
    assert result.degraded is True
    assert "provider" in result.reason


# ---------------------------------------------------------------------------
# Hybrid carries the same record
# ---------------------------------------------------------------------------

async def test_hybrid_success_is_marked_hybrid():
    with _with(_Reply(REPLY_SHAPES["prose-prefixed"])):
        result = await extraction.extract_entities_hybrid(TEXT, "doc-g5")
    assert result.method == "hybrid" and result.degraded is False
    assert "APT29" in _names(result[0])


async def test_hybrid_provider_failure_is_marked_nlp_and_degraded():
    with _with(_Raises(TimeoutError("read timed out"))):
        result = await extraction.extract_entities_hybrid(TEXT, "doc-g5")
    ents, rels = result
    assert result.method == "nlp" and result.degraded is True
    assert "TimeoutError" in result.reason
    assert ents


async def test_hybrid_lookup_failure_does_not_escape():
    with patch(
        "intel_platform.llm.providers._get_extraction_provider",
        new=AsyncMock(side_effect=RuntimeError("db down")),
    ):
        result = await extraction.extract_entities_hybrid(TEXT, "doc-g5")
    assert result.degraded is True


def test_nlp_results_carry_the_record_too():
    result = extraction.extract_entities_nlp(TEXT, "doc-g5")
    assert result.method == "nlp" and result.degraded is False
    assert set(result.meta) == {"method", "degraded", "reason", "skipped_items", "relationships_dropped_by_reason"}


def test_empty_text_still_compares_equal_to_an_empty_pair():
    assert extraction.extract_entities_nlp("   ", "d") == ([], [])


@pytest.mark.parametrize("how", ["copy", "deepcopy", "pickle"])
def test_the_record_survives_copying_and_pickling(how):
    """A tuple subclass is rebuilt from tuple(self) by copy and pickle; the
    record has to come with it, or a caller that caches or ships a result
    crashes (or silently loses the degraded marker)."""
    import copy
    import pickle

    original = extraction.ExtractionResult(
        [{"name": "a"}], [], method="nlp", degraded=True, reason="provider error (X)", skipped_items=2,
    )
    clone = {
        "copy": copy.copy,
        "deepcopy": copy.deepcopy,
        "pickle": lambda o: pickle.loads(pickle.dumps(o)),
    }[how](original)
    assert clone == original
    assert clone.meta == original.meta
