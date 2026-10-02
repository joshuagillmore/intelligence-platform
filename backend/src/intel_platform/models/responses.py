"""Response models: the JSON each API route declares it returns.

Every route names one of these (or a model local to its router) as its
``response_model``, so the OpenAPI schema, and the frontend types generated
from it, describe what the route actually sends. A model here declares what a
route already returns; it never reshapes it:

- A key a route sometimes leaves out is ``Optional`` with a ``None`` default.
- A value read from a schemaless Neo4j property is typed as loosely as the
  route treats it (``str | None`` where the route passes a missing property
  through), so an old or hand-written node cannot turn a read into a 500.
- ``extra="allow"`` is used only where the route returns an open-ended map
  (a node's stored properties, an enrichment payload, a service's growing
  stats), and each such model says so in its docstring.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    classification_level: str
    priority: str
    status: str
    entity_count: int = 0
    relationship_count: int = 0
    document_count: int = 0
    collection_count: int = 0
    created_at: str = ""
    updated_at: str = ""


class PirPlanLink(BaseModel):
    """A collection plan raised against a PIR — the next link in the cycle."""
    id: str
    name: str
    status: str
    source_count: int = 0
    records_acquired: int = 0
    created_at: str = ""


class PirResponse(BaseModel):
    id: str
    project_id: str
    title: str = ""
    text: str = ""
    refined_text: str = ""
    eeis: list[str] = []
    priority: str = "medium"
    status: str = "OPEN"
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""
    plan_count: int = 0
    plans: list[PirPlanLink] = []


class EntityResponse(BaseModel):
    id: str
    name: str
    entity_type: str
    properties: dict = {}
    confidence: float = 0.0
    corroboration_count: int = 0


class GraphResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]
    node_count: int
    edge_count: int


class HealthResponse(BaseModel):
    status: str
    neo4j_connected: bool
    ollama_connected: bool = False
    version: str = "0.1.0"
    # "ok", or the reason embeddings cannot be stored (vector column width
    # differs from EMBEDDING_DIMENSIONS). Not part of `status`: graph-only
    # retrieval still works, but an operator must be able to see it.
    embeddings: str = "ok"


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class StatusResponse(BaseModel):
    """A bare outcome: ``{"status": "deleted"}``, ``"ok"``, ``"logged_out"`` and the like."""
    status: str


class DeletedResponse(BaseModel):
    """A row removed by id."""
    deleted: bool
    id: str


class EmptyResponse(BaseModel):
    """``{}``: what a lookup with nothing to return sends."""
    model_config = ConfigDict(extra="forbid")


class EntityProperties(BaseModel):
    """An entity node's stored properties, flattened (``dict(node)``).

    Open-ended (``extra="allow"``): nodes are schemaless, and each entity type,
    extraction pass, enrichment provider and analyst edit adds its own
    properties (``latitude``, ``asn``, ``event_datetime``, ``content`` ...).
    The keys every entity carries are declared; the rest pass through as stored.
    """
    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    entity_type: str | None = None
    entity_category: str | None = None
    project_id: str | None = None


class GraphNodeProperties(BaseModel):
    """Any graph node's stored properties (``properties(n)``) on a traversal.

    Open-ended (``extra="allow"``) for the same reason as ``EntityProperties``,
    and looser still: a walk may end on a shared catalog node (an ATT&CK
    technique, a CWE), which is keyed and named differently.
    """
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    name: str | None = None
    entity_type: str | None = None


class TraversalEdgeItem(BaseModel):
    """One edge of a traversal, its stored properties nested under ``props``."""
    rel_type: str
    source_id: str | None = None
    target_id: str | None = None
    props: dict[str, Any] = {}


class GraphEdgeProperties(BaseModel):
    """One edge with its stored properties spread flat beside its endpoints.

    Open-ended (``extra="allow"``): every stored edge property (confidence,
    evidence, method, polarity, first_seen ...) is passed through as stored.
    """
    model_config = ConfigDict(extra="allow")

    rel_type: str
    source_id: str | None = None
    target_id: str | None = None


class RelationshipItem(BaseModel):
    """One edge touching an entity, its stored properties spread flat.

    Open-ended (``extra="allow"``): the edge's own properties are spread onto
    the item as stored. The ones every extracted edge carries (the
    ``Relationship`` model's) are declared; an edge written by another path
    (an ATT&CK mapping, a CVE chain) adds its own. ``direction`` is relative to
    the entity asked about; ``neighbor_*`` is the other end whichever way the
    edge points.
    """
    model_config = ConfigDict(extra="allow")

    rel_type: str
    source_id: str | None = None
    source_name: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    direction: str
    neighbor_id: str | None = None
    neighbor_name: str | None = None
    # Stored on the edge.
    id: str | None = None
    project_id: str | None = None
    confidence: float | None = None
    source: str | None = None
    method: str | None = None
    # The source sentence(s) asserting the relationship.
    evidence: str | None = None
    source_doc_id: str | None = None
    # "asserts" or "denies".
    polarity: str | None = None
    first_seen: str | None = None
    last_seen: str | None = None
    admiralty_rating: str | None = None
    corroboration_count: int | None = None
    corroboration_sources: list[str] | None = None
    # AGREE, CONFLICT ...
    corroboration_agreement: str | None = None


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class ProjectBatchDeleteResponse(BaseModel):
    # Projects that held anything; an id that never existed is not counted.
    deleted: int
    # Postgres rows removed, per table.
    relational_rows_removed: dict[str, int]


class ProjectDeleteResponse(BaseModel):
    status: str
    entities_removed: int
    relational_rows_removed: dict[str, int]


class ProjectActivityItem(BaseModel):
    id: str
    action: str
    entity_name: str
    entity_type: str
    timestamp: str


class ProjectActivityResponse(BaseModel):
    activity: list[ProjectActivityItem]
    count: int


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class PasswordChangedResponse(BaseModel):
    status: str
    username: str
