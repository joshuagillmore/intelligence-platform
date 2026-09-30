"""CVE detail via the NVD CVE API 2.0 (keyless; optional key raises the quota).

Populates ``Vulnerability.cvss_score`` / severity / description /
affected_products for a CVE id. Keyless the API allows ~5 requests / 30s, so
the rate limiter is conservative.
"""
from __future__ import annotations

import re
from datetime import timedelta

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.config import settings
from intel_platform.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
    ProviderError,
    fetch_json,
    register_provider,
)
from intel_platform.enrichment.observables import cve_id

_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_MAX_PRODUCTS = 25
_CWE_RE = re.compile(r"^CWE-\d+$")


def _cwe_ids(weaknesses: list) -> list[str]:
    """CWE ids from NVD's ``cve.weaknesses[]``, Primary first, deduped.

    Each weakness is ``{"type": "Primary"|"Secondary", "description":
    [{"lang": "en", "value": "CWE-79"}, ...]}``. NVD also emits non-CWE markers
    like ``NVD-CWE-noinfo``/``NVD-CWE-Other``; those don't match ``^CWE-\\d+$``
    and are dropped. Primary mappings are surfaced ahead of Secondary ones.
    """
    primary: list[str] = []
    secondary: list[str] = []
    seen: set[str] = set()
    for weakness in weaknesses or []:
        bucket = primary if weakness.get("type") == "Primary" else secondary
        for desc in weakness.get("description", []) or []:
            value = desc.get("value", "")
            if _CWE_RE.match(value) and value not in seen:
                seen.add(value)
                bucket.append(value)
    return primary + secondary


def _first_cvss(metrics: dict) -> tuple[float | None, str]:
    """Return (base_score, base_severity) from the best available CVSS metric."""
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key) or []
        if entries:
            data = entries[0].get("cvssData", {})
            score = data.get("baseScore")
            severity = data.get("baseSeverity") or entries[0].get("baseSeverity", "")
            return score, severity
    return None, ""


def _products(configurations: list) -> list[str]:
    products: list[str] = []
    seen = set()
    for cfg in configurations or []:
        for node in cfg.get("nodes", []) or []:
            for match in node.get("cpeMatch", []) or []:
                criteria = match.get("criteria", "")
                parts = criteria.split(":")
                # cpe:2.3:a:vendor:product:version:...
                if len(parts) >= 5:
                    label = f"{parts[3]} {parts[4]}".replace("_", " ").strip()
                    if label and label not in seen:
                        seen.add(label)
                        products.append(label)
    return products[:_MAX_PRODUCTS]


@register_provider
class NVDProvider(EnrichmentProvider):
    name = "nvd"
    supported_types = {"Vulnerability"}
    auto = False
    cache_ttl = timedelta(days=7)
    rate = 0.15         # ~4.5 / 30s, under the keyless cap
    capacity = 5.0

    def __init__(self, client: ProxiedClient | None = None):
        self._client = client or ProxiedClient()

    async def lookup(self, value: str, entity_type: str) -> EnrichmentResult:
        value = cve_id(value)
        if not value:
            return EnrichmentResult(skipped="no CVE id")
        headers = {"apiKey": settings.nvd_api_key} if settings.nvd_api_key else None
        data = await fetch_json(
            self._client, self.name, _URL, params={"cveId": value}, headers=headers, timeout=20,
        )
        vulns = data.get("vulnerabilities") if isinstance(data, dict) else None
        if not isinstance(vulns, list):
            raise ProviderError(self.name, "unexpected response shape")
        if not vulns:
            # NVD answered and has no record of this id.
            return EnrichmentResult(raw=data, source_url=_URL)

        cve = vulns[0].get("cve", {})
        descriptions = cve.get("descriptions", []) or []
        description = next(
            (d.get("value", "") for d in descriptions if d.get("lang") == "en"),
            descriptions[0].get("value", "") if descriptions else "",
        )
        score, severity = _first_cvss(cve.get("metrics", {}) or {})
        products = _products(cve.get("configurations", []) or [])
        cwe_ids = _cwe_ids(cve.get("weaknesses", []) or [])

        props: dict = {"cve_id": value, "description": description}
        if score is not None:
            props["cvss_score"] = score
        if severity:
            # NVD's own key; the service derives the node's `severity` from this
            # and KEV's `kev_severity`, so neither overwrites the other.
            props["cvss_severity"] = severity.lower()
        if products:
            props["affected_products"] = products
        if cwe_ids:
            props["cwe_ids"] = cwe_ids

        return EnrichmentResult(properties=props, raw=cve, source_url=f"{_URL}?cveId={value}")
