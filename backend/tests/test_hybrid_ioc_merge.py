"""G-1: hybrid extraction must not fuzzy-merge indicators.

Adjacent IPs, CVEs and ATT&CK sub-techniques score above the 0.92
Jaro-Winkler threshold the hybrid merge uses for semantic names:
185.220.101.42 vs .43 is 0.971, CVE-2024-3400 vs 3401 is 0.969, T1566.001 vs
.002 is 0.956. The merge compared regex IOCs fuzzily, and appended every kept
NLP name to the comparison list, so each sibling after the first matched the
one before it and was silently dropped. graph_builder already refuses fuzzy
matching for these types; the hybrid merge now does too.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from intel_platform.llm.base import LLMResponse
from intel_platform.services import extraction

TEXT = (
    "Operators staged infrastructure on 185.220.101.42, 185.220.101.43 and "
    "185.220.101.44 before the intrusion. The actor exploited CVE-2024-3400 and "
    "CVE-2024-3401 in PAN-OS. Initial access used T1566.001 and T1566.002 "
    "spearphishing. Sergei Lavrov commented on the report."
)

IOCS = [
    "185.220.101.42", "185.220.101.43", "185.220.101.44",
    "CVE-2024-3400", "CVE-2024-3401",
    "T1566.001", "T1566.002",
]


class _Provider:
    def __init__(self, entities: list[dict]):
        self._payload = json.dumps({"entities": entities, "relationships": []})

    def name(self) -> str:
        return "fake:model"

    async def generate(self, **_kw) -> LLMResponse:
        return LLMResponse(content=self._payload, model="fake")


async def _hybrid(llm_entities: list[dict]):
    with patch(
        "intel_platform.llm.providers._get_extraction_provider",
        new=AsyncMock(return_value=_Provider(llm_entities)),
    ):
        return await extraction.extract_entities_hybrid(TEXT, "doc-g1")


def _names(entities: list[dict]) -> list[str]:
    return [e["name"] for e in entities]


async def test_every_indicator_survives_when_the_llm_returns_none_of_them():
    ents, _ = await _hybrid([
        {"name": "PAN-OS", "entity_type": "Software", "confidence": 0.9},
    ])
    names = _names(ents)
    for ioc in IOCS:
        assert names.count(ioc) == 1, f"{ioc} was merged away or duplicated: {sorted(names)}"


async def test_siblings_survive_next_to_the_one_the_llm_did_return():
    """The LLM names one of each pair; the regex sibling is a different
    indicator, not a spelling variant of it."""
    ents, _ = await _hybrid([
        {"name": "185.220.101.42", "entity_type": "IPAddress", "confidence": 0.9},
        {"name": "CVE-2024-3400", "entity_type": "Vulnerability", "confidence": 0.9},
        {"name": "T1566.001", "entity_type": "TTP", "confidence": 0.9},
    ])
    names = _names(ents)
    for ioc in IOCS:
        assert names.count(ioc) == 1, f"{ioc}: {sorted(names)}"


async def test_an_exact_indicator_match_still_merges():
    """Exact (case/whitespace-normalised) matches are the same indicator and
    must still merge, keeping the higher confidence."""
    ents, _ = await _hybrid([
        {"name": " cve-2024-3400 ", "entity_type": "Vulnerability", "confidence": 0.5},
    ])
    matches = [e for e in ents if e["name"].strip().upper() == "CVE-2024-3400"]
    assert len(matches) == 1, _names(ents)
    assert matches[0]["confidence"] >= 0.95  # the regex confidence was merged in


async def test_semantic_names_still_fuzzy_merge():
    """The fix is scoped to indicators: a transliteration variant of a person
    is still one person."""
    ents, _ = await _hybrid([
        {"name": "Sergey Lavrov", "entity_type": "Person", "confidence": 0.9},
    ])
    lavrovs = [n for n in _names(ents) if "lavrov" in n.lower()]
    assert lavrovs == ["Sergey Lavrov"], lavrovs
