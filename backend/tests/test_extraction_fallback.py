"""Guard: LLM/hybrid extraction must degrade to NLP on ANY provider failure.

hybrid is the default extraction_mode, so a provider that is unreachable,
rate-limited, or erroring must never propagate and 500 the ingest path.
"""
from unittest.mock import AsyncMock, patch

from intel_platform.services import extraction

TEXT = "APT-29 targeted the German Federal Foreign Office in Berlin."


class _BoomProvider:
    async def generate(self, **kwargs):
        raise ConnectionError("ollama unreachable / provider 5xx")


async def test_llm_extraction_falls_back_to_nlp_on_provider_error():
    with patch(
        "intel_platform.llm.providers._get_extraction_provider",
        new=AsyncMock(return_value=_BoomProvider()),
    ):
        ents, rels = await extraction.extract_entities_llm(TEXT, "doc-fallback")

    # Did not raise, and returned NLP-derived results (never LLM).
    assert isinstance(ents, list) and isinstance(rels, list)
    assert ents, "expected NLP fallback to produce entities"
    assert all(e.get("method") in ("nlp", "regex") for e in ents)


async def test_hybrid_extraction_survives_provider_error():
    with patch(
        "intel_platform.llm.providers._get_extraction_provider",
        new=AsyncMock(return_value=_BoomProvider()),
    ):
        ents, rels = await extraction.extract_entities_hybrid(TEXT, "doc-fallback-hybrid")

    # Hybrid must not raise when the LLM half fails; it still returns NLP output.
    assert isinstance(ents, list) and isinstance(rels, list)
    assert ents
