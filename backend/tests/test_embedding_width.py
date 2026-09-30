"""G-9: embedding width is checked before it can reach the database.

Three parts of one failure:

- The factory fell back across providers of different widths (an unset
  OpenAI key quietly became Cohere, or Ollama), so vectors of one width went
  into a column sized for another.
- Nothing checked a vector's length before the insert, so the mismatch
  surfaced as a database error on flush...
- ...on the caller's session. In an agentic run that session also holds the
  run's activity rows; a failed flush left it needing a rollback, and every
  later write raised PendingRollbackError. The run's trail was lost.

It also turned up the concrete trigger: Cohere ``embed-v4`` returns 1536
dimensions unless asked otherwise, while the provider declared (and
``.env.example`` told operators to configure) 1024.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, event, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from intel_platform.llm.embeddings import (
    CohereEmbeddingProvider,
    EmbeddingConfigError,
    EmbeddingResult,
    OllamaEmbeddingProvider,
    get_embedding_provider,
)
from intel_platform.services import vector_search as vs


def _settings(**kw) -> SimpleNamespace:
    base = dict(
        embedding_provider="openai", embedding_model="", embedding_dimensions=1536,
        openai_api_key="", cohere_api_key="", ollama_base_url="http://localhost:11434",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _factory(**kw):
    with patch("intel_platform.config.get_settings", return_value=_settings(**kw)), \
         patch("openai.AsyncOpenAI"), patch("cohere.AsyncClientV2"):
        return get_embedding_provider()


# ---------------------------------------------------------------------------
# The factory
# ---------------------------------------------------------------------------

class TestTheFactoryRefusesAWidthItCannotStore:
    def test_a_provider_narrower_than_the_column_is_refused(self):
        with pytest.raises(EmbeddingConfigError) as exc:
            _factory(embedding_provider="ollama", embedding_dimensions=1536)
        msg = str(exc.value)
        assert "768" in msg and "1536" in msg and "EMBEDDING_DIMENSIONS" in msg

    def test_a_matching_width_is_accepted(self):
        p = _factory(embedding_provider="ollama", embedding_dimensions=768)
        assert isinstance(p, OllamaEmbeddingProvider)

    def test_cohere_at_its_declared_width_is_accepted(self):
        p = _factory(embedding_provider="cohere", cohere_api_key="k", embedding_dimensions=1024)
        assert isinstance(p, CohereEmbeddingProvider)


class TestNoCrossProviderFallback:
    def test_a_missing_key_is_an_error_not_a_different_provider(self):
        """openai configured, no OpenAI key, a Cohere key present: this used to
        return Cohere — 1024-wide vectors for a 1536 column."""
        with pytest.raises(EmbeddingConfigError, match="OPENAI_API_KEY"):
            _factory(embedding_provider="openai", openai_api_key="", cohere_api_key="k")

    def test_missing_cohere_key_is_an_error(self):
        with pytest.raises(EmbeddingConfigError, match="COHERE_API_KEY"):
            _factory(embedding_provider="cohere", cohere_api_key="", openai_api_key="k",
                     embedding_dimensions=1024)

    def test_an_unknown_provider_is_an_error(self):
        with pytest.raises(EmbeddingConfigError, match="EMBEDDING_PROVIDER"):
            _factory(embedding_provider="voyage")

    def test_it_is_a_runtime_error(self):
        """Callers already catch Exception around the factory."""
        assert issubclass(EmbeddingConfigError, RuntimeError)


class TestCohereReturnsTheWidthItDeclares:
    async def test_embed_v4_is_asked_for_its_declared_width(self):
        with patch("cohere.AsyncClientV2") as client_cls:
            client = client_cls.return_value
            client.embed = AsyncMock(return_value=MagicMock(
                embeddings=MagicMock(float_=[[0.0] * 1024]), meta=None,
            ))
            p = CohereEmbeddingProvider(api_key="k")  # default embed-v4.0
            await p.embed(["x"])
        assert client.embed.call_args.kwargs["output_dimension"] == p.dimension() == 1024

    async def test_v3_models_are_not_sent_a_dimension(self):
        """output_dimension is embed-v4 only; v3 models reject it."""
        with patch("cohere.AsyncClientV2") as client_cls:
            client = client_cls.return_value
            client.embed = AsyncMock(return_value=MagicMock(
                embeddings=MagicMock(float_=[[0.0] * 1024]), meta=None,
            ))
            p = CohereEmbeddingProvider(api_key="k", model="embed-english-v3.0")
            await p.embed(["x"])
        assert "output_dimension" not in client.embed.call_args.kwargs


# ---------------------------------------------------------------------------
# The insert
# ---------------------------------------------------------------------------

def _provider(width: int):
    p = MagicMock()
    p.name.return_value = f"fake:{width}"
    p.dimension.return_value = width

    async def _embed(texts, *, input_type="search_document"):
        return EmbeddingResult(embeddings=[[0.1] * width for _ in texts], model="fake")

    p.embed = AsyncMock(side_effect=_embed)
    return p


class TestTheInsertChecksWidth:
    async def test_a_wrong_width_writes_nothing(self):
        session = MagicMock()
        session.add_all = MagicMock()
        session.flush = AsyncMock()
        wrong = vs._EMBEDDING_DIM + 8
        stored = await vs.embed_and_store_chunks(
            [{"content": "a"}, {"content": "b"}], "doc", "proj", session, provider=_provider(wrong),
        )
        assert stored == 0
        session.add_all.assert_not_called()

    async def test_the_right_width_is_written(self):
        session = MagicMock()
        session.add_all = MagicMock()
        session.flush = AsyncMock()
        stored = await vs.embed_and_store_chunks(
            [{"content": "a"}], "doc", "proj", session, provider=_provider(vs._EMBEDDING_DIM),
        )
        assert stored == 1

    async def test_a_factory_refusal_is_a_zero_not_an_exception(self):
        with patch.object(vs, "get_embedding_provider", side_effect=EmbeddingConfigError("bad width")):
            stored = await vs.embed_and_store_chunks([{"content": "a"}], "doc", "proj", MagicMock())
        assert stored == 0

    async def test_search_survives_a_factory_refusal(self):
        with patch.object(vs, "get_embedding_provider", side_effect=EmbeddingConfigError("bad width")):
            assert await vs.vector_search("q", "proj", MagicMock()) == []


# ---------------------------------------------------------------------------
# The caller's session survives a failed insert
# ---------------------------------------------------------------------------

@pytest.fixture
async def sqlite_session():
    """A real AsyncSession with SAVEPOINT support (pysqlite needs the recipe
    from the SQLAlchemy SQLite docs to emit BEGIN/SAVEPOINT itself)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine.sync_engine, "connect")
    def _connect(dbapi_conn, _rec):
        dbapi_conn.isolation_level = None

    @event.listens_for(engine.sync_engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    meta = MetaData()
    activity = Table("activity", meta, Column("id", Integer, primary_key=True), Column("msg", String))
    async with engine.begin() as conn:
        await conn.run_sync(meta.create_all)
    # chunk_embeddings is deliberately NOT created: the insert fails in the
    # database, the way a width mismatch or a missing pgvector table does.
    async with AsyncSession(engine) as session:
        yield session, activity
    await engine.dispose()


async def test_a_failed_insert_does_not_poison_the_callers_session(sqlite_session):
    session, activity = sqlite_session
    await session.execute(insert(activity).values(msg="source acquired"))

    stored = await vs.embed_and_store_chunks(
        [{"content": "chunk"}], "doc", "proj", session, provider=_provider(vs._EMBEDDING_DIM),
    )
    assert stored == 0

    # The run carries on writing its trail, and the trail commits.
    await session.execute(insert(activity).values(msg="source complete"))
    await session.commit()
    count = (await session.execute(select(func.count()).select_from(activity))).scalar_one()
    assert count == 2
