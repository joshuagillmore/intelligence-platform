"""Merging one entity into another, moving every edge as it was.

Shared by the analyst's merge route (`POST /entities/merge`) and the startup
backfill that folds together entities which turn out to share a
(project_id, normalized_name, entity_type) key. Both must leave the graph in
the same shape, so there is one implementation.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable

from intel_platform.graph.store import GraphStore

logger = logging.getLogger(__name__)

# Keys `get_relationships` adds about the endpoints; everything else on a
# relationship row is a property of the edge itself.
REL_ENDPOINT_KEYS = frozenset({
    "rel_type", "source_id", "target_id", "source_name", "target_name", "direction",
    "neighbor_id", "neighbor_name",
})
# A relationship type as Neo4j stores it. Checked before a type read from the
# graph is handed to APOC, although it came from the graph and not a request.
_REL_TYPE_SHAPE = re.compile(r"[A-Z][A-Z0-9_]*")


def copy_edge_verbatim(store: GraphStore, rel_type: str, props: dict, source_id: str, target_id: str) -> bool:
    """Recreate an edge with its exact type and properties. False if nothing was created."""
    if not _REL_TYPE_SHAPE.fullmatch(rel_type or ""):
        return False
    with store._driver.session() as session:
        record = session.run(
            """
            MATCH (a {id: $source_id})
            MATCH (b {id: $target_id})
            CALL apoc.create.relationship(a, $rel_type, $props, b) YIELD rel
            RETURN count(rel) AS created
            """,
            source_id=source_id, target_id=target_id, rel_type=rel_type,
            props=store._serialize_props(props),
        ).single()
    return bool(record and record["created"])


def transfer_edge(store: GraphStore, rel: dict, source_id: str, target_id: str, project_id: str) -> bool:
    """Recreate one edge between new endpoints, keeping its type and properties.

    Allowlisted types go through `create_relationship`, so an edge the primary
    already has is corroborated rather than duplicated. Types outside that
    allowlist — the ATT&CK/CWE catalog edges (MAPS_TO, HAS_WEAKNESS, ENABLES) —
    are copied verbatim: the allowlist guards types arriving from requests and
    model output, and this type is already in the graph. A property the model
    will not accept also falls back to the verbatim copy, so a merge is never
    refused over one odd value.
    """
    from pydantic import ValidationError

    from intel_platform.models.relationships import Relationship

    rel_type = rel.get("rel_type", "")
    props = {k: v for k, v in rel.items() if k not in REL_ENDPOINT_KEYS}
    if rel_type in store.VALID_REL_TYPES:
        # project_id is passed explicitly: an edge the store wrote carries it
        # as a property too, and passing it twice was a TypeError that no
        # except clause caught, so merging any project-stamped edge failed.
        fields = {k: v for k, v in props.items() if k in Relationship.model_fields and k != "project_id"}
        try:
            created = store.create_relationship(Relationship(
                source_id=source_id, target_id=target_id, rel_type=rel_type,
                project_id=project_id, **fields,
            ))
            if created:
                return True
        except (ValueError, ValidationError):
            logger.warning("Merge: %s edge did not fit the model; copying it verbatim", rel_type, exc_info=True)
    try:
        return copy_edge_verbatim(store, rel_type, props, source_id, target_id)
    except Exception:
        logger.exception("Merge: could not recreate a %s edge %s -> %s", rel_type, source_id, target_id)
        return False


@dataclass
class MergeOutcome:
    transferred: int = 0
    failed: int = 0
    deleted: bool = False


def merge_entity_into(
    store: GraphStore, primary_id: str, merge_id: str, *, project_id: str,
    skip_ids: frozenset[str] | set[str] = frozenset(),
    transfer: Callable[[GraphStore, dict, str, str, str], bool] = transfer_edge,
) -> MergeOutcome:
    """Move `merge_id`'s edges, mentions and sources onto `primary_id`, then delete it.

    Each edge keeps its direction, type and properties (evidence, provenance,
    polarity). An edge to the primary, or to another entity in `skip_ids`
    (being merged into it in the same operation), is dropped rather than
    turned into a self-loop. The documents that mention the merged entity
    (MENTIONS edges and `source_doc_ids`) move to the primary. The entity is
    deleted only once every edge has been recreated; otherwise it is kept and
    the outcome says how many could not be moved — deleting it anyway is how
    edges used to disappear behind a success message.

    `transfer` is injectable so the route's own `_transfer_edge` stays the
    seam its tests patch.
    """
    outcome = MergeOutcome()
    for rel in store.get_relationships(merge_id):
        if "direction" in rel:
            outgoing = rel["direction"] == "out"
        else:
            outgoing = rel.get("source_id") == merge_id
        other = rel.get("target_id") if outgoing else rel.get("source_id")
        if other == primary_id or other in skip_ids:
            continue
        source_id, target_id = (primary_id, other) if outgoing else (other, primary_id)
        if transfer(store, rel, source_id, target_id, project_id):
            outcome.transferred += 1
        else:
            outcome.failed += 1

    if outcome.failed:
        logger.warning("Merge: kept %s; %d of its edges could not be moved", merge_id, outcome.failed)
        return outcome
    store.move_mentions(merge_id, primary_id)
    store.delete_entity(merge_id)
    outcome.deleted = True
    return outcome
