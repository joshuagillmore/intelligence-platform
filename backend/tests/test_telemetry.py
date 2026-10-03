"""Countable degraded outcomes (contract 1).

Each call site already logged its degraded outcome; nothing counted them, so a
quiet provider outage read as results that were merely thinner than usual.
`services.telemetry` counts them per subsystem and reason; `/health` reports
this process's totals and `GET /api/admin/degraded` the breakdown across
processes (flushing is tested in tests/test_telemetry_flush.py).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from intel_platform.api.app import app
from intel_platform.config import settings
from intel_platform.services import telemetry
from tests.ids import tp

client = TestClient(app)
headers = {"Authorization": f"Bearer {settings.api_key}"}


@pytest.fixture(autouse=True)
def _fresh_counts():
    telemetry.reset()
    yield
    telemetry.reset()


def _count(subsystem: str, reason: str | None = None) -> int:
    reasons = telemetry.snapshot().get(subsystem) or {}
    if reason is None:
        return sum(reasons.values())
    return reasons.get(reason, 0)


# ---------------------------------------------------------------------------
# The module
# ---------------------------------------------------------------------------

class TestCounts:
    def test_counts_by_subsystem_and_reason(self):
        telemetry.record_degraded("extraction", "TimeoutError")
        telemetry.record_degraded("extraction", "TimeoutError")
        telemetry.record_degraded("extraction", "unparsed", detail="doc d1")
        telemetry.record_degraded("topics", "label_failed")
        snap = telemetry.snapshot()
        assert snap["extraction"] == {"TimeoutError": 2, "unparsed": 1}
        assert snap["topics"] == {"label_failed": 1}
        assert telemetry.totals() == {"extraction": 3, "topics": 1}

    def test_snapshot_says_since_when(self):
        from datetime import datetime

        since = telemetry.snapshot()["since"]
        assert datetime.fromisoformat(since).tzinfo is not None

    def test_only_subsystems_that_degraded_appear(self):
        assert set(telemetry.snapshot()) == {"since"}
        assert telemetry.totals() == {}

    def test_detail_is_never_counted(self):
        telemetry.record_degraded("llm", "call_failed", detail="secret-host:11434 refused")
        assert "secret-host" not in str(telemetry.snapshot())

    def test_distinct_reasons_are_bounded(self):
        for i in range(telemetry.MAX_REASONS_PER_SUBSYSTEM + 25):
            telemetry.record_degraded("collection", f"reason-{i}")
        reasons = telemetry.snapshot()["collection"]
        assert len(reasons) == telemetry.MAX_REASONS_PER_SUBSYSTEM + 1
        assert reasons[telemetry.OVERFLOW_REASON] == 25
        assert sum(reasons.values()) == telemetry.MAX_REASONS_PER_SUBSYSTEM + 25

    def test_long_or_blank_reasons_are_tidied(self):
        telemetry.record_degraded("llm", "x" * 500)
        telemetry.record_degraded("llm", "   ")
        reasons = telemetry.snapshot()["llm"]
        assert all(len(r) <= telemetry.MAX_REASON_LENGTH for r in reasons)
        assert "unspecified" in reasons

    def test_a_snapshot_is_a_copy(self):
        telemetry.record_degraded("llm", "x")
        telemetry.snapshot()["llm"]["x"] = 99
        assert _count("llm", "x") == 1


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------

class TestEndpoints:
    def test_health_reports_totals(self):
        telemetry.record_degraded("embeddings", "embed_failed")
        telemetry.record_degraded("embeddings", "width_mismatch")
        body = client.get("/health").json()
        assert body["degraded"] == {"embeddings": 2}

    def test_health_reports_nothing_degraded_as_empty(self):
        assert client.get("/health").json()["degraded"] == {}

    def test_admin_gets_the_breakdown_by_process(self, monkeypatch):
        """Stored rows by process, plus the API's counts not flushed yet; the
        total is their sum. The table is faked here (tests/test_telemetry_flush.py
        reads a real one)."""
        from datetime import datetime, timedelta, timezone

        async def stored(since, db_factory):
            return {"worker": {"collection": {"source_failed": 2}}, "api": {"enrichment": {"rdap: http 503": 4}}}

        monkeypatch.setattr(telemetry, "_stored", stored)
        telemetry.record_degraded("enrichment", "rdap: http 503")
        resp = client.get("/api/admin/degraded", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["processes"] == {
            "api": {"enrichment": {"rdap: http 503": 5}},
            "worker": {"collection": {"source_failed": 2}},
        }
        assert body["total"] == {"enrichment": {"rdap: http 503": 5}, "collection": {"source_failed": 2}}
        assert body["history_available"] is True
        since = datetime.fromisoformat(body["since"])
        assert abs(datetime.now(timezone.utc) - timedelta(hours=24) - since) < timedelta(minutes=1)

    def test_unreadable_history_is_said_not_shown_as_nothing(self, monkeypatch):
        async def stored(since, db_factory):
            raise OSError("connection refused")

        monkeypatch.setattr(telemetry, "_stored", stored)
        telemetry.record_degraded("llm", "report_call_failed")
        body = client.get("/api/admin/degraded", headers=headers).json()
        assert body["history_available"] is False
        assert body["processes"] == {"api": {"llm": {"report_call_failed": 1}}, "worker": {}}
        assert body["total"] == {"llm": {"report_call_failed": 1}}

    def test_nothing_degraded_is_empty_maps(self, monkeypatch):
        async def stored(since, db_factory):
            return {}

        monkeypatch.setattr(telemetry, "_stored", stored)
        body = client.get("/api/admin/degraded", headers=headers).json()
        assert body["processes"] == {"api": {}, "worker": {}}
        assert body["total"] == {}
        assert body["history_available"] is True

    def test_an_analyst_cannot_read_it(self):
        from intel_platform.api.auth import create_access_token

        token = create_access_token("someone", "analyst")
        resp = client.get("/api/admin/degraded", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Call sites
# ---------------------------------------------------------------------------

def _embedder(vectors=None, fail=False, name="mock"):
    provider = MagicMock()
    provider.name = MagicMock(return_value=name)
    if fail:
        provider.embed = AsyncMock(side_effect=RuntimeError("down"))
    else:
        provider.embed = AsyncMock(return_value=SimpleNamespace(embeddings=vectors))
    return provider


class TestEmbeddings:
    async def test_a_failed_embedding_call_is_counted(self):
        from intel_platform.services import vector_search as vs

        stored = await vs.embed_and_store_chunks([{"content": "c"}], "d", "p", MagicMock(), provider=_embedder(fail=True))
        assert stored == 0
        assert _count("embeddings", "embed_failed") == 1

    async def test_a_width_mismatch_is_counted(self):
        from intel_platform.services import vector_search as vs

        wrong = [[0.1] * (vs._EMBEDDING_DIM + 1)]
        assert await vs.embed_and_store_chunks([{"content": "c"}], "d", "p", MagicMock(), provider=_embedder(wrong)) == 0
        assert _count("embeddings", "width_mismatch") == 1

    async def test_a_failed_query_embedding_is_counted(self):
        from intel_platform.services import vector_search as vs

        assert await vs.vector_search("q", "p", MagicMock(), provider=_embedder(fail=True)) == []
        assert _count("embeddings", "query_embed_failed") == 1

    async def test_a_wrong_width_query_vector_is_counted(self):
        from intel_platform.services import vector_search as vs

        assert await vs.vector_search("q", "p", MagicMock(), query_vector=[0.1, 0.2]) == []
        assert _count("embeddings", "width_mismatch") == 1


class TestEnrichment:
    async def test_a_provider_error_is_counted_with_the_provider(self):
        from intel_platform.enrichment.base import ProviderError
        from intel_platform.enrichment.service import EnrichmentService

        provider = SimpleNamespace(
            name="rdap", rate=1.0, capacity=1,
            lookup=AsyncMock(side_effect=ProviderError("rdap", "http 503")),
        )
        limiter = MagicMock()
        limiter.acquire = AsyncMock()
        svc = EnrichmentService(MagicMock(), limiter=limiter)
        entity = {"id": "e1", "name": "example.com", "entity_type": "Domain", "project_id": tp("t")}
        out = await svc._run(entity, [provider])
        assert out["providers"]["rdap"]["status"] == "error"
        assert _count("enrichment", "rdap: http 503") == 1

    async def test_a_raising_lookup_is_counted(self):
        from intel_platform.enrichment.service import EnrichmentService

        provider = SimpleNamespace(name="dns", rate=1.0, capacity=1, lookup=AsyncMock(side_effect=ValueError("x")))
        limiter = MagicMock()
        limiter.acquire = AsyncMock()
        svc = EnrichmentService(MagicMock(), limiter=limiter)
        await svc._run({"id": "e1", "name": "1.2.3.4", "entity_type": "IPAddress", "project_id": "p"}, [provider])
        assert _count("enrichment", "dns: lookup failed") == 1


class TestAttackMapping:
    async def test_an_unparsed_reply_is_counted(self, monkeypatch):
        from intel_platform.services.attack import mapping

        monkeypatch.setattr(mapping, "_fetch_unresolved_ttps", lambda *a, **k: [{"id": "t1", "name": "spoofed email"}])
        llm = MagicMock()
        llm.generate = AsyncMock(return_value=SimpleNamespace(content="T1566 probably."))
        monkeypatch.setattr(mapping, "_get_extraction_provider", AsyncMock(return_value=llm))
        session = MagicMock()
        count_result = MagicMock()
        count_result.scalar_one = MagicMock(return_value=5)
        session.execute = AsyncMock(side_effect=[
            count_result,
            [SimpleNamespace(technique_id="T1566", text="Phishing.", similarity=0.9)],
        ])
        result = await mapping.map_project_ttps(
            session, MagicMock(), tp("p"), embedding_provider=_embedder([[0.1] * 8]),
        )
        assert result["skip_reasons"] == {"unparsed": 1}
        assert _count("attack_mapping", "unparsed") == 1

    async def test_an_unavailable_embedding_batch_is_counted(self, monkeypatch):
        from intel_platform.services.attack import mapping

        monkeypatch.setattr(mapping, "_fetch_unresolved_ttps", lambda *a, **k: [{"id": "t1", "name": "x"}, {"id": "t2", "name": "y"}])
        result = await mapping.map_project_ttps(MagicMock(), MagicMock(), tp("p"), embedding_provider=_embedder(fail=True))
        assert result["reason"] == "embedding_unavailable"
        assert _count("attack_mapping", "embedding_unavailable") == 2


class TestTopics:
    async def test_failed_labels_are_counted(self, monkeypatch):
        from intel_platform.services import document_clustering
        from intel_platform.services.topics import TopicTreeService

        tree = {"name": "root", "entity_type": "topic", "children": [], "count": 2}

        async def _refine(node, _pairs):
            node["label_source"] = "partial"
            node["labels_refined"] = 1
            node["labels_failed"] = 2

        monkeypatch.setattr(document_clustering, "refine_labels_with_llm", _refine)
        monkeypatch.setattr("intel_platform.services.topics.cluster_documents", lambda pairs, pid: (tree, {}, {}))
        await TopicTreeService(MagicMock())._build_topic_branch([{"id": "d1", "content": "text"}], tp("p"))
        assert _count("topics", "label_failed") == 2

    async def test_a_refinement_that_raises_is_counted(self, monkeypatch):
        from intel_platform.services import document_clustering
        from intel_platform.services.topics import TopicTreeService

        tree = {"name": "root", "entity_type": "topic", "children": [], "count": 2}
        monkeypatch.setattr(document_clustering, "refine_labels_with_llm", AsyncMock(side_effect=RuntimeError("x")))
        monkeypatch.setattr("intel_platform.services.topics.cluster_documents", lambda pairs, pid: (tree, {}, {}))
        branch = await TopicTreeService(MagicMock())._build_topic_branch([{"id": "d1", "content": "text"}], tp("p"))
        assert branch["label_source"] == "keywords"
        assert _count("topics", "label_refinement_failed") == 1

    async def test_a_failed_summary_is_counted(self, monkeypatch):
        from intel_platform.llm import providers
        from intel_platform.services.topics import TopicTreeService

        svc = TopicTreeService(MagicMock())
        monkeypatch.setattr(svc, "get_topic_context", lambda eid, pid: {"document_excerpts": [], "keywords": [], "entity": {"name": "n"}})
        llm = MagicMock()
        llm.generate = AsyncMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(providers, "_get_provider", AsyncMock(return_value=llm))
        frames = [f async for f in svc.stream_summary("e-telemetry", tp("p"))]
        assert frames
        assert _count("topics", "summary_failed") == 1


class TestProducts:
    """reports.py / assess.py: every 503 is an `llm` degraded outcome."""

    @pytest.fixture
    def products(self, monkeypatch):
        from intel_platform.api.deps import get_graph_store
        from intel_platform.api.routes import llm as llm_routes
        from intel_platform.db.engine import get_db
        from intel_platform.services import graph_rag

        store = MagicMock()
        store.get_entity = MagicMock(return_value={"id": "e1", "name": "APT", "entity_type": "ThreatActor"})
        app.dependency_overrides[get_graph_store] = lambda: store

        async def _db():
            yield MagicMock()

        app.dependency_overrides[get_db] = _db

        async def _no_rag(self, query, project_id, *a, **k):
            return {"context": ""}

        monkeypatch.setattr(graph_rag.GraphRAGPipeline, "query", _no_rag)

        def use(provider):
            monkeypatch.setattr(llm_routes, "_get_provider", AsyncMock(return_value=provider))

        yield use
        app.dependency_overrides.pop(get_graph_store, None)
        app.dependency_overrides.pop(get_db, None)

    def test_a_report_with_no_provider_is_counted(self, products):
        products(None)
        resp = client.post("/api/reports/generate", json={"project_id": "p1"}, headers=headers)
        assert resp.status_code == 503
        assert _count("llm", "report_no_provider") == 1

    def test_a_failed_report_is_counted(self, products):
        llm = MagicMock()
        llm.generate = AsyncMock(side_effect=RuntimeError("x"))
        products(llm)
        assert client.post("/api/reports/generate", json={"project_id": "p1"}, headers=headers).status_code == 503
        assert _count("llm", "report_call_failed") == 1

    def test_an_empty_report_is_counted(self, products):
        llm = MagicMock()
        llm.generate = AsyncMock(return_value=SimpleNamespace(content="  ", model="m", total_tokens=1))
        products(llm)
        assert client.post("/api/reports/generate", json={"project_id": "p1"}, headers=headers).status_code == 503
        assert _count("llm", "report_empty_reply") == 1

    def test_a_failed_assessment_is_counted(self, products):
        llm = MagicMock()
        llm.generate = AsyncMock(side_effect=RuntimeError("x"))
        products(llm)
        resp = client.post("/api/assess/generate", json={"entity_id": "e1", "project_id": "p1"}, headers=headers)
        assert resp.status_code == 503
        assert _count("llm", "assessment_call_failed") == 1

    def test_an_assessment_with_no_provider_is_counted(self, products):
        products(None)
        client.post("/api/assess/generate", json={"entity_id": "e1", "project_id": "p1"}, headers=headers)
        assert _count("llm", "assessment_no_provider") == 1


class TestIngest:
    async def test_degraded_chunks_are_counted(self, monkeypatch):
        from intel_platform.api.routes import ingest
        from intel_platform.services.extraction import ExtractionResult

        async def _extract(text, doc_id, mode):
            return ExtractionResult([], [], method="nlp", degraded=True, reason="extraction failed (TimeoutError)")

        monkeypatch.setattr(ingest, "_extract", _extract)
        monkeypatch.setattr(ingest, "build_graph_from_extractions", lambda *a, **k: {"entities_created": 0, "relationships_created": 0})
        monkeypatch.setattr("intel_platform.services.vector_search.embed_and_store_chunks", AsyncMock(return_value=2))
        session = MagicMock()
        session.commit = AsyncMock()
        factory = MagicMock(return_value=MagicMock(
            __aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock(return_value=False),
        ))
        monkeypatch.setattr("intel_platform.db.engine.get_session_factory", lambda: factory)
        store = MagicMock()
        chunks = [{"content": "one"}, {"content": "two"}]
        await ingest._ingest_chunks(store, chunks, "src", tp("p"), "C3", "hybrid")
        assert _count("extraction", "extraction failed (TimeoutError)") == 2
