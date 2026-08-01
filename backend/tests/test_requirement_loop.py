"""Collect until the requirement is answered, or say plainly why it stopped.

The source loop works a fixed list of planned sources and stops whatever state
the requirement is in. A live run ended "3 element(s) still unanswered and
collection budget remains — continue collection" and nothing continued it,
because the assessment was a report with no actuator.

These tests care about the three stopping conditions staying distinguishable:
answered, retired after trying, and stopped short by budget. An exhausted run
reported as a satisfied one is the failure mode that matters.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from intel_platform.collection import requirement_loop as rl
from intel_platform.db.models import PirRequirement


class _FakeDB:
    """Enough AsyncSession surface for the loop, backed by a plain list."""

    def __init__(self, rows, plan=None, pir=None):
        self.rows = rows
        self.plan = plan
        self.pir = pir
        self.added = []
        self.deleted = []
        self.commits = 0

    async def get(self, model, pk):
        name = getattr(model, "__name__", "")
        if name == "CollectionPlan":
            return self.plan
        if name == "Pir":
            return self.pir
        return None

    async def execute(self, stmt):
        sql = str(stmt)
        rows = self.rows
        # The pass loop filters on status in its WHERE clause; sync and the
        # closing read do not. Match the predicate, not the column list — every
        # SELECT names `status` among its columns.
        if "status = " in sql:
            rows = [r for r in rows if r.status == "pending"]
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: list(rows)))

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, PirRequirement):
            self.rows.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)
        if obj in self.rows:
            self.rows.remove(obj)

    async def commit(self):
        self.commits += 1

    async def flush(self):
        pass


def _factory(db):
    class _Ctx:
        async def __aenter__(self_inner):
            return db

        async def __aexit__(self_inner, *exc):
            return False

    return lambda: _Ctx()


def _requirement(ordinal, text, status="pending", attempts=0):
    row = PirRequirement(pir_id="pir-1", project_id="p1", ordinal=ordinal, text=text)
    row.status = status
    row.attempts = attempts
    row.next_queries = []
    row.assessment_missing = ""
    row.assessment_confidence = ""
    return row


def _plan(pir_id="pir-1"):
    return SimpleNamespace(id="plan-1", pir_id=pir_id, sources=[])


def _pir(eeis):
    return SimpleNamespace(id="pir-1", project_id="p1", eeis=list(eeis))


@pytest.fixture
def no_collection(monkeypatch):
    """Re-tasked collection is stubbed out; these tests are about control flow."""
    async def _none(*a, **kw):
        return 0

    monkeypatch.setattr(rl, "_collect_for_element", _none)


def _assessor(verdicts):
    """verdicts: list of (satisfied, queries) consumed in order."""
    seq = list(verdicts)

    async def fake(text, project_id, db, provider, tried_queries=None, store=None):
        satisfied, queries = seq.pop(0) if seq else (False, ["more"])
        return SimpleNamespace(
            satisfied=satisfied, confidence="medium",
            missing="" if satisfied else "still missing",
            next_queries=queries, assessed=True,
        )

    return fake


class TestStoppingConditions:
    async def test_all_elements_answered_reports_as_answered(self, monkeypatch, no_collection):
        rows = [_requirement(0, "a?"), _requirement(1, "b?")]
        db = _FakeDB(rows, plan=_plan(), pir=_pir(["a?", "b?"]))
        monkeypatch.setattr(rl, "assess_requirement", _assessor([(True, []), (True, [])]))

        out = await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None,
        )
        assert sorted(out.satisfied) == ["a?", "b?"]
        assert out.retired == [] and out.still_open == []
        assert out.stopped_on == "all_elements_answered"
        assert out.answered_everything is True

    async def test_stubborn_element_is_retired_not_left_pending(self, monkeypatch, no_collection):
        rows = [_requirement(0, "a?")]
        db = _FakeDB(rows, plan=_plan(), pir=_pir(["a?"]))
        monkeypatch.setattr(rl, "assess_requirement", _assessor([(False, ["q1"]), (False, ["q2"])]))

        out = await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None,
            attempts_per_element=2,
        )
        assert out.retired == ["a?"]
        assert rows[0].status == "unmet", "tried and given up on is not the same as untried"
        assert out.answered_everything is False

    async def test_source_budget_stops_the_loop_and_says_so(self, monkeypatch, no_collection):
        rows = [_requirement(0, "a?")]
        db = _FakeDB(rows, plan=_plan(), pir=_pir(["a?"]))
        monkeypatch.setattr(rl, "assess_requirement", _assessor([(False, ["q"])]))

        out = await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None,
            source_limit=4, sources_already_used=4,
        )
        assert out.stopped_on == "source_budget"
        assert out.still_open == ["a?"]
        assert out.answered_everything is False, "an exhausted run is not a satisfied one"

    async def test_exhausted_passes_are_not_reported_as_resolved(self, monkeypatch, no_collection):
        rows = [_requirement(0, "a?")]
        db = _FakeDB(rows, plan=_plan(), pir=_pir(["a?"]))
        monkeypatch.setattr(rl, "assess_requirement", _assessor([(False, ["q"])] * 10))

        out = await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None,
            max_passes=1, attempts_per_element=99,
        )
        assert out.stopped_on == "pass_budget"
        assert out.still_open == ["a?"]

    async def test_a_plan_without_a_pir_does_nothing(self):
        db = _FakeDB([], plan=_plan(pir_id=None), pir=None)
        out = await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None,
        )
        assert out.passes_run == 0 and out.sources_added == 0
        assert out.stopped_on == "nothing_to_do"


class TestRetasking:
    async def test_gap_queries_drive_the_next_collection(self, monkeypatch):
        seen = {}

        async def fake_collect(db, plan, row, queries, *a, **kw):
            seen["queries"] = list(queries)
            return 1

        monkeypatch.setattr(rl, "_collect_for_element", fake_collect)
        rows = [_requirement(0, "enrichment levels?")]
        db = _FakeDB(rows, plan=_plan(), pir=_pir(["enrichment levels?"]))
        monkeypatch.setattr(
            rl, "assess_requirement", _assessor([(False, ["IAEA 60 percent Fordow"]), (True, [])])
        )

        out = await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None, attempts_per_element=5,
        )
        assert seen["queries"] == ["IAEA 60 percent Fordow"]
        assert out.sources_added == 1
        assert out.satisfied == ["enrichment levels?"]

    async def test_tried_queries_accumulate_so_they_are_not_repeated(self, monkeypatch, no_collection):
        rows = [_requirement(0, "a?")]
        db = _FakeDB(rows, plan=_plan(), pir=_pir(["a?"]))
        monkeypatch.setattr(rl, "assess_requirement", _assessor([(False, ["q1"]), (False, ["q2"])]))

        await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None,
            max_passes=2, attempts_per_element=5,
        )
        assert rows[0].next_queries == ["q1", "q2"]

    async def test_assessor_reasoning_is_persisted(self, monkeypatch, no_collection):
        rows = [_requirement(0, "a?")]
        db = _FakeDB(rows, plan=_plan(), pir=_pir(["a?"]))
        monkeypatch.setattr(rl, "assess_requirement", _assessor([(False, ["q"])]))

        await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None, max_passes=1,
        )
        assert rows[0].assessment_missing == "still missing"
        assert rows[0].assessment_confidence == "medium"


class TestSyncRequirements:
    async def test_elements_become_rows(self):
        db = _FakeDB([])
        rows = await rl.sync_requirements(db, _pir(["a?", "b?"]))
        assert [r.text for r in rows] == ["a?", "b?"]
        assert [r.ordinal for r in rows] == [0, 1]

    async def test_unchanged_text_keeps_its_state(self):
        existing = _requirement(0, "a?", status="satisfied", attempts=3)
        db = _FakeDB([existing])
        rows = await rl.sync_requirements(db, _pir(["a?"]))
        assert rows[0].status == "satisfied" and rows[0].attempts == 3

    async def test_rewritten_text_resets_state(self):
        """A reworded element is a different question; carrying a stale
        'satisfied' across would claim an answer to something never asked."""
        existing = _requirement(0, "old?", status="satisfied", attempts=3)
        db = _FakeDB([existing])
        rows = await rl.sync_requirements(db, _pir(["new?"]))
        assert rows[0].text == "new?"
        assert rows[0].status == "pending" and rows[0].attempts == 0

    async def test_removed_elements_are_deleted(self):
        db = _FakeDB([_requirement(0, "a?"), _requirement(1, "b?")])
        rows = await rl.sync_requirements(db, _pir(["a?"]))
        assert len(rows) == 1
        assert len(db.deleted) == 1

    async def test_blank_elements_are_ignored(self):
        db = _FakeDB([])
        rows = await rl.sync_requirements(db, _pir(["a?", "  ", ""]))
        assert len(rows) == 1


class _FkEnforcingDB(_FakeDB):
    """A fake that models the one thing the plain fake cannot: the foreign key.

    `collection_activity.source_id` references `collection_sources.id`. The
    original fake accepted any insert in any order, so a pass that logged an
    activity against a source it had not yet flushed looked fine in tests and
    died in Postgres:

        ForeignKeyViolationError: insert or update on table
        "collection_activity" violates foreign key constraint
        "collection_activity_source_id_fkey"

    Live symptom: `requirement_pass` followed five seconds later by
    `requirement_loop_failed`, and no re-tasking at all.
    """

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.visible_source_ids: set = set()
        self._unflushed: list = []

    def add(self, obj):
        name = type(obj).__name__
        if name == "CollectionSource":
            self._unflushed.append(obj)
        elif name == "CollectionActivity":
            sid = getattr(obj, "source_id", None)
            if sid is not None and sid not in self.visible_source_ids:
                raise RuntimeError(
                    "FOREIGN KEY VIOLATION: collection_activity.source_id "
                    f"{sid} is not present in collection_sources"
                )
        super().add(obj)

    async def flush(self):
        for src in self._unflushed:
            self.visible_source_ids.add(src.id)
        self._unflushed.clear()

    async def commit(self):
        await self.flush()
        self.commits += 1


class TestRetaskedSourcesAreFlushedBeforeBeingLogged:
    async def test_a_retasked_source_exists_before_activity_references_it(self, monkeypatch):
        """Regression: the source must be flushed before the activity row that
        carries its id, or the FK rejects the insert and the pass dies."""
        from types import SimpleNamespace

        def fake_search(query, max_results=3, proxy=None):
            return [{"url": "https://example.com/a", "title": "A", "snippet": ""}]

        monkeypatch.setattr("intel_platform.collection.search.web_search", fake_search)
        monkeypatch.setattr(
            "intel_platform.collection.proxy.get_active_proxy_config",
            lambda: SimpleNamespace(get_proxy_url=lambda: None),
        )

        acquired = []

        async def fake_acquire(source, plan, db, store, mode, provider=None, max_results=3):
            acquired.append(source.name)

        db = _FkEnforcingDB([], plan=_plan(), pir=_pir(["a?"]))
        row = _requirement(0, "a?")

        added = await rl._collect_for_element(
            db, _plan(), row, ["baltic cable damage"], None, object(),
            fake_acquire, "nlp", None,
        )

        assert added == 1, "the re-tasked source should have been acquired"
        assert acquired, "acquire_source was never called"


class TestRetaskedSourceIsAcquirable:
    """The re-tasked source must be something the acquisition path can actually use.

    Both of these were wrong in the shipped version, and both were invisible to
    a suite that stubs acquire_source: the type was "web", which is not in the
    connector registry, so every re-tasked source raised

        ValueError: Unknown source type: web.
        Available: ['file_upload', 'web_scrape', 'rss_feed', 'database', 'api_feed']

    while the gap queries feeding it were finding exactly the right pages.
    """

    async def test_source_type_is_a_registered_connector(self, monkeypatch):
        from types import SimpleNamespace

        from intel_platform.connectors.base import CONNECTOR_REGISTRY

        def fake_search(query, max_results=3, proxy=None):
            return [{"url": "https://example.com/a", "title": "A", "snippet": ""}]

        monkeypatch.setattr("intel_platform.collection.search.web_search", fake_search)
        monkeypatch.setattr(
            "intel_platform.collection.proxy.get_active_proxy_config",
            lambda: SimpleNamespace(get_proxy_url=lambda: None),
        )

        seen = {}

        async def capture(source, plan, db, store, mode, provider=None, max_results=3):
            seen["type"] = source.source_type
            seen["config"] = dict(source.config or {})

        db = _FkEnforcingDB([], plan=_plan(), pir=_pir(["a?"]))
        await rl._collect_for_element(
            db, _plan(), _requirement(0, "a?"), ["q"], None, object(), capture, "nlp", None,
        )

        assert seen["type"] in CONNECTOR_REGISTRY, (
            f"{seen['type']!r} is not an acquirable source type; "
            f"registry has {sorted(CONNECTOR_REGISTRY)}"
        )

    async def test_source_config_satisfies_the_connector(self, monkeypatch):
        """The config must pass the connector's own configure(), not merely look right."""
        from types import SimpleNamespace

        from intel_platform.connectors.base import get_connector

        def fake_search(query, max_results=3, proxy=None):
            return [{"url": "https://example.com/a", "title": "A", "snippet": ""}]

        monkeypatch.setattr("intel_platform.collection.search.web_search", fake_search)
        monkeypatch.setattr(
            "intel_platform.collection.proxy.get_active_proxy_config",
            lambda: SimpleNamespace(get_proxy_url=lambda: None),
        )

        captured = {}

        async def capture(source, plan, db, store, mode, provider=None, max_results=3):
            captured["source"] = source

        db = _FkEnforcingDB([], plan=_plan(), pir=_pir(["a?"]))
        await rl._collect_for_element(
            db, _plan(), _requirement(0, "a?"), ["q"], None, object(), capture, "nlp", None,
        )

        src = captured["source"]
        connector = get_connector(src.source_type)
        validated = connector.configure(dict(src.config))
        assert validated["url"] == "https://example.com/a"


class TestTerminalStateNamesWhatHappened:
    """A run that answered nothing must not be labelled as resolved.

    Observed live:

        0/3 element(s) answered after 2 pass(es); 0 source(s) added;
        stopped on all_elements_resolved

    Both remaining elements had been *retired* after exhausting their attempts.
    Nothing was pending, so the old logic called that "all_elements_resolved" —
    which reads as success for a run that answered nothing, and breaks the rule
    this module states in its own docstring.
    """

    async def test_retired_elements_are_not_called_resolved(self, monkeypatch, no_collection):
        rows = [_requirement(0, "a?")]
        db = _FakeDB(rows, plan=_plan(), pir=_pir(["a?"]))
        monkeypatch.setattr(rl, "assess_requirement", _assessor([(False, ["q"])] * 6))

        out = await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None,
            attempts_per_element=1, max_passes=3,
        )
        assert out.retired == ["a?"]
        assert out.stopped_on == "elements_retired"
        assert out.stopped_on != "all_elements_resolved"
        assert out.answered_everything is False

    async def test_genuinely_answered_elements_say_so(self, monkeypatch, no_collection):
        rows = [_requirement(0, "a?")]
        db = _FakeDB(rows, plan=_plan(), pir=_pir(["a?"]))
        monkeypatch.setattr(rl, "assess_requirement", _assessor([(True, [])]))

        out = await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None,
        )
        assert out.satisfied == ["a?"]
        assert out.stopped_on == "all_elements_answered"
        assert out.answered_everything is True

    async def test_a_mix_of_answered_and_retired_reports_retired(self, monkeypatch, no_collection):
        """One answered and one given up on is not a fully answered run."""
        rows = [_requirement(0, "a?"), _requirement(1, "b?")]
        db = _FakeDB(rows, plan=_plan(), pir=_pir(["a?", "b?"]))
        monkeypatch.setattr(rl, "assess_requirement", _assessor([(True, []), (False, ["q"])] ))

        out = await rl.run_requirement_passes(
            "plan-1", _factory(db), lambda: None, object(), None,
            attempts_per_element=1, max_passes=3,
        )
        assert out.satisfied == ["a?"] and out.retired == ["b?"]
        assert out.stopped_on == "elements_retired"
        assert out.answered_everything is False
