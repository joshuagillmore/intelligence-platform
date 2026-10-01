"""E-1: a provider that could not get an answer must say so.

Every provider used to swallow transport/status/parse failures and return an
empty ``EnrichmentResult``. The service then applied it, stamped the node
``enriched: true``, cached it for the provider's full TTL (30 days for geoip, 7
for NVD/email) and reported ``status: "ok"`` — an email-provider outage wrote
``has_mx: false``. An outage is not an answer.

Each real provider class is exercised against a client that raises, one that
returns 429 (with a JSON body the old code would happily read), one that
returns 500 (with an HTML body), and a 200 whose body is not JSON. The lookup
must raise ``ProviderError``; through the service, nothing may be cached and
nothing may be written to the graph. No network: every client is a fake.
"""
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import intel_platform.enrichment.providers  # noqa: F401  (register providers)
from intel_platform.enrichment import service as service_mod
from intel_platform.enrichment.base import ProviderError
from intel_platform.enrichment.cache import RateLimiter
from intel_platform.enrichment.providers import certs, dns, email, geocode, geoip, kev, nvd, rdap
from intel_platform.enrichment.service import EnrichmentService
from tests.ids import tp

# (module, provider class, entity type, entity name)
PROVIDERS = [
    pytest.param(dns, dns.DNSProvider, "Domain", "evil.com", id="dns"),
    pytest.param(geoip, geoip.GeoIPProvider, "IPAddress", "8.8.8.8", id="geoip"),
    pytest.param(kev, kev.KEVProvider, "Vulnerability", "CVE-2021-44228", id="kev"),
    pytest.param(nvd, nvd.NVDProvider, "Vulnerability", "CVE-2021-44228", id="nvd"),
    pytest.param(rdap, rdap.RDAPProvider, "Domain", "evil.com", id="rdap"),
    pytest.param(certs, certs.CertsProvider, "Domain", "evil.com", id="certs"),
    pytest.param(email, email.EmailProvider, "EmailAddress", "admin@evil.com", id="email"),
    pytest.param(geocode, geocode.GeocodeProvider, "Location", "Mozdok", id="geocode"),
]


def _raising_client():
    client = MagicMock()
    client.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    return client


def _status_client(status: int, json_body=None, json_error: bool = False):
    resp = MagicMock()
    resp.status_code = status
    if json_error:
        resp.json = MagicMock(side_effect=ValueError("Expecting value: line 1 column 1"))
    else:
        resp.json = MagicMock(return_value=json_body)
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    return client


FAILURES = [
    pytest.param(_raising_client, id="transport"),
    # A throttled reply often still carries a JSON body; reading it as an answer
    # is exactly how a rate limit became "no records" for a month.
    pytest.param(lambda: _status_client(429, {"message": "Too Many Requests"}), id="429"),
    pytest.param(lambda: _status_client(500, json_error=True), id="500"),
    pytest.param(lambda: _status_client(200, json_error=True), id="unparseable"),
]


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    # Each case gets its own limiter (geocode's bucket holds one token) and a
    # cold KEV catalog, so cases cannot throttle or satisfy one another.
    monkeypatch.setattr(service_mod, "_RATE_LIMITER", RateLimiter(), raising=False)
    kev._reset_catalog()
    # geoip consults the egress mode before looking anything up; direct here.
    monkeypatch.setattr(geoip, "_egress_mode", AsyncMock(return_value="direct"), raising=False)
    yield
    kev._reset_catalog()


@pytest.mark.parametrize("make_client", FAILURES)
@pytest.mark.parametrize("module,provider_cls,entity_type,name", PROVIDERS)
async def test_lookup_raises_provider_error(module, provider_cls, entity_type, name, make_client):
    provider = provider_cls(client=make_client())
    with pytest.raises(ProviderError) as info:
        await provider.lookup(name, entity_type)
    assert info.value.provider == provider_cls.name
    assert info.value.reason  # a short, client-safe reason


@pytest.mark.parametrize("make_client", FAILURES)
@pytest.mark.parametrize("module,provider_cls,entity_type,name", PROVIDERS)
async def test_service_neither_caches_nor_writes_a_failed_lookup(
    monkeypatch, module, provider_cls, entity_type, name, make_client,
):
    client = make_client()
    monkeypatch.setattr(module, "ProxiedClient", lambda *a, **k: client)

    entity = {"id": "e1", "name": name, "entity_type": entity_type, "project_id": tp("e1")}
    store = MagicMock()
    store.get_entity = MagicMock(return_value=entity)
    store.update_entity = MagicMock(return_value=entity)
    cache = MagicMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    writer = MagicMock()

    svc = EnrichmentService(store, write_related=writer, cache=cache)
    out = await svc.enrich_entity("e1", only={provider_cls.name})

    result = out["providers"][provider_cls.name]
    assert result["status"] == "error"
    assert result["reason"]
    assert "properties" not in result
    cache.set.assert_not_awaited()
    store.update_entity.assert_not_called()
    writer.assert_not_called()


def test_provider_error_carries_provider_and_reason():
    err = ProviderError("dns", "http 503")
    assert err.provider == "dns"
    assert err.reason == "http 503"
    assert isinstance(err, RuntimeError)
