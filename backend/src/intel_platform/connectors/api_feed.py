"""API feed connector — fetches structured data from HTTP APIs.

Supports JSON APIs with configurable auth, pagination, and response
path traversal for extracting records from nested responses.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from intel_platform.collection.proxy import ProxiedClient
from intel_platform.connectors.base import (
    AcquireResult,
    ConnectorHealth,
    HealthStatus,
    SourceConnector,
    register_connector,
)

logger = logging.getLogger(__name__)


@register_connector
class APIFeedConnector(SourceConnector):
    """Fetch structured data from HTTP JSON APIs."""

    source_type = "api_feed"
    config_keys = ("base_url",)
    capability_note = (
        "Fetches public JSON over HTTP. There is no credential store, so anything "
        "requiring a key, token, OAuth or a paid plan CANNOT be collected — do not "
        "propose Twitter/X, Meta, LinkedIn or similar commercial APIs."
    )

    def configure(self, config: dict) -> dict:
        base_url = config.get("base_url", "").strip()
        if not base_url:
            raise ValueError("'base_url' is required for api_feed sources")
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"API URL must use http or https, got: {parsed.scheme}")

        auth_type = config.get("auth_type", "none")
        if auth_type not in ("none", "bearer", "api_key"):
            raise ValueError(f"auth_type must be none, bearer, or api_key, got: {auth_type}")

        return {
            "base_url": base_url.rstrip("/"),
            "endpoint": config.get("endpoint", "").strip().lstrip("/"),
            "method": config.get("method", "GET").upper(),
            "headers": config.get("headers", {}),
            "auth_type": auth_type,
            "auth_value": config.get("auth_value", ""),
            "response_path": config.get("response_path", ""),
            "params": config.get("params", {}),
            "timeout": float(config.get("timeout", 30)),
        }

    async def test(self, config: dict) -> HealthStatus:
        try:
            url = self._build_url(config)
            headers = self._build_headers(config)
            client = ProxiedClient()
            resp = await client.get(url, timeout=10, headers=headers)
            if resp.status_code < 400:
                return HealthStatus(status=ConnectorHealth.HEALTHY)
            return HealthStatus(status=ConnectorHealth.DEGRADED, last_error=f"HTTP {resp.status_code}")
        except Exception as e:
            return HealthStatus(status=ConnectorHealth.UNHEALTHY, last_error=str(e))

    async def acquire(self, config: dict, since: datetime | None = None) -> AcquireResult:
        url = self._build_url(config)
        if not url:
            return AcquireResult(success=False, error="No API URL configured")

        headers = self._build_headers(config)
        timeout = config.get("timeout", 30)

        try:
            client = ProxiedClient()
            resp = await client.get(url, timeout=timeout, headers=headers)
            resp.raise_for_status()

            try:
                data = resp.json()
            except json.JSONDecodeError:
                # If not JSON, treat as text
                return AcquireResult(
                    success=True, record_count=1,
                    records=[{"content": resp.text, "source_url": url}],
                    metadata={"source_url": url},
                )

            # Navigate response_path to extract records
            response_path = config.get("response_path", "")
            records_data = self._navigate_path(data, response_path)

            # Normalize to list of dicts
            if isinstance(records_data, list):
                records = [r if isinstance(r, dict) else {"value": r} for r in records_data]
            elif isinstance(records_data, dict):
                records = [records_data]
            else:
                records = [{"value": records_data}]

            # Add source metadata to each record
            for r in records:
                r.setdefault("_source_url", url)
                r.setdefault("_acquired_at", datetime.now(timezone.utc).isoformat())

            return AcquireResult(
                success=True,
                record_count=len(records),
                records=records,
                metadata={"source_url": url, "response_path": response_path},
            )
        except Exception as e:
            return AcquireResult(success=False, error=str(e), metadata={"source_url": url})

    @staticmethod
    def _build_url(config: dict) -> str:
        base = config.get("base_url", "")
        endpoint = config.get("endpoint", "")
        if endpoint:
            return f"{base}/{endpoint}"
        return base

    @staticmethod
    def _build_headers(config: dict) -> dict:
        headers = dict(config.get("headers", {}))
        auth_type = config.get("auth_type", "none")
        auth_value = config.get("auth_value", "")

        if auth_type == "bearer" and auth_value:
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_type == "api_key" and auth_value:
            headers["X-API-Key"] = auth_value

        headers.setdefault("Accept", "application/json")
        return headers

    @staticmethod
    def _navigate_path(data, path: str):
        """Navigate a dot-notation path into a nested dict/list."""
        if not path:
            return data
        for key in path.split("."):
            if isinstance(data, dict):
                data = data.get(key, data)
            elif isinstance(data, list) and key.isdigit():
                idx = int(key)
                data = data[idx] if idx < len(data) else data
            else:
                break
        return data
