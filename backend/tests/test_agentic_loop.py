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
