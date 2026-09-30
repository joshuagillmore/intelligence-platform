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


def _maps_to_llm(driver) -> list[dict]:
    with driver.session() as session:
        return session.run(
            """
            MATCH (:TTP {project_id: $pid})-[r:MAPS_TO {method: 'llm'}]->(tech:AttackTechnique)
            RETURN tech.attack_id AS id, r.confidence AS confidence, r.rationale AS rationale
            """,
            pid=PROJECT_ID,
        ).data()


async def test_confirmed_match_creates_llm_mapsto(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(name="Users received a spoofed email with a malicious attachment", project_id=PROJECT_ID))

    session = _mock_session([
        {"id": "T9995", "text": "Synthetic Phishing. Adversaries send phishing messages.", "sim": 0.91},
        {"id": "T9996", "text": "Synthetic Scripting. Abuse of interpreters.", "sim": 0.42},
    ])
    reply = '{"matches": [{"technique_id": "T9995", "confidence": 0.82, "rationale": "spoofed email with attachment"}]}'

    with _patch_llm(reply):
        result = await mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
        )

    assert result == {"mapped": 1, "skipped": 0, "skip_reasons": {}}
    edges = _maps_to_llm(driver)
    assert len(edges) == 1
    assert edges[0]["id"] == "T9995"
    assert edges[0]["confidence"] == 0.82
    assert edges[0]["rationale"] == "spoofed email with attachment"


async def test_below_threshold_is_skipped_not_written(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(name="Some vague activity was observed", project_id=PROJECT_ID))

    session = _mock_session([
        {"id": "T9995", "text": "Synthetic Phishing. Adversaries send phishing messages.", "sim": 0.55},
    ])
    reply = '{"matches": [{"technique_id": "T9995", "confidence": 0.2, "rationale": "weak"}]}'

    with _patch_llm(reply):
        result = await mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
        )

    assert result == {"mapped": 0, "skipped": 1, "skip_reasons": {"rejected": 1}}
    assert _maps_to_llm(driver) == []


async def test_degrades_when_embedding_provider_unreachable(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(name="Anything at all", project_id=PROJECT_ID))

    session = _mock_session([])  # never reached

    # No LLM patch needed — batch should short-circuit before any LLM call.
    result = await mapping.map_project_ttps(
        session, driver, PROJECT_ID, embedding_provider=_embed_provider(fail=True),
    )

    assert result["mapped"] == 0 and result["skipped"] == 1
    assert result["skip_reasons"] == {"embedding_unavailable": 1}
    assert result["reason"] == "embedding_unavailable"
    assert _maps_to_llm(driver) == []
    session.execute.assert_not_called()


async def test_degrades_when_pgvector_retrieve_errors(techniques, graph_store):
    """A real pgvector error (e.g. embedding dim != the Vector column) degrades to
    skips instead of 500-ing the endpoint."""
    driver = techniques
    graph_store.create_entity(TTP(name="Users received a spoofed email", project_id=PROJECT_ID))

    session = MagicMock()
    session.execute = AsyncMock(side_effect=RuntimeError("vector dimension mismatch"))

    with _patch_llm('{"matches": []}'):  # provider resolves; retrieve fails before it's used
        result = await mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
        )

    assert result["mapped"] == 0 and result["skipped"] == 1
    assert result["skip_reasons"] == {"candidate_retrieval_failed": 1}
    assert result["reason"] == "candidate_retrieval_failed"
    assert _maps_to_llm(driver) == []


async def test_reports_when_catalogue_is_not_embedded(techniques, graph_store):
    """An unembedded catalogue must not look like "the model rejected everything".

    Found live: 695 techniques loaded in Neo4j, zero rows in
    attack_technique_embeddings, and /attack/map returned {"mapped": 0,
    "skipped": 19} — the same shape as a genuine no-match, so the missing
    prerequisite was invisible.
    """
    driver = techniques
    graph_store.create_entity(TTP(name="Users received a spoofed email", project_id=PROJECT_ID))

    session = MagicMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar_one=lambda: 0))

    with _patch_llm('{"matches": []}'):
        result = await mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
        )

    assert result["mapped"] == 0
    assert result["skipped"] == 1
    assert result["reason"] == "technique_catalogue_not_embedded"
    assert "attack/embed" in result["detail"]
    assert _maps_to_llm(driver) == []


# --- E-6: the reply is read however the model presents it -------------------

_MATCH = '{"matches": [{"technique_id": "T9995", "confidence": 0.82, "rationale": "spoofed email"}]}'


@pytest.mark.parametrize("reply", [
    pytest.param(_MATCH, id="bare"),
    pytest.param(f"```json\n{_MATCH}\n```", id="fenced"),
    pytest.param(f"Here is my assessment of the candidates:\n\n{_MATCH}", id="prose-prefixed"),
    pytest.param(f"**Result:** {_MATCH}", id="bolded"),
    pytest.param(f"1. {_MATCH}", id="numbered"),
    pytest.param(f"| verdict | {_MATCH} |", id="table-row"),
    pytest.param(
        '{\n  "matches": [\n    {\n      "technique_id": "T9995",\n      "confidence": 0.82,\n'
        '      "rationale": "spoofed email"\n    }\n  ]\n}',
        id="pretty-printed",
    ),
])
def test_parse_matches_reads_every_presentation(reply):
    assert mapping._parse_matches(reply) == [
        {"technique_id": "T9995", "confidence": 0.82, "rationale": "spoofed email"},
    ]


@pytest.mark.parametrize("reply", [
    pytest.param("T9995 looks like the best fit here, fairly confident.", id="all-prose"),
    pytest.param("", id="empty"),
    pytest.param('{"verdict": "T9995"}', id="object-without-matches"),
    pytest.param('{"matches": "T9995"}', id="matches-not-a-list"),
])
def test_parse_matches_reports_an_unreadable_reply_as_none(reply):
    # None is "we could not read the reply" — never [] ("the model rejected
    # every candidate"), which is a different finding.
    assert mapping._parse_matches(reply) is None


def test_parse_matches_empty_list_is_a_rejection():
    assert mapping._parse_matches('{"matches": []}') == []


async def test_prose_prefixed_reply_is_mapped(techniques, graph_store):
    # Verified live: a lead-in sentence made the old fence-split parser return
    # [], and the TTP was counted "skipped" as if the model had rejected it.
    driver = techniques
    graph_store.create_entity(TTP(name="Users received a spoofed email", project_id=PROJECT_ID))
    session = _mock_session([{"id": "T9995", "text": "Synthetic Phishing.", "sim": 0.9}])

    with _patch_llm(f"Here is my assessment of the candidates:\n\n{_MATCH}"):
        result = await mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
        )

    assert result["mapped"] == 1
    assert [e["id"] for e in _maps_to_llm(driver)] == ["T9995"]


async def test_unparsed_reply_is_its_own_reason(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(name="Users received a spoofed email", project_id=PROJECT_ID))
    session = _mock_session([{"id": "T9995", "text": "Synthetic Phishing.", "sim": 0.9}])

    with _patch_llm("T9995 looks like the best fit here, fairly confident."):
        result = await mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
        )

    assert result["mapped"] == 0
    assert result["skipped"] == 1
    assert result["skip_reasons"] == {"unparsed": 1}
    assert _maps_to_llm(driver) == []


async def test_rejection_is_counted_as_rejected(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(name="Users received a spoofed email", project_id=PROJECT_ID))
    session = _mock_session([{"id": "T9995", "text": "Synthetic Phishing.", "sim": 0.9}])

    with _patch_llm('{"matches": []}'):
        result = await mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
        )

    assert result["skip_reasons"] == {"rejected": 1}


# --- E-7: selection, ordering and stale edges --------------------------------

def _link(driver, ttp_id: str, tech_id: str, method: str) -> None:
    with driver.session() as session:
        session.run(
            """
            MATCH (t:TTP {id: $ttp_id}), (tech:AttackTechnique {attack_id: $tech_id})
            MERGE (t)-[r:MAPS_TO]->(tech)
            SET r.method = $method, r.confidence = 0.9
            """,
            ttp_id=ttp_id, tech_id=tech_id, method=method,
        )


def _maps_to(driver, ttp_id: str) -> dict[str, str]:
    with driver.session() as session:
        rows = session.run(
            "MATCH (:TTP {id: $id})-[r:MAPS_TO]->(tech:AttackTechnique) RETURN tech.attack_id AS id, r.method AS m",
            id=ttp_id,
        ).data()
    return {r["id"]: r["m"] for r in rows}


async def test_llm_mapped_ttp_is_not_reselected(techniques, graph_store):
    # Every run used to re-send TTPs the LLM had already mapped: the query
    # excluded only method:'tcode' edges.
    driver = techniques
    graph_store.create_entity(TTP(id="test-ttp-mapped", name="Spoofed email", project_id=PROJECT_ID))
    _link(driver, "test-ttp-mapped", "T9995", "llm")

    assert mapping._fetch_unresolved_ttps(driver, PROJECT_ID, 10) == []

    provider = MagicMock()
    provider.generate = AsyncMock()
    with patch("intel_platform.services.attack.mapping._get_extraction_provider",
               new=AsyncMock(return_value=provider)):
        result = await mapping.map_project_ttps(
            _mock_session([]), driver, PROJECT_ID, embedding_provider=_embed_provider(),
        )
    assert result["mapped"] == 0 and result["skipped"] == 0
    provider.generate.assert_not_called()


def test_remap_reselects_llm_mapped_but_never_tcode(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(id="test-ttp-llm", name="Spoofed email", project_id=PROJECT_ID))
    graph_store.create_entity(TTP(id="test-ttp-tcode", name="T9996 scripting", project_id=PROJECT_ID))
    _link(driver, "test-ttp-llm", "T9995", "llm")
    _link(driver, "test-ttp-tcode", "T9996", "tcode")

    ids = [t["id"] for t in mapping._fetch_unresolved_ttps(driver, PROJECT_ID, 10, remap=True)]
    assert ids == ["test-ttp-llm"]


def test_selection_is_ordered_by_id_so_the_cap_is_deterministic(techniques, graph_store):
    driver = techniques
    for suffix in ("c", "a", "d", "b"):
        graph_store.create_entity(TTP(id=f"test-ttp-{suffix}", name=f"activity {suffix}", project_id=PROJECT_ID))

    ids = [t["id"] for t in mapping._fetch_unresolved_ttps(driver, PROJECT_ID, 2)]
    assert ids == ["test-ttp-a", "test-ttp-b"]


async def test_remap_removes_a_stale_llm_edge_the_model_no_longer_confirms(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(id="test-ttp-stale", name="Spoofed email", project_id=PROJECT_ID))
    _link(driver, "test-ttp-stale", "T9996", "llm")  # an earlier, wrong mapping
    session = _mock_session([
        {"id": "T9995", "text": "Synthetic Phishing.", "sim": 0.9},
        {"id": "T9996", "text": "Synthetic Scripting.", "sim": 0.4},
    ])

    with _patch_llm(_MATCH):  # confirms T9995 only
        result = await mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(), remap=True,
        )

    assert result["mapped"] == 1
    assert result["stale_removed"] == 1
    assert _maps_to(driver, "test-ttp-stale") == {"T9995": "llm"}


async def test_remap_rejection_removes_the_llm_edge(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(id="test-ttp-rej", name="Spoofed email", project_id=PROJECT_ID))
    _link(driver, "test-ttp-rej", "T9995", "llm")
    session = _mock_session([{"id": "T9995", "text": "Synthetic Phishing.", "sim": 0.9}])

    with _patch_llm('{"matches": []}'):
        result = await mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(), remap=True,
        )

    assert result["skip_reasons"] == {"rejected": 1}
    assert _maps_to(driver, "test-ttp-rej") == {}


async def test_remap_keeps_the_edge_when_the_reply_is_unreadable(techniques, graph_store):
    # An unreadable reply is not a disagreement; it must not delete anything.
    driver = techniques
    graph_store.create_entity(TTP(id="test-ttp-keep", name="Spoofed email", project_id=PROJECT_ID))
    _link(driver, "test-ttp-keep", "T9995", "llm")
    session = _mock_session([{"id": "T9995", "text": "Synthetic Phishing.", "sim": 0.9}])

    with _patch_llm("I think it is probably phishing."):
        result = await mapping.map_project_ttps(
            session, driver, PROJECT_ID, embedding_provider=_embed_provider(), remap=True,
        )

    assert result["skip_reasons"] == {"unparsed": 1}
    assert result["stale_removed"] == 0
    assert _maps_to(driver, "test-ttp-keep") == {"T9995": "llm"}


# --- contract 14: a provider failure is an error, not an empty mapping ------

async def test_llm_failure_surfaces_as_an_error(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(name="Users received a spoofed email", project_id=PROJECT_ID))
    session = _mock_session([{"id": "T9995", "text": "Synthetic Phishing.", "sim": 0.9}])

    provider = MagicMock()
    # Stands in for llm.base.LLMProviderError (a RuntimeError), e.g. Ollama's
    # 404 "model not found", which used to come back as an empty reply.
    provider.generate = AsyncMock(side_effect=RuntimeError("model 'qwen2.5:14b' not found"))
    with patch("intel_platform.services.attack.mapping._get_extraction_provider",
               new=AsyncMock(return_value=provider)):
        with pytest.raises(mapping.LLMUnavailable):
            await mapping.map_project_ttps(
                session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
            )
    assert _maps_to_llm(driver) == []


async def test_no_llm_provider_surfaces_as_an_error(techniques, graph_store):
    driver = techniques
    graph_store.create_entity(TTP(name="Users received a spoofed email", project_id=PROJECT_ID))
    session = _mock_session([{"id": "T9995", "text": "Synthetic Phishing.", "sim": 0.9}])

    with patch("intel_platform.services.attack.mapping._get_extraction_provider",
               new=AsyncMock(side_effect=RuntimeError("no provider configured"))):
        with pytest.raises(mapping.LLMUnavailable):
            await mapping.map_project_ttps(
                session, driver, PROJECT_ID, embedding_provider=_embed_provider(),
            )
