"""run_agentic_loop end to end, with every collaborator faked.

No database, no network, no model: the session is an in-memory fake shared by
every `db_factory()` call, and the resolve/acquire/evaluate phases are replaced
per test. What these tests pin is the loop's own bookkeeping — what it records
about a source, what it logs, and what it does when a phase fails.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from intel_platform.collection import agentic
from intel_platform.db.models import CollectionActivity


class FakeSession:
    def __init__(self, plan):
        self.plan = plan
        self.added: list = []
        self.commits = 0

    async def get(self, model, pk):
        return self.plan if getattr(model, "__name__", "") == "CollectionPlan" else None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass

    async def rollback(self):
        pass

    def events(self) -> list[str]:
        return [a.event for a in self.added if isinstance(a, CollectionActivity)]

    def messages(self, event: str) -> list[str]:
        return [a.message for a in self.added if isinstance(a, CollectionActivity) and a.event == event]


def _factory(session):
    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    return lambda: _Ctx()


def _source(source_type="rss_feed", config=None, name="Feed"):
    return SimpleNamespace(
        id=uuid.uuid4(), name=name, source_type=source_type, enabled=True,
        config=config if config is not None else {"feed_url": "https://feeds.example.org/rss"},
        collection_status="queued", total_records_acquired=0,
        last_success_at=None, last_failure_at=None, last_error="",
    )


def _plan(sources):
    return SimpleNamespace(
        id=uuid.uuid4(), project_id="test-agentic", pir_id=None,
        refined_pir="", pir="Who operates the Fordow site?", requirement="",
        routing_rules={"extraction_mode": "nlp"}, sources=sources,
        status="ACTIVE", updated_at=None,
    )


class FakeProvider:
    def name(self):
        return "fake"

    async def generate(self, **kwargs):
        return SimpleNamespace(content="", model="fake")


async def _provider():
    return FakeProvider()


def _acquired(records=1, accepted=1):
    return {
        "record_count": records, "accepted_count": accepted, "total_chars": 500,
        "entities_created": 2, "relationships_created": 1, "chunks_embedded": 0,
        "embed_failures": 0, "rejected_pages": [],
        "records": [{"url": "https://feeds.example.org/item", "title": "t", "content": "x" * 200}],
    }


@pytest.fixture
def wired(monkeypatch):
    """Resolution is a no-op; acquisition and evaluation are scripted per test."""
    async def no_resolve(plan, sources, db, provider, max_results=10):
        return None

    monkeypatch.setattr(agentic, "resolve_sources", no_resolve)
    state = SimpleNamespace(acquire_calls=[], evaluations=[], acquire=None)

    async def fake_acquire(source, plan, db, store, extraction_mode="nlp", provider=None, max_results=10):
        state.acquire_calls.append(SimpleNamespace(
            source_type=source.source_type, config=dict(source.config or {}), source_id=source.id,
        ))
        return await state.acquire(len(state.acquire_calls))

    async def fake_evaluate(source, plan, acquire_result, provider):
        if state.evaluations:
            return state.evaluations.pop(0)
        return {"satisfied": True, "follow_up_urls": [], "notes": "done"}

    monkeypatch.setattr(agentic, "acquire_source", fake_acquire)
    monkeypatch.setattr(agentic, "evaluate_results", fake_evaluate)
    return state


async def _run(plan, **kwargs):
    session = FakeSession(plan)
    await agentic.run_agentic_loop(plan.id, _factory(session), lambda: None, _provider, **kwargs)
    return session


class TestFollowUps:
    async def test_a_failed_follow_up_does_not_fail_an_acquired_source(self, wired):
        async def acquire(n):
            if n == 1:
                return _acquired()
            raise RuntimeError("follow-up page timed out")

        wired.acquire = acquire
        wired.evaluations = [{"satisfied": False, "follow_up_urls": ["https://news.example.org/lead"], "notes": ""}]
        source = _source()
        session = await _run(_plan([source]))

        assert source.collection_status == "succeeded", "the planned acquisition worked"
        assert "source_followup_failed" in session.events()
        assert "source_failed" not in session.events()

    async def test_rss_follow_ups_fetch_the_leads_not_the_feed(self, wired):
        async def acquire(n):
            return _acquired()

        wired.acquire = acquire
        wired.evaluations = [
            {"satisfied": False, "follow_up_urls": ["https://news.example.org/lead"], "notes": ""},
            {"satisfied": False, "follow_up_urls": ["https://news.example.org/lead-2"], "notes": ""},
        ]
        source = _source()
        await _run(_plan([source]))

        follow_ups = wired.acquire_calls[1:]
        assert follow_ups, "the leads were never fetched"
        assert all(c.source_type == "web_scrape" for c in follow_ups), "an RSS source re-read its own feed"
        assert follow_ups[0].config["urls"] == ["https://news.example.org/lead"]
        assert source.config == {"feed_url": "https://feeds.example.org/rss"}, "follow-ups overwrote the source's config"

    async def test_follow_up_urls_pass_the_url_filter(self, wired):
        async def acquire(n):
            return _acquired()

        wired.acquire = acquire
        wired.evaluations = [{
            "satisfied": False, "notes": "",
            "follow_up_urls": ["http://127.0.0.1:8000/api/projects", "ftp://files.example.org/x",
                               "https://news.example.org/lead"],
        }]
        await _run(_plan([_source()]))

        fetched = [u for c in wired.acquire_calls[1:] for u in c.config.get("urls", [])]
        assert fetched == ["https://news.example.org/lead"]

    async def test_no_valid_follow_up_means_no_follow_up_fetch(self, wired):
        async def acquire(n):
            return _acquired()

        wired.acquire = acquire
        wired.evaluations = [{"satisfied": False, "follow_up_urls": ["http://169.254.169.254/"], "notes": ""}]
        await _run(_plan([_source()]))
        assert len(wired.acquire_calls) == 1

    async def test_unsatisfied_evaluation_is_not_logged_as_satisfied(self, wired):
        async def acquire(n):
            return _acquired()

        wired.acquire = acquire
        wired.evaluations = [{"satisfied": False, "follow_up_urls": [], "notes": "thin coverage"}]
        session = await _run(_plan([_source()]))

        [message] = session.messages("source_evaluated")
        assert "not satisfied" in message.lower()

    async def test_string_false_is_not_satisfied(self, wired):
        """Models return "false" as often as false; bool("false") is True."""
        async def acquire(n):
            return _acquired()

        wired.acquire = acquire
        wired.evaluations = [{"satisfied": "false", "follow_up_urls": ["https://news.example.org/lead"], "notes": ""}]
        await _run(_plan([_source()]))
        assert len(wired.acquire_calls) == 2, "the lead was skipped as if the source were satisfied"


# ---------------------------------------------------------------------------
# C-10: a page the content gate refuses spends no budget
# ---------------------------------------------------------------------------

def _rejected_only():
    out = _acquired(records=1, accepted=0)
    out["entities_created"] = 0
    out["relationships_created"] = 0
    out["rejected_pages"] = [("https://example.org/login", "login or paywall page")]
    return out


class TestContentGateSpendsNoBudget:
    async def test_a_source_with_nothing_usable_is_not_a_success(self, wired):
        async def acquire(n):
            return _rejected_only()

        wired.acquire = acquire
        source = _source("web_scrape", {"urls": ["https://example.org/login"]}, name="Walled")
        session = await _run(_plan([source]))

        assert source.collection_status == "failed"
        assert "login or paywall" in source.last_error
        assert "source_succeeded" not in session.events()

    async def test_the_next_source_gets_the_budget(self, wired):
        async def acquire(n):
            return _rejected_only() if n == 1 else _acquired()

        wired.acquire = acquire
        walled = _source("web_scrape", {"urls": ["https://example.org/login"]}, name="Walled")
        good = _source("web_scrape", {"urls": ["https://example.org/report"]}, name="Good")
        # source_limit=2 leaves a planned budget of 1 (one held for re-tasking).
        session = await _run(_plan([walled, good]), source_limit=2)

        assert good.collection_status == "succeeded", "a refused page spent the only planned slot"
        assert "source_skipped" not in session.events()


class TestAcquireSourceCountsWhatItKept:
    @pytest.fixture
    def quiet(self, monkeypatch):
        async def no_extract(text, doc_id, mode):
            return [], []

        async def no_embed(chunks, doc_id, project_id, db):
            return 0

        monkeypatch.setattr(agentic, "_extract_entities", no_extract)
        monkeypatch.setattr("intel_platform.services.vector_search.embed_and_store_chunks", no_embed)

    def _connector(self, records):
        from intel_platform.connectors.base import AcquireResult

        class Connector:
            async def acquire(self, config):
                return AcquireResult(success=True, record_count=len(records), records=records)

        return Connector()

    async def test_a_refused_page_is_not_accepted(self, monkeypatch, quiet):
        page = {"url": "https://example.org/login", "title": "Sign in", "content": "Please sign in to continue. " * 20}
        monkeypatch.setattr(agentic, "get_connector", lambda t: self._connector([page]))
        monkeypatch.setattr(agentic, "rejection_reason", lambda url, content, title="": "login or paywall page")
        stored = []
        store = SimpleNamespace(create_entity=lambda e: stored.append(e))
        source = _source("api_feed", {"base_url": "https://example.org/api"})

        out = await agentic.acquire_source(source, _plan([source]), FakeSession(None), store)
        assert out["accepted_count"] == 0
        assert stored == []
        assert out["rejected_pages"] == [("https://example.org/login", "login or paywall page")]

    async def test_structured_api_records_become_a_document(self, monkeypatch, quiet):
        """JSON API records carry fields, not `content`. They were skipped as
        empty, so an api_feed reported "Acquired 20 docs, 0 entities"."""
        records = [
            {"name": "Atomic Energy Organization of Iran", "type": "Organization", "country": "Iran",
             "_source_url": "https://api.example.org/v1/orgs"},
            {"name": "Fordow Fuel Enrichment Plant", "type": "Facility", "country": "Iran",
             "_source_url": "https://api.example.org/v1/orgs"},
        ]
        monkeypatch.setattr(agentic, "get_connector", lambda t: self._connector(records))
        monkeypatch.setattr(agentic, "rejection_reason", lambda url, content, title="": "")
        stored = []
        store = SimpleNamespace(create_entity=lambda e: stored.append(e))
        source = _source("api_feed", {"base_url": "https://api.example.org/v1/orgs"}, name="Org registry")

        out = await agentic.acquire_source(source, _plan([source]), FakeSession(None), store)

        assert out["accepted_count"] == 1
        [doc] = stored
        assert "Fordow Fuel Enrichment Plant" in doc.content
        assert "_source_url" not in doc.content

    async def test_a_kept_page_is_accepted(self, monkeypatch, quiet):
        text = "The Fordow facility is operated by the Atomic Energy Organization of Iran. " * 5
        page = {"url": "https://example.org/report", "title": "Report", "content": text}
        monkeypatch.setattr(agentic, "get_connector", lambda t: self._connector([page]))
        monkeypatch.setattr(agentic, "rejection_reason", lambda url, content, title="": "")
        stored = []
        store = SimpleNamespace(create_entity=lambda e: stored.append(e))
        source = _source("api_feed", {"base_url": "https://example.org/api"})

        out = await agentic.acquire_source(source, _plan([source]), FakeSession(None), store)
        assert out["accepted_count"] == 1
        assert len(stored) == 1

    async def test_the_document_records_where_it_came_from(self, monkeypatch, quiet):
        """The runner path sets Document.url; the agentic path did not, so a
        collected document could not say which page it was."""
        text = "The Fordow facility is operated by the Atomic Energy Organization of Iran. " * 5
        page = {"url": "https://example.org/report", "title": "Report", "content": text}
        monkeypatch.setattr(agentic, "get_connector", lambda t: self._connector([page]))
        monkeypatch.setattr(agentic, "rejection_reason", lambda url, content, title="": "")
        stored = []
        store = SimpleNamespace(create_entity=lambda e: stored.append(e))
        source = _source("api_feed", {"base_url": "https://example.org/api"})

        await agentic.acquire_source(source, _plan([source]), FakeSession(None), store)
        assert stored[0].url == "https://example.org/report"


# ---------------------------------------------------------------------------
# Contract 14: a provider failure is recorded, never swallowed
# ---------------------------------------------------------------------------

class LLMProviderError(RuntimeError):
    """Stand-in for llm.base.LLMProviderError (WP-C): what Ollama now raises."""


REPORT = "The Fordow facility is operated by the Atomic Energy Organization of Iran. " * 5


class _DownProvider:
    def name(self):
        return "ollama:qwen2.5:14b"

    async def generate(self, **kwargs):
        raise LLMProviderError("model 'qwen2.5:14b' not found")


class TestProviderFailuresAreRecorded:
    @pytest.fixture
    def one_page(self, monkeypatch):
        from intel_platform.connectors.base import AcquireResult

        class Connector:
            async def acquire(self, config):
                page = {"url": "https://example.org/report", "title": "Report", "content": REPORT}
                return AcquireResult(success=True, record_count=1, records=[page])

        async def no_embed(chunks, doc_id, project_id, db):
            return 0

        monkeypatch.setattr(agentic, "get_connector", lambda t: Connector())
        monkeypatch.setattr(agentic, "rejection_reason", lambda url, content, title="": "")
        monkeypatch.setattr("intel_platform.services.vector_search.embed_and_store_chunks", no_embed)
        source = _source("api_feed", {"base_url": "https://example.org/api"})
        return source

    async def test_failed_extraction_is_counted_and_logged(self, monkeypatch, one_page):
        async def extraction_down(text, doc_id, mode):
            raise LLMProviderError("model not found")

        monkeypatch.setattr(agentic, "_extract_entities", extraction_down)
        session = FakeSession(None)
        store = SimpleNamespace(create_entity=lambda e: None)

        out = await agentic.acquire_source(one_page, _plan([one_page]), session, store, "hybrid")

        assert out["chunks_failed"] >= 1
        assert any("failed" in m for m in session.messages("doc_extracted"))

    async def test_a_chunk_that_fell_back_to_nlp_is_recorded(self, monkeypatch, one_page):
        class ExtractionResult(tuple):
            """Shape of services.extraction.ExtractionResult (WP-C): a 2-tuple
            that also says whether the model was bypassed."""
            degraded = True
            reason = "LLMProviderError"

        async def degraded(text, doc_id, mode):
            return ExtractionResult(([{"name": "Fordow", "entity_type": "Facility"}], []))

        monkeypatch.setattr(agentic, "_extract_entities", degraded)
        monkeypatch.setattr(agentic, "build_graph_from_extractions", lambda *a, **kw: {})
        session = FakeSession(None)
        store = SimpleNamespace(create_entity=lambda e: None)

        out = await agentic.acquire_source(one_page, _plan([one_page]), session, store, "hybrid")

        assert out["chunks_degraded"] >= 1
        assert out["degrade_reasons"] == ["LLMProviderError"]
        assert any("fell back to NLP" in m for m in session.messages("doc_extracted"))

    async def test_relevance_and_summary_outages_are_counted(self, monkeypatch, one_page):
        async def no_extract(text, doc_id, mode):
            return [], []

        monkeypatch.setattr(agentic, "_extract_entities", no_extract)
        stored = []
        store = SimpleNamespace(create_entity=lambda e: stored.append(e))

        out = await agentic.acquire_source(
            one_page, _plan([one_page]), FakeSession(None), store, provider=_DownProvider(),
        )

        assert len(stored) == 1, "the relevance screen still fails open"
        assert out["relevance_unchecked"] == 1
        assert out["summaries_failed"] == 1

    async def test_the_source_line_says_what_did_not_run(self, wired):
        async def acquire(n):
            out = _acquired()
            out.update(chunks_failed=3, relevance_unchecked=1, summaries_failed=1)
            return out

        wired.acquire = acquire
        session = await _run(_plan([_source()]))
        [line] = session.messages("source_acquired")
        assert "3 chunk(s) failed extraction" in line
        assert "relevance not checked" in line

    async def test_resolution_says_the_model_was_unavailable(self, monkeypatch):
        async def no_search(*a, **kw):
            return None

        monkeypatch.setattr(agentic, "_resolve_via_search", no_search)
        monkeypatch.setattr(agentic.asyncio, "sleep", _no_sleep)
        source = _source("web_scrape", {})
        await agentic.resolve_sources(_plan([source]), [source], FakeSession(None), _DownProvider())

        assert source.collection_status == "failed"
        assert "LLMProviderError" in source.last_error
        assert "parse" not in source.last_error.lower()

    async def test_evaluation_says_the_model_was_unavailable(self, monkeypatch):
        monkeypatch.setattr(agentic.asyncio, "sleep", _no_sleep)
        source = _source()
        out = await agentic.evaluate_results(source, _plan([source]), _acquired(), _DownProvider())
        assert out["satisfied"] is False
        assert "LLMProviderError" in out["notes"]


async def _no_sleep(*_a, **_kw):
    return None


# ---------------------------------------------------------------------------
# Contract 15: blocking work leaves the event loop; contract 17: dropped
# attributes are logged
# ---------------------------------------------------------------------------

class TestBlockingWorkLeavesTheLoop:
    """The sync Neo4j driver and spaCy ran on the API's event loop: one 40-edge
    document stalled /health and every other request while it was written."""

    async def test_store_extraction_and_graph_build_run_in_threads(self, monkeypatch, caplog):
        import logging
        import threading

        from intel_platform.connectors.base import AcquireResult

        threads: dict[str, object] = {}

        class Connector:
            async def acquire(self, config):
                page = {"url": "https://example.org/report", "title": "Report", "content": REPORT}
                return AcquireResult(success=True, record_count=1, records=[page])

        def nlp(text, doc_id):
            threads["nlp"] = threading.current_thread()
            return [{"name": "Fordow", "entity_type": "Facility"}], []

        def build(store, ents, rels, project_id, source_doc_id=None):
            threads["build"] = threading.current_thread()
            return {"entities_created": 1, "relationships_created": 0, "dropped_attributes": 2}

        async def no_embed(chunks, doc_id, project_id, db):
            return 0

        def create_entity(entity):
            threads["store"] = threading.current_thread()

        monkeypatch.setattr(agentic, "get_connector", lambda t: Connector())
        monkeypatch.setattr(agentic, "rejection_reason", lambda url, content, title="": "")
        monkeypatch.setattr("intel_platform.services.extraction.extract_entities_nlp", nlp)
        monkeypatch.setattr(agentic, "build_graph_from_extractions", build)
        monkeypatch.setattr("intel_platform.services.vector_search.embed_and_store_chunks", no_embed)
        source = _source("api_feed", {"base_url": "https://example.org/api"})

        with caplog.at_level(logging.WARNING, logger="intel_platform.collection.agentic"):
            out = await agentic.acquire_source(
                source, _plan([source]), FakeSession(None), SimpleNamespace(create_entity=create_entity), "nlp",
            )

        main = threading.main_thread()
        assert threads["store"] is not main
        assert threads["nlp"] is not main
        assert threads["build"] is not main
        assert out["entities_created"] == 1
        assert any("dropped" in r.getMessage() and "2" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# R-12: the loop honours PAUSED / ARCHIVED and never writes over them
# ---------------------------------------------------------------------------

async def _stop_when_paused_or_archived(db, plan_id):
    """Stand-in for plan_executor.plan_should_stop (WP-E)."""
    return getattr(db.plan, "status", None) in ("PAUSED", "ARCHIVED")


class TestPauseAndArchive:
    async def test_pausing_mid_run_stops_before_the_next_source(self, wired, monkeypatch):
        monkeypatch.setattr(
            "intel_platform.services.plan_executor.plan_should_stop", _stop_when_paused_or_archived, raising=False,
        )
        plan = _plan([_source(name="First"), _source(name="Second")])

        async def acquire(n):
            plan.status = "PAUSED"  # the analyst presses Pause during the first source
            return _acquired()

        wired.acquire = acquire
        retasked = []

        async def fake_passes(*a, **kw):
            retasked.append(1)

        monkeypatch.setattr("intel_platform.collection.requirement_loop.run_requirement_passes", fake_passes)
        session = await _run(plan)

        assert len(wired.acquire_calls) == 1, "the second source was collected after Pause"
        assert retasked == [], "re-tasking ran after Pause"
        assert plan.status == "PAUSED"
        assert session.events()[-1] == "plan_completed"
        assert "PAUSED" in session.messages("plan_completed")[-1]

    async def test_completion_does_not_unarchive_a_plan(self, wired):
        plan = _plan([_source()])

        async def acquire(n):
            plan.status = "ARCHIVED"
            return _acquired()

        wired.acquire = acquire
        await _run(plan)
        assert plan.status == "ARCHIVED", "completion wrote COMPLETED over ARCHIVED"

    async def test_no_provider_is_a_failure_not_a_completion(self, wired):
        async def no_provider():
            raise RuntimeError("no LLM configured")

        plan = _plan([_source()])
        session = FakeSession(plan)
        await agentic.run_agentic_loop(plan.id, _factory(session), lambda: None, no_provider)

        assert plan.status == "FAILED"
        assert "plan_failed" in session.events()


# ---------------------------------------------------------------------------
# Provider selection lives in llm/providers.py, not here
# ---------------------------------------------------------------------------

class TestProviderSelection:
    """agentic.py re-implemented provider precedence: with Ollama chosen by the
    operator and any cloud key present, it silently switched to the cloud."""

    @pytest.fixture
    def captured_provider(self, monkeypatch):
        seen = {}

        async def capture(plan, sources, db, provider, max_results=10):
            seen["provider"] = provider

        monkeypatch.setattr(agentic, "resolve_sources", capture)
        return seen

    async def test_the_operators_ollama_choice_is_used(self, monkeypatch, captured_provider):
        async def a_cloud_key(name):
            return "sk-cloud"

        monkeypatch.setattr("intel_platform.llm.providers._resolve_api_key", a_cloud_key)
        ollama = SimpleNamespace(name=lambda: "ollama:qwen2.5:14b")

        async def get_provider():
            return ollama

        plan = _plan([])
        await agentic.run_agentic_loop(plan.id, _factory(FakeSession(plan)), lambda: None, get_provider)
        assert captured_provider["provider"] is ollama

    async def test_default_is_the_collection_provider(self, monkeypatch, captured_provider):
        chosen = FakeProvider()

        async def collection_provider():
            return chosen

        monkeypatch.setattr("intel_platform.llm.providers._get_collection_provider", collection_provider)
        plan = _plan([])
        await agentic.run_agentic_loop(plan.id, _factory(FakeSession(plan)), lambda: None)
        assert captured_provider["provider"] is chosen

    def test_no_private_provider_chain_remains(self):
        assert not hasattr(agentic, "_get_agentic_provider")


# ---------------------------------------------------------------------------
# R-3: a crashed run says it failed
# ---------------------------------------------------------------------------

class TestACrashIsRecorded:
    """With no top-level handler a crash left the plan "running" for 600 s,
    then "stalled", never "failed", and the exception went nowhere."""

    @pytest.fixture
    def resolve_raises(self, monkeypatch):
        async def boom(plan, sources, db, provider, max_results=10):
            raise RuntimeError("secret internal detail: connection string postgres://u:p@db")

        monkeypatch.setattr(agentic, "resolve_sources", boom)

    async def test_a_crash_writes_plan_failed_and_does_not_escape(self, resolve_raises):
        plan = _plan([_source()])
        session = await _run(plan)  # must not raise

        assert "plan_failed" in session.events()
        assert plan.status == "FAILED"
        assert "plan_completed" not in session.events()

    async def test_the_failure_message_does_not_carry_exception_text(self, resolve_raises):
        session = await _run(_plan([_source()]))
        [message] = session.messages("plan_failed")
        assert "postgres://" not in message
        assert "RuntimeError" in message

    async def test_a_paused_plan_stays_paused(self, resolve_raises):
        plan = _plan([_source()])
        plan.status = "PAUSED"
        session = await _run(plan)
        assert "plan_failed" in session.events()
        assert plan.status == "PAUSED", "a crash must not overwrite the analyst's pause"

    async def test_cancellation_is_recorded_and_still_propagates(self, monkeypatch):
        import asyncio

        async def cancelled(plan, sources, db, provider, max_results=10):
            raise asyncio.CancelledError()

        monkeypatch.setattr(agentic, "resolve_sources", cancelled)
        plan = _plan([_source()])
        session = FakeSession(plan)
        with pytest.raises(asyncio.CancelledError):
            await agentic.run_agentic_loop(plan.id, _factory(session), lambda: None, _provider)
        assert "plan_failed" in session.events()
