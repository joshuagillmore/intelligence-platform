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

    # --- Capability metadata -------------------------------------------------
    # What this connector can actually reach, declared next to the code that
    # does the reaching. The collection planner is prompted from this rather
    # than from a hand-maintained list, because the two drifted: the planner
    # was offering source types with rules of thumb about when to choose them
    # and nothing about what the system can obtain, so it proposed a Twitter
    # API feed and a "weekly report" upload as if both were collection the
    # system would perform.

    #: Config keys the planner must supply for this type to be executable.
    config_keys: tuple[str, ...] = ()
    #: False when producing data needs a person — the planner should propose
    #: these only as an explicit request to the analyst, never as collection.
    unattended: bool = True
    #: Written for the planner: what this type can and cannot reach.
    capability_note: str = ""

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


def unattended_source_types() -> list[str]:
    """Types the system can collect without a person doing something first."""
    return sorted(t for t, c in CONNECTOR_REGISTRY.items() if c.unattended)


def describe_collection_capabilities() -> str:
    """What this deployment can actually collect, written for the planner.

    Derived from the connector registry so it cannot drift from the code. It
    drifted twice already: the planning skill's system prompt and the prompt
    built at the call site listed different type sets (one had `database`, the
    other did not) and disagreed about config keys, and neither said anything
    about what the connectors can reach. A planner told only that `api_feed`
    means "structured data APIs" will propose a Twitter API feed, which this
    system has no way to authenticate to.
    """
    lines: list[str] = []
    for source_type in sorted(CONNECTOR_REGISTRY):
        cls = CONNECTOR_REGISTRY[source_type]
        if cls.config_keys:
            keys = ", ".join(f'"{k}": "..."' for k in cls.config_keys)
            config = f'CONFIG must include {{{keys}}}'
        else:
            config = "no CONFIG"
        marker = "" if cls.unattended else "  [ANALYST ACTION, NOT COLLECTION]"
        lines.append(f"- {source_type}: {config}{marker}")
        if cls.capability_note:
            lines.append(f"    {cls.capability_note}")
    return "\n".join(lines)


def get_connector(source_type: str) -> SourceConnector:
    """Instantiate a connector by source type."""
    cls = CONNECTOR_REGISTRY.get(source_type)
    if cls is None:
        raise ValueError(f"Unknown source type: {source_type}. Available: {list(CONNECTOR_REGISTRY.keys())}")
    return cls()
