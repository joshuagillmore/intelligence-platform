"""Tests for the enrichment provider registry (Task 2.2) and the orchestrator
service (Task 2.3)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

# Register the real providers before the registry fixture snapshots it, so a
# test that uses one (E-3) cannot leave the registry emptied for later files.
import intel_platform.enrichment.providers  # noqa: F401
from intel_platform.enrichment import base as base_mod
from intel_platform.enrichment import service as service_mod
from intel_platform.enrichment.cache import RateLimiter
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


@pytest.fixture(autouse=True)
def _fresh_shared_limiter(monkeypatch):
    """The limiter is process-wide by design (E-2); give each test its own so
    provider names reused across tests cannot throttle one another."""
    monkeypatch.setattr(service_mod, "_RATE_LIMITER", RateLimiter(), raising=False)


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


# --- E-2: one rate limiter per process, not per request ---------------------

async def test_rate_limit_is_shared_across_service_instances():
    # Provider quotas (ip-api 45/min, Nominatim 1/s) are per client IP. The
    # route and the auto-enrich hook build a new EnrichmentService per call, so
    # a limiter owned by the service never throttled anything across requests.
    class _QuotaProvider(EnrichmentProvider):
        name = "quotaprov"
        supported_types = {"IPAddress"}
        rate = 0.001     # effectively no refill within the test
        capacity = 1.0

        async def lookup(self, value, entity_type):
            return EnrichmentResult(properties={"x": 1})

    register_provider(_QuotaProvider)
    entity = {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}

    first = EnrichmentService(_store_with_entity(entity), write_related=MagicMock(), cache=_cache_miss())
    await first.enrich_entity("e1")  # spends the only token

    second = EnrichmentService(_store_with_entity(entity), write_related=MagicMock(), cache=_cache_miss())
    assert second.limiter is first.limiter
    assert second.limiter.try_acquire("quotaprov", rate=0.001, capacity=1.0) is False


def test_route_and_hook_services_use_the_shared_limiter():
    from intel_platform.api.routes import enrichment as enrichment_route

    route_service = enrichment_route._service(MagicMock())
    assert route_service.limiter is EnrichmentService(MagicMock()).limiter


def test_explicit_limiter_still_wins():
    own = RateLimiter()
    assert EnrichmentService(MagicMock(), limiter=own).limiter is own


# --- E-3: a Vulnerability is looked up by its CVE id ------------------------

def _kev_service(monkeypatch, entity, catalog):
    from intel_platform.enrichment.providers import kev

    kev._reset_catalog()
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value={"vulnerabilities": catalog})
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    monkeypatch.setattr(kev, "ProxiedClient", lambda *a, **k: client)
    register_provider(kev.KEVProvider)
    store = _store_with_entity(entity)
    cache = _cache_miss()
    return EnrichmentService(store, write_related=MagicMock(), cache=cache), store, cache, client


async def test_named_vulnerability_uses_its_cve_id_property(monkeypatch):
    # Extraction names the node "Log4Shell" and records cve_id; KEV used to be
    # asked about "LOG4SHELL", answer "not known-exploited", and have that
    # cached for a day.
    entity = {
        "id": "v1", "name": "Log4Shell", "entity_type": "Vulnerability",
        "project_id": "test-p", "cve_id": "CVE-2021-44228",
    }
    svc, store, cache, _ = _kev_service(
        monkeypatch, entity, [{"cveID": "CVE-2021-44228", "dateAdded": "2021-12-10"}],
    )
    out = await svc.enrich_entity("v1", only={"kev"})

    assert out["observable"] == "CVE-2021-44228"
    assert out["providers"]["kev"]["status"] == "ok"
    _, props = store.update_entity.call_args_list[0][0]
    assert props["known_exploited"] is True
    assert cache.set.await_args[0][1] == "CVE-2021-44228"  # cached under the id


async def test_vulnerability_without_a_cve_id_asserts_nothing(monkeypatch):
    entity = {"id": "v1", "name": "Log4Shell", "entity_type": "Vulnerability", "project_id": "test-p"}
    svc, store, cache, client = _kev_service(
        monkeypatch, entity, [{"cveID": "CVE-2021-44228", "dateAdded": "2021-12-10"}],
    )
    out = await svc.enrich_entity("v1", only={"kev"})

    assert out["providers"]["kev"] == {"status": "skipped", "reason": "no CVE id"}
    store.update_entity.assert_not_called()   # nothing written, not even `enriched`
    cache.set.assert_not_awaited()
    client.get.assert_not_called()


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class _ThreadRecordingStore:
    """A GraphStore stand-in that records whether each call ran on the loop."""

    def __init__(self, entity):
        self.entity = entity
        self.on_loop: dict[str, bool] = {}

    def _mark(self, name):
        self.on_loop[name] = _on_event_loop()

    def get_entity(self, entity_id):
        self._mark("get_entity")
        return self.entity

    def update_entity(self, entity_id, props):
        self._mark("update_entity")
        return self.entity

    def find_entity_by_exact_name(self, project_id, name, entity_type=None):
        self._mark("find_entity_by_exact_name")
        return None

    def search_entity_by_name(self, project_id, name, limit=20):
        self._mark("search_entity_by_name")
        return []

    def create_entity(self, model):
        self._mark("create_entity")
        return {"id": "n2"}

    def create_relationship(self, rel):
        self._mark("create_relationship")
        return {}


async def test_graph_store_calls_run_off_the_event_loop():
    # E-4: the sync Neo4j driver blocks; on the loop, one Investigate stalls
    # /health and every other request for the length of its writes.
    class _RelProvider(EnrichmentProvider):
        name = "relprov2"
        supported_types = {"Domain"}

        async def lookup(self, value, entity_type):
            return EnrichmentResult(
                properties={"x": 1},
                related=[RelatedEntity(name="1.2.3.4", entity_type="IPAddress", rel_type="RESOLVES_TO")],
            )

    register_provider(_RelProvider)
    store = _ThreadRecordingStore(
        {"id": "e1", "name": "evil.com", "entity_type": "Domain", "project_id": "test-p"}
    )
    out = await EnrichmentService(store, cache=_cache_miss()).enrich_entity("e1")

    assert out["providers"]["relprov2"]["status"] == "ok"
    assert set(store.on_loop) >= {
        "get_entity", "update_entity", "find_entity_by_exact_name", "create_entity", "create_relationship",
    }
    assert not any(store.on_loop.values()), store.on_loop


async def test_cache_hit_apply_runs_off_the_event_loop():
    register_provider(_PropProvider)
    store = _ThreadRecordingStore(
        {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}
    )
    cache = MagicMock()
    cache.get = AsyncMock(return_value={"properties": {"asn": "AS1"}, "related": []})
    cache.set = AsyncMock()
    out = await EnrichmentService(store, cache=cache).enrich_entity("e1")
    assert out["providers"]["propprov"]["status"] == "cached"
    assert store.on_loop.get("update_entity") is False


def test_default_writer_passes_project_id_on_the_relationship(monkeypatch):
    # Contract 16: create_relationship uses Relationship.project_id for a
    # labelled, indexed match; the enrichment writer must supply it.
    import intel_platform.models.relationships as rel_mod

    captured: list[dict] = []

    class _CapturingRelationship:
        def __init__(self, **kwargs):
            captured.append(kwargs)
            self.__dict__.update(kwargs)

    monkeypatch.setattr(rel_mod, "Relationship", _CapturingRelationship)
    store = MagicMock()
    store.find_entity_by_exact_name = MagicMock(return_value={"id": "n2"})
    store.create_relationship = MagicMock(return_value={})
    EnrichmentService(store, cache=_cache_miss())._default_write_related(
        {"id": "e1"},
        [RelatedEntity(name="1.2.3.4", entity_type="IPAddress", rel_type="RESOLVES_TO")],
        "test-p",
    )
    assert captured and captured[0]["project_id"] == "test-p"


async def test_geoip_over_tor_is_reported_skipped_and_writes_nothing(monkeypatch):
    from intel_platform.enrichment.providers import geoip

    monkeypatch.setattr(geoip, "_egress_mode", AsyncMock(return_value="tor"))
    client = MagicMock()
    client.get = AsyncMock()
    monkeypatch.setattr(geoip, "ProxiedClient", lambda *a, **k: client)
    register_provider(geoip.GeoIPProvider)
    store = _store_with_entity(
        {"id": "e1", "name": "8.8.8.8", "entity_type": "IPAddress", "project_id": "test-p"}
    )
    cache = _cache_miss()
    out = await EnrichmentService(store, write_related=MagicMock(), cache=cache).enrich_entity(
        "e1", only={"geoip"},
    )
    assert out["providers"]["geoip"] == {"status": "skipped", "reason": "plain-HTTP lookup not sent over Tor"}
    store.update_entity.assert_not_called()
    cache.set.assert_not_awaited()
    client.get.assert_not_called()


# --- Low -> E: KEV and NVD no longer overwrite each other's severity --------

class _NodeStore:
    """A one-node store that really merges properties (SET n += props)."""

    def __init__(self, node):
        self.node = dict(node)

    def get_entity(self, entity_id):
        return dict(self.node)

    def update_entity(self, entity_id, props):
        self.node.update(props)
        return dict(self.node)


def _vuln_services(monkeypatch, *, in_kev: bool, nvd_severity: str):
    from intel_platform.enrichment.providers import kev, nvd

    kev._reset_catalog()

    def client_for(payload):
        resp = MagicMock()
        resp.status_code = 200
        resp.json = MagicMock(return_value=payload)
        client = MagicMock()
        client.get = AsyncMock(return_value=resp)
        return client

    kev_catalog = [{"cveID": "CVE-2021-44228", "dateAdded": "2021-12-10"}] if in_kev else []
    kev_client = client_for({"vulnerabilities": kev_catalog})
    nvd_client = client_for({"vulnerabilities": [{"cve": {
        "id": "CVE-2021-44228",
        "descriptions": [{"lang": "en", "value": "Log4j RCE"}],
        "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 6.5, "baseSeverity": nvd_severity}}]},
    }}]})
    monkeypatch.setattr(kev, "ProxiedClient", lambda *a, **k: kev_client)
    monkeypatch.setattr(nvd, "ProxiedClient", lambda *a, **k: nvd_client)
    register_provider(kev.KEVProvider)
    register_provider(nvd.NVDProvider)
    store = _NodeStore({
        "id": "v1", "name": "CVE-2021-44228", "entity_type": "Vulnerability", "project_id": "test-p",
    })
    return EnrichmentService(store, write_related=MagicMock(), cache=_cache_miss()), store


@pytest.mark.parametrize("order", [("kev", "nvd"), ("nvd", "kev")])
async def test_kev_and_nvd_severity_do_not_depend_on_which_ran_last(monkeypatch, order):
    # Each used to write `severity`; whichever finished last won, so a
    # known-exploited CVE could read "medium".
    svc, store = _vuln_services(monkeypatch, in_kev=True, nvd_severity="MEDIUM")
    for name in order:
        await svc.enrich_entity("v1", only={name})

    assert store.node["kev_severity"] == "critical"
    assert store.node["cvss_severity"] == "medium"
    assert store.node["severity"] == "critical"


async def test_severity_follows_cvss_when_not_known_exploited(monkeypatch):
    svc, store = _vuln_services(monkeypatch, in_kev=False, nvd_severity="HIGH")
    await svc.enrich_entity("v1")  # both providers, concurrently

    assert store.node["known_exploited"] is False
    assert "kev_severity" not in store.node
    assert store.node["severity"] == "high"


async def test_malformed_cve_id_property_is_not_used(monkeypatch):
    entity = {
        "id": "v1", "name": "Log4Shell", "entity_type": "Vulnerability",
        "project_id": "test-p", "cve_id": "N/A",
    }
    svc, store, _, _ = _kev_service(monkeypatch, entity, [])
    out = await svc.enrich_entity("v1", only={"kev"})
    assert out["providers"]["kev"]["status"] == "skipped"
    store.update_entity.assert_not_called()
