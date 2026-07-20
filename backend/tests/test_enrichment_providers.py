"""Fixture-based tests for the free/keyless enrichment providers.

Every HTTP call is mocked — no network. Each test asserts the provider maps a
representative API payload to the right properties/edges.
"""
import json
from unittest.mock import AsyncMock, MagicMock

from intel_platform.enrichment.providers.certs import CertsProvider
from intel_platform.enrichment.providers.dns import DNSProvider
from intel_platform.enrichment.providers.geoip import GeoIPProvider
from intel_platform.enrichment.providers.kev import KEVProvider, _reset_catalog
from intel_platform.enrichment.providers.nvd import NVDProvider
from intel_platform.enrichment.providers.rdap import RDAPProvider


def _resp(payload):
    resp = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def _client(get_impl):
    client = MagicMock()
    client.get = AsyncMock(side_effect=get_impl)
    return client


# --- DNS --------------------------------------------------------------------

async def test_dns_records_and_resolves_to_edges():
    async def get(url, params=None, headers=None, timeout=10):
        if params["type"] == "A":
            return _resp({"Answer": [{"name": "evil.com", "type": 1, "data": "1.2.3.4"}]})
        return _resp({"Answer": []})

    result = await DNSProvider(client=_client(get)).lookup("evil.com", "Domain")
    assert json.loads(result.properties["dns_records"])["A"] == ["1.2.3.4"]
    assert any(r.rel_type == "RESOLVES_TO" and r.name == "1.2.3.4" for r in result.related)


# --- GeoIP ------------------------------------------------------------------

async def test_geoip_populates_asn_and_geolocation():
    async def get(url, params=None, timeout=10):
        return _resp({
            "status": "success", "country": "United States", "countryCode": "US",
            "regionName": "California", "city": "Mountain View", "lat": 37.4,
            "lon": -122.0, "org": "Google LLC", "as": "AS15169 Google LLC",
            "query": "8.8.8.8",
        })

    result = await GeoIPProvider(client=_client(get)).lookup("8.8.8.8", "IPAddress")
    assert result.properties["asn"] == "AS15169 Google LLC"
    geo = json.loads(result.properties["geolocation"])
    assert geo["city"] == "Mountain View" and geo["country_code"] == "US"


async def test_geoip_handles_failure_status():
    async def get(url, params=None, timeout=10):
        return _resp({"status": "fail", "message": "reserved range", "query": "10.0.0.1"})

    result = await GeoIPProvider(client=_client(get)).lookup("10.0.0.1", "IPAddress")
    assert result.properties == {}


# --- KEV --------------------------------------------------------------------

async def test_kev_hit_marks_known_exploited():
    _reset_catalog()

    async def get(url, timeout=30):
        return _resp({"vulnerabilities": [{"cveID": "CVE-2021-44228", "dateAdded": "2021-12-10"}]})

    result = await KEVProvider(client=_client(get)).lookup("CVE-2021-44228", "Vulnerability")
    assert result.properties["known_exploited"] is True
    assert result.properties["severity"] == "critical"
    assert result.properties["kev_date_added"] == "2021-12-10"


async def test_kev_miss_marks_not_exploited():
    _reset_catalog()

    async def get(url, timeout=30):
        return _resp({"vulnerabilities": [{"cveID": "CVE-2000-0001", "dateAdded": "2000-01-01"}]})

    result = await KEVProvider(client=_client(get)).lookup("CVE-2021-44228", "Vulnerability")
    assert result.properties["known_exploited"] is False


# --- NVD --------------------------------------------------------------------

async def test_nvd_extracts_cvss_description_products():
    async def get(url, params=None, timeout=20):
        return _resp({"vulnerabilities": [{"cve": {
            "id": "CVE-2021-44228",
            "descriptions": [{"lang": "en", "value": "Log4j RCE"}],
            "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 10.0, "baseSeverity": "CRITICAL"}}]},
            "configurations": [{"nodes": [{"cpeMatch": [
                {"criteria": "cpe:2.3:a:apache:log4j:2.0:*:*:*:*:*:*:*"}
            ]}]}],
        }}]})

    result = await NVDProvider(client=_client(get)).lookup("CVE-2021-44228", "Vulnerability")
    assert result.properties["cvss_score"] == 10.0
    assert result.properties["severity"] == "critical"
    assert result.properties["description"] == "Log4j RCE"
    assert "apache log4j" in result.properties["affected_products"]


# --- RDAP -------------------------------------------------------------------

async def test_rdap_domain_extracts_registrar_and_date():
    async def get(url, timeout=15):
        return _resp({
            "events": [{"eventAction": "registration", "eventDate": "1997-09-15T00:00:00Z"}],
            "entities": [{
                "roles": ["registrar"],
                "vcardArray": ["vcard", [["fn", {}, "text", "MarkMonitor Inc."]]],
            }],
        })

    result = await RDAPProvider(client=_client(get)).lookup("google.com", "Domain")
    assert result.properties["registrar"] == "MarkMonitor Inc."
    assert result.properties["registration_date"].startswith("1997-09-15")


# --- Certs ------------------------------------------------------------------

async def test_certs_summary_and_siblings():
    async def get(url, params=None, timeout=20):
        return _resp([
            {"issuer_name": "C=US, O=Let's Encrypt, CN=R3", "name_value": "evil.com\nwww.evil.com"},
            {"issuer_name": "C=US, O=Let's Encrypt, CN=R3", "name_value": "mail.evil.com"},
        ])

    result = await CertsProvider(client=_client(get)).lookup("evil.com", "Domain")
    assert result.properties["cert_san_count"] >= 3
    assert "C=US, O=Let's Encrypt, CN=R3" in result.properties["cert_issuers"]
    siblings = [r.name for r in result.related]
    assert "www.evil.com" in siblings and "mail.evil.com" in siblings
    assert "evil.com" not in siblings  # the queried domain isn't its own sibling
