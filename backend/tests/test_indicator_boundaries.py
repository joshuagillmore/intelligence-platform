"""G-8 / E-8: where an indicator starts, and whether it is one.

Three ways an indicator was minted or lost wrongly:

1. Chunk overlap was a character slice, so the next chunk began mid-token:
   "...evilcorp-servers.com" carried over as "rs.com", which the domain regex
   then minted as a Domain at 0.9.
2. The sourcing rule (a host inside a hyperlink is provenance, not content;
   an undefanged URL is a citation) was applied to regex entities only. The
   model emitting the same bbc.com citation minted it anyway.
3. The defang detector knew only [.] (.) [dot] [at] and recorded the host, so
   ``http://evil[.]com/gate.php`` lost its URL and ``evil{.}com``,
   ``evil(dot)com`` and ``ops(at)evil(dot)com`` did not count as defanged.
"""
from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, patch

from intel_platform.llm.base import LLMResponse
from intel_platform.services import extraction
from intel_platform.services.ingestion import chunk_text


# ---------------------------------------------------------------------------
# 1. Chunk overlap starts on a word boundary
# ---------------------------------------------------------------------------

def _tokens(s: str) -> set[str]:
    return set(s.split())


def _assert_no_fragments(text: str, chunks: list[str]) -> None:
    whole = _tokens(text)
    for i, chunk in enumerate(chunks):
        stray = _tokens(chunk) - whole
        assert not stray, f"chunk {i} contains token fragments {sorted(stray)[:5]}"


def test_sentence_path_overlap_does_not_cut_a_token():
    text = " ".join(
        f"Beacon {i} reached evilcorp-servers.com and staging-{i}.example.net overnight."
        for i in range(60)
    )
    chunks = chunk_text(text, chunk_size=300, overlap=77)
    assert len(chunks) > 3
    _assert_no_fragments(text, chunks)


def test_word_path_overlap_does_not_cut_a_token():
    """A paragraph with no sentence punctuation takes the word-splitting path."""
    text = " ".join(f"host{i}.evilcorp-servers.com" for i in range(200))
    chunks = chunk_text(text, chunk_size=300, overlap=77)
    assert len(chunks) > 3
    _assert_no_fragments(text, chunks)


def test_overlap_still_carries_context():
    text = " ".join(f"Sentence number {i} mentions example{i}.org today." for i in range(80))
    chunks = chunk_text(text, chunk_size=300, overlap=100)
    for prev, nxt in zip(chunks, chunks[1:]):
        first_word = nxt.split()[0]
        assert first_word in prev, "overlap was dropped entirely"


def test_no_fragment_domain_reaches_extraction():
    """The symptom: a cut through "host18.evilcorp-servers.com" left
    "8.evilcorp-servers.com" at the head of the next chunk — a Domain."""
    text = " ".join(f"host{i}.evilcorp-servers.com" for i in range(200))
    minted: set[str] = set()
    for chunk in chunk_text(text, chunk_size=300, overlap=77):
        ents, _ = extraction.extract_entities_nlp(chunk, "doc-g8")
        minted |= {e["name"] for e in ents if e["entity_type"] == "Domain"}
    legit = {f"host{i}.evilcorp-servers.com" for i in range(200)}
    assert minted <= legit, f"fragments minted as domains: {sorted(minted - legit)[:5]}"


# ---------------------------------------------------------------------------
# 3. Every defang marker refang understands counts as defanged; URLs survive
# ---------------------------------------------------------------------------

def _nlp_names(text: str, entity_type: str) -> dict[str, dict]:
    ents, _ = extraction.extract_entities_nlp(text, "doc-g8")
    return {e["name"]: e for e in ents if e["entity_type"] == entity_type}


def test_a_defanged_host_inside_a_plain_url_keeps_its_url():
    urls = _nlp_names("The loader beacons to http://evil[.]com/gate.php every hour.", "URL")
    assert "http://evil.com/gate.php" in urls


def test_a_bracketed_colon_scheme_keeps_its_url():
    urls = _nlp_names("Payload served from hxxp[:]//dropper[.]net/a.bin yesterday.", "URL")
    assert "http://dropper.net/a.bin" in urls


def test_a_defanged_url_inside_markdown_link_syntax_keeps_its_url():
    urls = _nlp_names("See [the gate](hxxps://evil[.]com/gate.php) for details.", "URL")
    assert "https://evil.com/gate.php" in urls


def test_braced_and_word_markers_count_as_defanged():
    text = "Infrastructure: evil{.}com, second(dot)net and ops(at)third(dot)org were observed."
    ents, _ = extraction.extract_entities_nlp(text, "doc-g8")
    by_name = {e["name"]: e for e in ents}
    assert by_name["evil.com"]["confidence"] == 0.95
    assert by_name["second.net"]["confidence"] == 0.95
    assert "ops@third.org" in by_name


def test_defanged_hosts_inside_links_are_still_indicators():
    """Defanging overrides the in-a-link rule: the author asserted it."""
    domains = _nlp_names("Callback: hxxps://c2(dot)evil-updates{.}com/check", "Domain")
    assert "c2.evil-updates.com" in domains


# ---------------------------------------------------------------------------
# 2. The model's Domain/URL entities obey the same sourcing rule
# ---------------------------------------------------------------------------

SOURCED_TEXT = (
    "Analysts tied the campaign to evil-updates.com, which served the loader. "
    "The payload was fetched from hxxp://evil-updates[.]com/gate.php. "
    "Reporting via https://www.bbc.com/news/world-123 and https://apps.apple.com/app/x."
)


class _Reply:
    def __init__(self, entities: list[dict]):
        self._payload = json.dumps({"entities": entities, "relationships": []})

    def name(self) -> str:
        return "fake:model"

    async def generate(self, **_kw) -> LLMResponse:
        return LLMResponse(content=self._payload, model="fake")


LLM_ENTITIES = [
    {"name": "Evil-Updates.COM", "entity_type": "Domain", "confidence": 0.9},
    {"name": "http://evil-updates.com/gate.php", "entity_type": "URL", "confidence": 0.9},
    {"name": "bbc.com", "entity_type": "Domain", "confidence": 0.8},
    {"name": "www.bbc.com", "entity_type": "Domain", "confidence": 0.8},
    {"name": "https://www.bbc.com/news/world-123", "entity_type": "URL", "confidence": 0.8},
    {"name": "apps.apple.com", "entity_type": "Domain", "confidence": 0.8},
    {"name": "c2-backup.net", "entity_type": "Domain", "confidence": 0.7},
    {"name": "BBC", "entity_type": "Organization", "confidence": 0.8},
]


async def _run(fn):
    with patch(
        "intel_platform.llm.providers._get_extraction_provider",
        new=AsyncMock(return_value=_Reply(LLM_ENTITIES)),
    ):
        return await fn(SOURCED_TEXT, "doc-g8")


def _llm_names(result) -> set[str]:
    return {e["name"] for e in result[0] if e.get("method") == "llm"}


async def test_llm_citation_hosts_and_urls_are_dropped():
    result = await _run(extraction.extract_entities_llm)
    names = _llm_names(result)
    citations = {"bbc.com", "www.bbc.com", "https://www.bbc.com/news/world-123", "apps.apple.com"}
    assert not names & citations, names & citations


async def test_llm_indicators_the_text_asserts_are_kept():
    result = await _run(extraction.extract_entities_llm)
    names = _llm_names(result)
    assert "Evil-Updates.COM" in names                  # stands alone in prose (any case)
    assert "http://evil-updates.com/gate.php" in names  # defanged in the text
    assert "BBC" in names                                # not a Domain/URL: untouched


async def test_a_host_the_text_never_contains_is_not_judged():
    """A host the text never states cannot be shown to be a citation; the
    rule is about provenance, so it is left alone rather than guessed at."""
    result = await _run(extraction.extract_entities_llm)
    assert "c2-backup.net" in _llm_names(result)


async def test_hybrid_applies_the_rule_too():
    result = await _run(extraction.extract_entities_hybrid)
    names = {e["name"].lower() for e in result[0]}
    assert "apps.apple.com" not in names
    assert "https://www.bbc.com/news/world-123" not in names
    assert "evil-updates.com" in names


def test_fixture_sanity():
    assert re.search(r"bbc\.com", SOURCED_TEXT)
