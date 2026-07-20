"""EnrichmentProvider contract + registry.

Mirrors ``collection.connectors.base``: a provider subclass declares which
observable types it handles and how fresh its data stays, implements one async
``lookup`` returning an ``EnrichmentResult``, and registers itself. The service
(``enrichment.service``) discovers providers by entity type via the registry.

Adding a provider requires:
1. Subclass ``EnrichmentProvider`` (set name/supported_types/cache_ttl/etc.)
2. Implement ``lookup(value, entity_type)``
3. ``@register_provider`` (or call ``register_provider`` on the class)
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import timedelta


@dataclass
class RelatedEntity:
    """A node (+ typed edge) an enrichment lookup discovered.

    ``direction`` "out" means ``(observable)-[rel_type]->(related)``; "in"
    reverses it. e.g. a DNS A record → RelatedEntity(name=ip, entity_type=
    "IPAddress", rel_type="RESOLVES_TO", direction="out").
    """
    name: str
    entity_type: str
    rel_type: str
    direction: str = "out"
    properties: dict = field(default_factory=dict)


@dataclass
class EnrichmentResult:
    """What a provider returns for one observable."""
    properties: dict = field(default_factory=dict)      # merged onto the node
    related: list[RelatedEntity] = field(default_factory=list)  # new nodes + edges
    raw: dict = field(default_factory=dict)             # audit payload (cached)
    source_url: str = ""                                # evidence for writes


class EnrichmentProvider(abc.ABC):
    """Base contract for a cyber-observable enrichment source."""

    name: str = ""                       # registry key, e.g. "rdap"
    supported_types: set[str] = frozenset()  # {"IPAddress", "Domain", ...}
    requires_key: bool = False           # needs an API key to run
    cache_ttl: timedelta = timedelta(days=1)  # per-provider freshness window
    auto: bool = False                   # runs in the selective auto-enrich pass
    rate: float = 1.0                    # rate-limiter tokens per second
    capacity: float = 5.0                # rate-limiter burst capacity

    @abc.abstractmethod
    async def lookup(self, value: str, entity_type: str) -> EnrichmentResult:
        """Look up one observable and return its enrichment."""


# ---------------------------------------------------------------------------
# Provider registry — maps provider name -> provider class
# ---------------------------------------------------------------------------

PROVIDER_REGISTRY: dict[str, type[EnrichmentProvider]] = {}


def register_provider(cls: type[EnrichmentProvider]) -> type[EnrichmentProvider]:
    """Register a provider class (decorator or direct call)."""
    if cls.name:
        PROVIDER_REGISTRY[cls.name] = cls
    return cls


def get_providers_for(
    entity_type: str, available_keys: frozenset[str] | set[str] = frozenset()
) -> list[EnrichmentProvider]:
    """Instantiate every registered provider eligible for ``entity_type``.

    A provider is eligible if it supports the type and either needs no key or
    has one present in ``available_keys``.
    """
    providers: list[EnrichmentProvider] = []
    for cls in PROVIDER_REGISTRY.values():
        if entity_type not in cls.supported_types:
            continue
        if cls.requires_key and cls.name not in available_keys:
            continue
        providers.append(cls())
    return providers
