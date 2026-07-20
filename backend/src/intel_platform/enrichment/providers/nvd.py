"""CVE detail via the NVD CVE API 2.0 (keyless; optional key raises the quota).

Populates ``Vulnerability.cvss_score`` / severity / description /
affected_products for a CVE id. Keyless the API allows ~5 requests / 30s, so
the rate limiter is conservative.
"""
from __future__ import annotations

from datetime import timedelta

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.config import settings
from intel_platform.enrichment.base import (
    EnrichmentProvider,
    EnrichmentResult,
    register_provider,
)

_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_MAX_PRODUCTS = 25


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
        headers = {"apiKey": settings.nvd_api_key} if settings.nvd_api_key else None
        try:
            resp = await self._client.get(_URL, params={"cveId": value}, headers=headers, timeout=20)
            data = resp.json()
        except Exception:
            return EnrichmentResult(source_url=_URL)

        if not isinstance(data, dict):
            return EnrichmentResult(source_url=_URL)
        vulns = data.get("vulnerabilities") or []
        if not vulns:
            return EnrichmentResult(raw=data, source_url=_URL)

        cve = vulns[0].get("cve", {})
        descriptions = cve.get("descriptions", []) or []
        description = next(
            (d.get("value", "") for d in descriptions if d.get("lang") == "en"),
            descriptions[0].get("value", "") if descriptions else "",
        )
        score, severity = _first_cvss(cve.get("metrics", {}) or {})
        products = _products(cve.get("configurations", []) or [])

        props: dict = {"cve_id": value, "description": description}
        if score is not None:
            props["cvss_score"] = score
        if severity:
            props["severity"] = severity.lower()
        if products:
            props["affected_products"] = products

        return EnrichmentResult(properties=props, raw=cve, source_url=f"{_URL}?cveId={value}")
