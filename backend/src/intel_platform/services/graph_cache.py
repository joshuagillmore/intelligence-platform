"""In-memory cache for computed NetworkX graphs and algorithm results per project.

Avoids rebuilding the full NetworkX graph on every algorithm call.
Cache is invalidated when entities or relationships are created/updated/deleted.

The graph slot is reserved for the analytics build: `services.enrichment.
_build_networkx_graph`, which reads `GraphStore.get_full_graph(limit=10000)`.
Centrality, communities, statistics, structural holes and ego networks all
read the cached graph expecting that build. Nothing else may store a graph
here — `GET /graph` once cached its display graph (default limit 500, any
limit a caller asked for) under the same project key, so `/graph?limit=1`
silently reduced every analytic to one node for the TTL. A display graph is
built fresh from `get_full_graph`, or cached somewhere keyed by its limit.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import networkx as nx

DEFAULT_GRAPH_TTL = 300  # seconds
DEFAULT_METRICS_TTL = 300  # seconds


class GraphCache:
    """Simple in-memory cache for NetworkX graphs and computed metrics.

    Stores one DiGraph per project_id plus arbitrary metric results keyed
    by ``(project_id, metric_name)``.  Each entry has an independent TTL.
    """

    def __init__(
        self,
        graph_ttl: int = DEFAULT_GRAPH_TTL,
        metrics_ttl: int = DEFAULT_METRICS_TTL,
    ):
        self._graph_ttl = graph_ttl
        self._metrics_ttl = metrics_ttl
        # {project_id: (timestamp, nx.DiGraph)}
        self._graphs: dict[str, tuple[float, nx.DiGraph]] = {}
        # {(project_id, metric_name): (timestamp, Any)}
        self._metrics: dict[tuple[str, str], tuple[float, Any]] = {}

    # ------------------------------------------------------------------
    # Graph cache
    # ------------------------------------------------------------------

    def get_or_build_graph(
        self,
        project_id: str,
        builder_fn: Callable[[], nx.DiGraph],
    ) -> nx.DiGraph:
        """Return cached graph or call *builder_fn* to build and cache it.

        Only the analytics build may call this (see the module docstring):
        the key is the project alone, so whatever is cached is what every
        analytic reads.
        """
        now = time.time()
        if project_id in self._graphs:
            cached_time, graph = self._graphs[project_id]
            if now - cached_time < self._graph_ttl:
                return graph

        graph = builder_fn()
        self._graphs[project_id] = (now, graph)
        return graph

    # ------------------------------------------------------------------
    # Metrics cache
    # ------------------------------------------------------------------

    def get_metric(self, project_id: str, metric_name: str) -> Any | None:
        """Return cached metric value or ``None`` if missing / expired."""
        key = (project_id, metric_name)
        if key in self._metrics:
            cached_time, value = self._metrics[key]
            if time.time() - cached_time < self._metrics_ttl:
                return value
            del self._metrics[key]
        return None

    def set_metric(self, project_id: str, metric_name: str, value: Any) -> None:
        """Store a metric value in the cache."""
        self._metrics[(project_id, metric_name)] = (time.time(), value)

    # ------------------------------------------------------------------
    # Invalidation
    # ------------------------------------------------------------------

    def invalidate(self, project_id: str) -> None:
        """Clear all cached data (graph + metrics) for *project_id*."""
        self._graphs.pop(project_id, None)
        keys_to_remove = [k for k in self._metrics if k[0] == project_id]
        for key in keys_to_remove:
            del self._metrics[key]

    def clear(self) -> None:
        """Clear the entire cache (useful in tests)."""
        self._graphs.clear()
        self._metrics.clear()


# Module-level singleton — import and use directly.
graph_cache = GraphCache()
