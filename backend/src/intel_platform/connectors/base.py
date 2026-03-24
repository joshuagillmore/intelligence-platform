"""Base connector interface — all source connectors implement this contract.

Adding a new source type requires:
1. Subclass SourceConnector
2. Implement configure(), test(), acquire(), normalize()
3. Register in CONNECTOR_REGISTRY
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ConnectorHealth(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class AcquireResult:
    """Result returned by a connector's acquire() method."""
    success: bool
    record_count: int = 0
    records: list[dict] = field(default_factory=list)
    raw_data: bytes | None = None
    error: str = ""
    metadata: dict = field(default_factory=dict)
    # Profiling info for structured data
    schema_info: dict = field(default_factory=dict)
    profiling: dict = field(default_factory=dict)
    preview_rows: list[dict] = field(default_factory=list)


@dataclass
class HealthStatus:
    status: ConnectorHealth
    last_success: datetime | None = None
    last_failure: datetime | None = None
    last_error: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SourceConnector(abc.ABC):
    """Base interface for all source connectors."""

    # Subclasses set this
    source_type: str = ""

    @abc.abstractmethod
    def configure(self, config: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize configuration. Returns validated config.

        Raises ValueError on invalid configuration.
        """

    @abc.abstractmethod
    async def test(self, config: dict[str, Any]) -> HealthStatus:
        """Test connectivity / readability with the given config."""

    async def discover(self, config: dict[str, Any]) -> dict[str, Any]:
        """Optional: discover schema/metadata about the source.

        Default: returns empty dict. Override for sources that support
        schema browsing (databases, structured files).
        """
        return {}

    @abc.abstractmethod
    async def acquire(self, config: dict[str, Any], since: datetime | None = None) -> AcquireResult:
        """Fetch data from the source. `since` enables incremental collection."""

    def normalize(self, result: AcquireResult) -> list[dict]:
        """Transform raw acquisition result into platform common format.

        Default: returns result.records as-is. Override for sources
        that need format-specific normalization.
        """
        return result.records

    async def health_check(self, config: dict[str, Any]) -> HealthStatus:
        """Check if the source is reachable and functioning."""
        return await self.test(config)


# ---------------------------------------------------------------------------
# Connector registry — maps source_type strings to connector classes
# ---------------------------------------------------------------------------

CONNECTOR_REGISTRY: dict[str, type[SourceConnector]] = {}


def register_connector(cls: type[SourceConnector]) -> type[SourceConnector]:
    """Decorator to register a connector class."""
    if cls.source_type:
        CONNECTOR_REGISTRY[cls.source_type] = cls
    return cls


def get_connector(source_type: str) -> SourceConnector:
    """Instantiate a connector by source type."""
    cls = CONNECTOR_REGISTRY.get(source_type)
    if cls is None:
        raise ValueError(f"Unknown source type: {source_type}. Available: {list(CONNECTOR_REGISTRY.keys())}")
    return cls()
