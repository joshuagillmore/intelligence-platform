"""Tests for the enrichment provider registry (Task 2.2) and the orchestrator
service (Task 2.3)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from intel_platform.enrichment import base as base_mod
from intel_platform.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
    RelatedEntity,
    get_providers_for,
    register_provider,
)
from intel_platform.enrichment.service import EnrichmentService


@pytest.fixture(autouse=True)
def _isolated_registry():
    """Snapshot/restore the global provider registry so tests don't leak into
    each other (the registry is module-global mutable state)."""
    saved = dict(base_mod.PROVIDER_REGISTRY)
    base_mod.PROVIDER_REGISTRY.clear()
    yield
    base_mod.PROVIDER_REGISTRY.clear()
    base_mod.PROVIDER_REGISTRY.update(saved)


def _cache_miss():
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


def _store_with_entity(entity):
    store = MagicMock()
    store.get_entity = MagicMock(return_value=entity)
    store.update_entity = MagicMock(return_value=entity)
    return store


class _FakeIP(EnrichmentProvider):
    name = "fake_ip"
    supported_types = {"IPAddress"}
    auto = True

    async def lookup(self, value, entity_type):
        return EnrichmentResult(properties={"seen": value})


class _KeyedIP(EnrichmentProvider):
    name = "keyed_ip"
    supported_types = {"IPAddress"}
    requires_key = True

    async def lookup(self, value, entity_type):
        return EnrichmentResult()


# --- registry ---------------------------------------------------------------

def test_register_and_match_by_type():
    register_provider(_FakeIP)
    ip_providers = get_providers_for("IPAddress")
    assert any(isinstance(p, _FakeIP) for p in ip_providers)


def test_provider_excluded_for_unsupported_type():
    register_provider(_FakeIP)
    domain_providers = get_providers_for("Domain")
    assert all(not isinstance(p, _FakeIP) for p in domain_providers)


def test_requires_key_excluded_without_key_included_with():
    register_provider(_KeyedIP)
    without = [p.name for p in get_providers_for("IPAddress")]
    assert "keyed_ip" not in without
    with_key = [p.name for p in get_providers_for("IPAddress", available_keys={"keyed_ip"})]
    assert "keyed_ip" in with_key


# --- orchestrator service (Task 2.3) ----------------------------------------

class _PropProvider(EnrichmentProvider):
    name = "propprov"
    supported_types = {"IPAddress"}
    auto = True

    async def lookup(self, value, entity_type):
        return EnrichmentResult(properties={"asn": "AS123"}, source_url="http://x")


class _BoomProvider(EnrichmentProvider):
    name = "boomprov"
    supported_types = {"IPAddress"}
    auto = True

    async def lookup(self, value, entity_type):
        raise RuntimeError("provider down")


async def test_enrich_merges_properties_onto_node():
    register_provider(_PropProvider)
    store = _store_with_entity(
        {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}
    )
    svc = EnrichmentService(store, write_related=MagicMock(), cache=_cache_miss())
    out = await svc.enrich_entity("e1")
    assert out["providers"]["propprov"]["status"] == "ok"
    entity_id, props = store.update_entity.call_args[0]
    assert entity_id == "e1"
    assert props["asn"] == "AS123"
    assert props["enriched"] is True
    assert "enriched_at" in props


async def test_enrich_isolates_failing_provider():
    register_provider(_PropProvider)
    register_provider(_BoomProvider)
    store = _store_with_entity(
        {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}
    )
    svc = EnrichmentService(store, write_related=MagicMock(), cache=_cache_miss())
    out = await svc.enrich_entity("e1")
    assert out["providers"]["boomprov"]["status"] == "error"
    assert out["providers"]["propprov"]["status"] == "ok"  # the good one still applied
    store.update_entity.assert_called()  # failure did not block the write


async def test_enrich_cache_hit_applies_without_lookup():
    class _SpyProvider(EnrichmentProvider):
        name = "spyprov"
        supported_types = {"IPAddress"}
        called = False

        async def lookup(self, value, entity_type):
            _SpyProvider.called = True
            return EnrichmentResult(properties={"asn": "AS-FRESH"})

    register_provider(_SpyProvider)
    store = _store_with_entity(
        {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}
    )
    cache = MagicMock()
    cache.get = AsyncMock(return_value={
        "properties": {"asn": "AS-CACHED"}, "related": [], "source_url": "", "raw": {},
    })
    cache.set = AsyncMock()
    svc = EnrichmentService(store, write_related=MagicMock(), cache=cache)
    out = await svc.enrich_entity("e1")

    assert out["providers"]["spyprov"]["status"] == "cached"
    assert _SpyProvider.called is False  # cache hit -> no external lookup
    # B2: the cached result is still applied to THIS node (not silently skipped)
    _, props = store.update_entity.call_args[0]
    assert props["asn"] == "AS-CACHED"
    assert props["enriched"] is True


async def test_auto_enrich_runs_only_auto_providers():
    class _AutoD(EnrichmentProvider):
        name = "autod"
        supported_types = {"Domain"}
        auto = True

        async def lookup(self, value, entity_type):
            return EnrichmentResult(properties={"a": 1})

    class _ManualD(EnrichmentProvider):
        name = "manuald"
        supported_types = {"Domain"}
        auto = False

        async def lookup(self, value, entity_type):
            return EnrichmentResult(properties={"m": 1})

    register_provider(_AutoD)
    register_provider(_ManualD)
    entity = {"id": "e1", "name": "evil.com", "entity_type": "Domain", "project_id": "test-p"}
    svc = EnrichmentService(_store_with_entity(entity), write_related=MagicMock(), cache=_cache_miss())
    out = await svc.auto_enrich(entity)
    assert "autod" in out["providers"]
    assert "manuald" not in out["providers"]


async def test_related_entity_invokes_writer():
    class _RelProvider(EnrichmentProvider):
        name = "relprov"
        supported_types = {"Domain"}

        async def lookup(self, value, entity_type):
            return EnrichmentResult(related=[
                RelatedEntity(name="1.2.3.4", entity_type="IPAddress", rel_type="RESOLVES_TO"),
            ])

    register_provider(_RelProvider)
    entity = {"id": "e1", "name": "evil.com", "entity_type": "Domain", "project_id": "test-p"}
    writer = MagicMock()
    svc = EnrichmentService(_store_with_entity(entity), write_related=writer, cache=_cache_miss())
    await svc.enrich_entity("e1")
    writer.assert_called_once()
    _, related, _ = writer.call_args[0]
    assert related[0].rel_type == "RESOLVES_TO"


def test_default_writer_creates_node_and_edge():
    # The built-in graph writer upserts the related node and its typed edge.
    store = MagicMock()
    store.find_entity_by_exact_name = MagicMock(return_value=None)
    store.search_entity_by_name = MagicMock(return_value=[])
    store.create_entity = MagicMock(return_value={"id": "n2"})
    store.create_relationship = MagicMock(return_value={})
    svc = EnrichmentService(store, cache=_cache_miss())
    svc._default_write_related(
        {"id": "e1"},
        [RelatedEntity(name="1.2.3.4", entity_type="IPAddress", rel_type="RESOLVES_TO")],
        "test-p",
    )
    store.create_entity.assert_called_once()
    store.create_relationship.assert_called_once()
    rel = store.create_relationship.call_args[0][0]
    assert rel.rel_type == "RESOLVES_TO"
    assert rel.source_id == "e1" and rel.target_id == "n2"
    assert rel.method == "enrichment"


def test_default_writer_dedupes_by_exact_name():
    # A high-frequency parent (e.g. a country) must reuse the existing node via
    # the deterministic exact-name lookup, not create a duplicate.
    store = MagicMock()
    store.find_entity_by_exact_name = MagicMock(return_value={"id": "existing-russia"})
    store.create_entity = MagicMock()
    store.create_relationship = MagicMock(return_value={})
    svc = EnrichmentService(store, cache=_cache_miss())
    svc._default_write_related(
        {"id": "e1"},
        [RelatedEntity(name="Russia", entity_type="Location", rel_type="BELONGS_TO")],
        "test-p",
    )
    store.create_entity.assert_not_called()
    rel = store.create_relationship.call_args[0][0]
    assert rel.target_id == "existing-russia" and rel.rel_type == "BELONGS_TO"


async def test_store_write_failure_is_isolated():
    # B1: a Neo4j write failure during apply must not abort the run or propagate
    # out of enrich_entity — the provider is marked error, the call returns.
    register_provider(_PropProvider)
    store = _store_with_entity(
        {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}
    )
    store.update_entity = MagicMock(side_effect=RuntimeError("neo4j down"))
    svc = EnrichmentService(store, write_related=MagicMock(), cache=_cache_miss())
    out = await svc.enrich_entity("e1")  # must not raise
    assert out["providers"]["propprov"]["status"] == "error"


async def test_enrich_only_filters_to_named_providers():
    register_provider(_PropProvider)  # "propprov" on IPAddress

    class _Other(EnrichmentProvider):
        name = "otherprov"
        supported_types = {"IPAddress"}

        async def lookup(self, value, entity_type):
            return EnrichmentResult(properties={"x": 1})

    register_provider(_Other)
    store = _store_with_entity(
        {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}
    )
    svc = EnrichmentService(store, write_related=MagicMock(), cache=_cache_miss())
    out = await svc.enrich_entity("e1", only={"propprov"})
    assert "propprov" in out["providers"]
    assert "otherprov" not in out["providers"]


async def test_enrich_bypass_cache_skips_cache_get():
    register_provider(_PropProvider)
    store = _store_with_entity(
        {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}
    )
    cache = MagicMock()
    cache.get = AsyncMock(return_value={"properties": {"asn": "AS-CACHED"}})
    cache.set = AsyncMock()
    svc = EnrichmentService(store, write_related=MagicMock(), cache=cache)
    out = await svc.enrich_entity("e1", bypass_cache=True)
    cache.get.assert_not_called()  # bypass -> fresh lookup, cache not consulted
    assert out["providers"]["propprov"]["status"] == "ok"


async def test_investigate_bounded_by_overall_budget(monkeypatch):
    # A provider slower than the budget yields status "timeout", not a hang.
    class _SlowProvider(EnrichmentProvider):
        name = "slowprov"
        supported_types = {"IPAddress"}

        async def lookup(self, value, entity_type):
            await asyncio.sleep(5)
            return EnrichmentResult()

    register_provider(_SlowProvider)
    monkeypatch.setattr(EnrichmentService, "OVERALL_BUDGET_S", 0.05)
    store = _store_with_entity(
        {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}
    )
    svc = EnrichmentService(store, write_related=MagicMock(), cache=_cache_miss())
    out = await svc.enrich_entity("e1")
    assert out["providers"]["slowprov"]["status"] == "timeout"


async def test_apply_strips_protected_identity_keys():
    # S1: a provider returning node-identity keys must not clobber them.
    class _EvilProvider(EnrichmentProvider):
        name = "evilprov"
        supported_types = {"IPAddress"}

        async def lookup(self, value, entity_type):
            return EnrichmentResult(properties={
                "asn": "AS1", "id": "HACKED", "project_id": "other", "entity_type": "Malware",
            })

    register_provider(_EvilProvider)
    store = _store_with_entity(
        {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}
    )
    svc = EnrichmentService(store, write_related=MagicMock(), cache=_cache_miss())
    await svc.enrich_entity("e1")
    _, props = store.update_entity.call_args[0]
    assert props["asn"] == "AS1"
    assert "id" not in props
    assert "project_id" not in props
    assert "entity_type" not in props
