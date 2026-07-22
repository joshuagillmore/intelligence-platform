"""Tests for RAG text→technique mapping (``services.attack.mapping``).

The embedding provider, the LLM confirmation call, and the pgvector candidate
retrieval (Postgres session) are all mocked — only the graph writes hit the live
local Neo4j so we can assert the ``MAPS_TO {method:"llm"}`` edge is (or is not)
created. No real embedding/LLM API calls are made.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from intel_platform.llm.embeddings import EmbeddingResult
from intel_platform.models.entities import TTP
from intel_platform.services.attack import mapping

PROJECT_ID = "test-attack-mapping"


@pytest.fixture
def techniques(neo4j_driver):
    """Two global technique nodes for the MERGE to bind to; cleaned up after.

    Fictitious ids (T999x) so the teardown can't prune real ATT&CK reference nodes
    that may already be loaded in the shared local Neo4j.
    """
    with neo4j_driver.session() as session:
        session.run(
            """
            UNWIND $rows AS r
            MERGE (t:AttackTechnique {attack_id: r.id})
            SET t.name = r.name, t.description = r.desc, t.is_subtechnique = false
            """,
            rows=[
                {"id": "T9995", "name": "Synthetic Phishing", "desc": "Adversaries send phishing messages."},
                {"id": "T9996", "name": "Synthetic Scripting", "desc": "Abuse of interpreters."},
            ],
        )
    yield neo4j_driver
    with neo4j_driver.session() as session:
        session.run("MATCH (t:AttackTechnique) WHERE t.attack_id IN ['T9995','T9996'] DETACH DELETE t")


def _embed_provider(fail: bool = False) -> MagicMock:
    provider = MagicMock()
    if fail:
        provider.embed = AsyncMock(side_effect=RuntimeError("embedding backend down"))
    else:
        async def _embed(texts, *, input_type="search_document"):
            return EmbeddingResult(embeddings=[[0.1] * 8 for _ in texts], model="mock")
        provider.embed = AsyncMock(side_effect=_embed)
    return provider


def _mock_session(candidates: list[dict]) -> MagicMock:
    """AsyncSession stub whose execute() yields the given candidate rows."""
    rows = [SimpleNamespace(technique_id=c["id"], text=c["text"], similarity=c["sim"]) for c in candidates]
    session = MagicMock()
    session.execute = AsyncMock(return_value=rows)
    return session


def _patch_llm(json_reply: str):
    """Patch the extraction provider so generate() returns a canned JSON reply."""
    provider = MagicMock()
    provider.generate = AsyncMock(return_value=SimpleNamespace(content=json_reply))
    return patch(
        "intel_platform.services.attack.mapping._get_extraction_provider",
        new=AsyncMock(return_value=provider),
    )


def _run(coro):
    # Mirror the suite's existing sync-wrapper pattern (see test_vector_search.py).
    # NOT asyncio.run(): that closes the shared default loop and breaks sibling
    # tests that reuse get_event_loop().run_until_complete().
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def _maps_to_llm(driver) -> list[dict]:
    with driver.session() as session:
        return session.run(
            """
            MATCH (:TTP {project_id: $pid})-[r:MAPS_TO {method: 'llm'}]->(tech:AttackTechnique)
            RETURN tech.attack_id AS id, r.confidence AS confidence, r.rationale AS rationale
            """,
            pid=PROJECT_ID,
        ).data()


def test_confirmed_match_creates_llm_mapsto(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(name="Users received a spoofed email with a malicious attachment", project_id=PROJECT_ID))

    session = _mock_session([
        {"id": "T9995", "text": "Synthetic Phishing. Adversaries send phishing messages.", "sim": 0.91},
        {"id": "T9996", "text": "Synthetic Scripting. Abuse of interpreters.", "sim": 0.42},
    ])
    reply = '{"matches": [{"technique_id": "T9995", "confidence": 0.82, "rationale": "spoofed email with attachment"}]}'

    with _patch_llm(reply):
        result = _run(mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
        ))

    assert result == {"mapped": 1, "skipped": 0}
    edges = _maps_to_llm(driver)
    assert len(edges) == 1
    assert edges[0]["id"] == "T9995"
    assert edges[0]["confidence"] == 0.82
    assert edges[0]["rationale"] == "spoofed email with attachment"


def test_below_threshold_is_skipped_not_written(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(name="Some vague activity was observed", project_id=PROJECT_ID))

    session = _mock_session([
        {"id": "T9995", "text": "Synthetic Phishing. Adversaries send phishing messages.", "sim": 0.55},
    ])
    reply = '{"matches": [{"technique_id": "T9995", "confidence": 0.2, "rationale": "weak"}]}'

    with _patch_llm(reply):
        result = _run(mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
        ))

    assert result == {"mapped": 0, "skipped": 1}
    assert _maps_to_llm(driver) == []


def test_degrades_when_embedding_provider_unreachable(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(name="Anything at all", project_id=PROJECT_ID))

    session = _mock_session([])  # never reached

    # No LLM patch needed — batch should short-circuit before any LLM call.
    result = _run(mapping.map_project_ttps(
        session, driver, PROJECT_ID, embedding_provider=_embed_provider(fail=True),
    ))

    assert result == {"mapped": 0, "skipped": 1}
    assert _maps_to_llm(driver) == []
    session.execute.assert_not_called()


def test_degrades_when_pgvector_retrieve_errors(techniques, graph_store):
    """A real pgvector error (e.g. embedding dim != the Vector column) degrades to
    skips instead of 500-ing the endpoint."""
    driver = techniques
    graph_store.create_entity(TTP(name="Users received a spoofed email", project_id=PROJECT_ID))

    session = MagicMock()
    session.execute = AsyncMock(side_effect=RuntimeError("vector dimension mismatch"))

    with _patch_llm('{"matches": []}'):  # provider resolves; retrieve fails before it's used
        result = _run(mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
        ))

    assert result == {"mapped": 0, "skipped": 1}
    assert _maps_to_llm(driver) == []
