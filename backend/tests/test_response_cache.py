"""The endpoint response cache.

`@cached(ttl=60)` sat on `/api/topics` and cached nothing: three back-to-back
calls each took ~20s against a live graph. The key was built from
`str(args)` and `str(sorted(kwargs.items()))`, and FastAPI passes
dependency-injected services as arguments — `get_graph_store` returns a new
`GraphStore(driver)` per request, whose default repr carries the object's
memory address. Every request therefore produced a unique key: the cache stored
every response and returned none of them.

It hid well. CPython reuses the address of an object freed immediately, so a
throwaway check ("call it twice with a fresh service") does see a hit; only
holding the services alive, as a real request does, exposes it.
"""
from __future__ import annotations

import asyncio

import pytest

from intel_platform.api import cache as cache_mod
from intel_platform.api.cache import _make_key, cached, clear_cache


class _Service:
    """Stands in for GraphStore(driver): a new instance per request."""


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


class TestKeying:
    def test_injected_services_do_not_churn_the_key(self):
        """The whole defect in one assertion."""
        def endpoint(project_id, store=None):
            ...

        a = _make_key(endpoint, (), {"project_id": "p1", "store": _Service()})
        b = _make_key(endpoint, (), {"project_id": "p1", "store": _Service()})
        assert a == b

    def test_request_parameters_still_separate_entries(self):
        def endpoint(project_id, store=None):
            ...

        svc = _Service()
        a = _make_key(endpoint, (), {"project_id": "p1", "store": svc})
        b = _make_key(endpoint, (), {"project_id": "p2", "store": svc})
        assert a != b

    def test_every_query_parameter_participates(self):
        def endpoint(project_id, method="tfidf", granularity="medium"):
            ...

        base = {"project_id": "p", "method": "tfidf", "granularity": "medium"}
        assert _make_key(endpoint, (), base) != _make_key(endpoint, (), {**base, "granularity": "detailed"})
        assert _make_key(endpoint, (), base) != _make_key(endpoint, (), {**base, "method": "semantic"})

    def test_two_endpoints_never_collide(self):
        """Same-named functions in different modules must not share entries."""
        def a(project_id):
            ...

        def b(project_id):
            ...

        b.__name__ = "a"
        assert _make_key(a, (), {"project_id": "p"}) != _make_key(b, (), {"project_id": "p"})

    def test_argument_order_does_not_matter(self):
        def endpoint(project_id, limit=10):
            ...

        one = _make_key(endpoint, (), {"project_id": "p", "limit": 10})
        two = _make_key(endpoint, (), {"limit": 10, "project_id": "p"})
        assert one == two

    def test_collection_arguments_are_compared_by_value(self):
        def endpoint(ids):
            ...

        assert _make_key(endpoint, (), {"ids": ["a", "b"]}) == _make_key(endpoint, (), {"ids": ["a", "b"]})
        assert _make_key(endpoint, (), {"ids": ["a", "b"]}) != _make_key(endpoint, (), {"ids": ["b", "a"]})

    def test_the_key_holds_no_memory_address(self):
        def endpoint(store=None):
            ...

        assert "0x" not in _make_key(endpoint, (), {"store": _Service()})


class TestCachingActuallyHappens:
    async def test_repeated_requests_run_the_work_once(self):
        """Services held alive for the whole run, as they are during a request —
        without that, address reuse makes a broken cache look like it works."""
        runs = {"n": 0}

        @cached(ttl=60)
        async def get_topic_tree(project_id, store=None):
            runs["n"] += 1
            return {"tree": project_id}

        held = [_Service() for _ in range(3)]
        results = [await get_topic_tree(project_id="p1", store=s) for s in held]

        assert runs["n"] == 1, "the expensive work ran again for an identical request"
        assert results == [{"tree": "p1"}] * 3
        assert len(cache_mod._cache) == 1, "one entry per distinct request, not per request"

    async def test_a_different_project_is_not_served_a_stale_answer(self):
        runs = []

        @cached(ttl=60)
        async def get_topic_tree(project_id, store=None):
            runs.append(project_id)
            return {"tree": project_id}

        held = [_Service() for _ in range(2)]
        assert await get_topic_tree(project_id="p1", store=held[0]) == {"tree": "p1"}
        assert await get_topic_tree(project_id="p2", store=held[1]) == {"tree": "p2"}
        assert runs == ["p1", "p2"]

    async def test_an_expired_entry_is_recomputed(self):
        runs = {"n": 0}

        @cached(ttl=0)
        async def endpoint(project_id):
            runs["n"] += 1
            return runs["n"]

        await endpoint(project_id="p")
        await asyncio.sleep(0.01)
        await endpoint(project_id="p")
        assert runs["n"] == 2

    def test_sync_endpoints_cache_too(self):
        runs = {"n": 0}

        @cached(ttl=60)
        def endpoint(project_id, store=None):
            runs["n"] += 1
            return runs["n"]

        held = [_Service() for _ in range(3)]
        for s in held:
            endpoint(project_id="p", store=s)
        assert runs["n"] == 1


class TestUnboundedGrowth:
    def test_the_cache_does_not_grow_once_per_request(self):
        """Every miss stored a full response, so a cache that never hit was also
        a slow leak up to the 500-entry cap — each entry a whole topic tree."""
        @cached(ttl=60)
        def endpoint(project_id, store=None):
            return "x" * 1000

        held = [_Service() for _ in range(50)]
        for s in held:
            endpoint(project_id="p", store=s)
        assert len(cache_mod._cache) == 1
