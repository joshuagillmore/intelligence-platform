"""Tests for `_acquire_urls_concurrent` — bounded concurrent multi-URL fetch.

Covers record aggregation, per-URL error isolation, `CollectionActivity`
telemetry, the `urls[:10]` cap, and the Semaphore concurrency bound.
"""
from __future__ import annotations

import asyncio

from intel_platform.collection.agentic import _acquire_urls_concurrent
from intel_platform.db.models import CollectionActivity


# ---------------------------------------------------------------------------
# Minimal fakes mirroring the collection runtime contract
# ---------------------------------------------------------------------------

class FakeResult:
    def __init__(self, records):
        self.records = records


class FakeConnector:
    """acquire(config) -> object with .records. `fail_urls` raise instead."""

    def __init__(self, *, records_per_url=1, fail_urls=None):
        self.records_per_url = records_per_url
        self.fail_urls = set(fail_urls or [])
        self.seen_urls: list[str] = []

    async def acquire(self, config):
        url = config["url"]
        self.seen_urls.append(url)
        await asyncio.sleep(0)  # yield control so fetches can interleave
        if url in self.fail_urls:
            raise RuntimeError(f"boom for {url}")
        recs = [
            {"url": url, "content": f"content from {url} number {i}"}
            for i in range(self.records_per_url)
        ]
        return FakeResult(recs)


class ConcurrencyTrackingConnector:
    """Records the peak number of concurrently in-flight acquire() calls."""

    def __init__(self, hold=0.02):
        self.hold = hold
        self.active = 0
        self.max_active = 0

    async def acquire(self, config):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.hold)
            return FakeResult([{"url": config["url"], "content": "hello world"}])
        finally:
            self.active -= 1


class FakeDB:
    """AsyncSession-like: sync add(), async commit()."""

    def __init__(self):
        self.added: list = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _events(db: FakeDB) -> list[str]:
    return [a.event for a in db.added if isinstance(a, CollectionActivity)]


def _make_plan_source():
    plan = type("Plan", (), {"id": "plan-1"})()
    source = type("Source", (), {"id": "source-1"})()
    return plan, source


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAcquireUrlsConcurrent:
    async def test_aggregates_records_across_urls(self):
        connector = FakeConnector(records_per_url=2)
        db = FakeDB()
        plan, source = _make_plan_source()
        urls = ["https://a.example.com", "https://b.example.com", "https://c.example.com"]

        records, errors = await _acquire_urls_concurrent(
            connector, {"timeout": 10}, urls,
            db=db, plan=plan, source=source, concurrency=4,
        )

        assert errors == []
        assert len(records) == 6  # 3 urls * 2 records each
        assert {r["url"] for r in records} == set(urls)

    async def test_one_url_failure_does_not_kill_others(self):
        connector = FakeConnector(records_per_url=1, fail_urls=["https://bad.example.com"])
        db = FakeDB()
        plan, source = _make_plan_source()
        urls = ["https://good1.example.com", "https://bad.example.com", "https://good2.example.com"]

        records, errors = await _acquire_urls_concurrent(
            connector, {}, urls,
            db=db, plan=plan, source=source, concurrency=4,
        )

        # The good URLs still produce records; only the bad one is in errors.
        assert len(records) == 2
        assert {r["url"] for r in records} == {"https://good1.example.com", "https://good2.example.com"}
        assert len(errors) == 1
        assert "https://bad.example.com" in errors[0]

    async def test_emits_lifecycle_activity_events(self):
        connector = FakeConnector(records_per_url=1, fail_urls=["https://bad.example.com"])
        db = FakeDB()
        plan, source = _make_plan_source()
        urls = ["https://good.example.com", "https://bad.example.com"]

        await _acquire_urls_concurrent(
            connector, {}, urls,
            db=db, plan=plan, source=source, concurrency=4,
        )

        events = _events(db)
        # One url_fetching per URL, plus a fetched (good) and a failed (bad).
        assert events.count("url_fetching") == 2
        assert events.count("url_fetched") == 1
        assert events.count("url_failed") == 1
        # Activity rows are tagged with the plan/source ids.
        activities = [a for a in db.added if isinstance(a, CollectionActivity)]
        assert all(a.plan_id == "plan-1" and a.source_id == "source-1" for a in activities)

    async def test_caps_at_ten_urls(self):
        connector = FakeConnector(records_per_url=1)
        db = FakeDB()
        plan, source = _make_plan_source()
        urls = [f"https://site{i}.example.com" for i in range(15)]

        records, errors = await _acquire_urls_concurrent(
            connector, {}, urls,
            db=db, plan=plan, source=source, concurrency=4,
        )

        # Only the first 10 URLs are fetched.
        assert len(connector.seen_urls) == 10
        assert len(records) == 10
        assert set(connector.seen_urls) == set(urls[:10])

    async def test_concurrency_is_bounded(self):
        connector = ConcurrencyTrackingConnector(hold=0.02)
        db = FakeDB()
        plan, source = _make_plan_source()
        urls = [f"https://site{i}.example.com" for i in range(8)]

        await _acquire_urls_concurrent(
            connector, {}, urls,
            db=db, plan=plan, source=source, concurrency=2,
        )

        # Never more than `concurrency` fetches in flight, and it actually
        # ran in parallel (peaked at the bound rather than serializing).
        assert connector.max_active <= 2
        assert connector.max_active == 2

    async def test_concurrency_floor_of_one(self):
        # concurrency <= 0 must not deadlock: Semaphore is clamped to >= 1.
        connector = ConcurrencyTrackingConnector(hold=0.0)
        db = FakeDB()
        plan, source = _make_plan_source()
        urls = ["https://a.example.com", "https://b.example.com"]

        records, errors = await _acquire_urls_concurrent(
            connector, {}, urls,
            db=db, plan=plan, source=source, concurrency=0,
        )

        assert len(records) == 2
        assert connector.max_active == 1
