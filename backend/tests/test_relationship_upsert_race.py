"""Concurrent assertions of one claim make one edge and lose no source.

`create_relationship` looked for an existing edge in one query and created or
updated it in another. Two builds asserting the same claim at once — the
agentic loop ingests sources concurrently — could both see "no edge" and both
create one, or both read the same corroboration list and each write back its
own, losing the other's source. (Review, Low → G: check-then-create races.)
"""
from __future__ import annotations

import threading

from intel_platform.models.entities import Organization
from intel_platform.models.relationships import Relationship

PROJECT = "test-upsert-race"
WORKERS = 12


def test_concurrent_assertions_make_one_edge_with_every_source(graph_store):
    a = Organization(name="Race Actor", project_id=PROJECT)
    b = Organization(name="Race Target", project_id=PROJECT)
    graph_store.create_entity(a)
    graph_store.create_entity(b)

    barrier = threading.Barrier(WORKERS)
    errors: list[BaseException] = []

    def assert_claim(i: int) -> None:
        barrier.wait()
        try:
            graph_store.create_relationship(Relationship(
                source_id=a.id, target_id=b.id, rel_type="TARGETS",
                source_doc_id=f"doc-{i}", project_id=PROJECT,
            ))
        except BaseException as exc:  # noqa: BLE001 — surfaced by the assert below
            errors.append(exc)

    threads = [threading.Thread(target=assert_claim, args=(i,)) for i in range(WORKERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    edges = [r for r in graph_store.get_relationships(a.id) if r["target_id"] == b.id]
    assert len(edges) == 1, f"{len(edges)} edges for one claim"
    assert sorted(edges[0]["corroboration_sources"]) == sorted(f"doc-{i}" for i in range(WORKERS))
    assert edges[0]["corroboration_count"] == WORKERS
