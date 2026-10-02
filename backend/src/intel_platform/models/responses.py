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

from pydantic import BaseModel, ConfigDict, RootModel


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


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class ProxyModeItem(BaseModel):
    mode: str


class AdminConfigResponse(BaseModel):
    llm_provider: str
    llm_model: str
    extraction_mode: str
    chunk_size: int
    chunk_overlap: int
    # Host and port only; the credentials part of the URI is never sent.
    neo4j_uri: str
    proxy: ProxyModeItem


class DegradedResponse(RootModel[dict[str, dict[str, int] | str]]):
    """``{"since": iso8601, <subsystem>: {<reason>: count}}``: degraded outcomes
    since the process started. Only subsystems that degraded at least once appear."""


class ApiKeyItem(BaseModel):
    id: str
    provider: str
    label: str
    # The last four characters, or "(unreadable)" when the key cannot be decrypted.
    key_preview: str
    is_active: bool
    created_at: str | None = None


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeyItem]


class ApiKeyCreatedResponse(BaseModel):
    id: str
    provider: str
    label: str
    key_preview: str
    is_active: bool
    status: str


class ApiKeyActivatedResponse(BaseModel):
    status: str
    active_key_id: str


class LlmModelItem(BaseModel):
    provider: str
    model: str
    # Ollama's reported parameter size and quantization; empty for cloud models.
    params: str | None = None
    quantization: str | None = None
    size_gb: float
    # Whether the provider has a key (cloud) or is reachable (Ollama).
    configured: bool


class LlmModelListResponse(BaseModel):
    models: list[LlmModelItem]
    active_provider: str
    active_model: str


class LlmSelectionResponse(BaseModel):
    active_provider: str
    active_model: str
    status: str


class ProxyConfigResponse(BaseModel):
    mode: str
    vpn_http_proxy: str
    tor_socks_proxy: str


class EnrichmentConfigResponse(BaseModel):
    auto_enabled: bool


class VpnStatusResponse(BaseModel):
    """The VPN sidecar's state. When it cannot be reached only ``reachable`` and
    ``running`` (both false) are known, and the rest are null."""
    reachable: bool
    running: bool
    status: str | None = None
    public_ip: str | None = None
    country: str | None = None
    region: str | None = None
    city: str | None = None
    mode: str | None = None


class VpnActionResponse(BaseModel):
    ok: bool
    reachable: bool
    # The sidecar's answer ("running"/"stopped"); null when the request failed.
    outcome: str | None = None


# ---------------------------------------------------------------------------
# Personas
# ---------------------------------------------------------------------------

class PersonaResponse(BaseModel):
    id: str
    name: str
    description: str
    skills: list[str]
    temperature: float
    active: bool


class PersonaListResponse(BaseModel):
    personas: list[PersonaResponse]
    active_persona: str


class PersonaActivatedResponse(BaseModel):
    active_persona: str


# ---------------------------------------------------------------------------
# Notebook
# ---------------------------------------------------------------------------

class NoteCreatedResponse(BaseModel):
    note_id: str
    title: str
    note_type: str
    linked_entities: int
    # Entity ids no link could be made to (unknown, or in another project).
    unlinked_entity_ids: list[str]


class NoteResponse(EntityProperties):
    """A notebook entry: a Report node with ``report_type`` "notebook_entry".

    Open-ended (``extra="allow"``) as every ``EntityProperties`` is; the fields
    the notebook reads are declared.
    """
    content: str | None = None
    report_type: str | None = None
    note_type: str | None = None
    created_at: str | None = None


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

class WatchlistAddResponse(BaseModel):
    entity_id: str
    entity_name: str | None = None
    status: str
    watchlist_size: int


class WatchlistRemoveResponse(BaseModel):
    entity_id: str
    status: str


class WatchedEntityItem(BaseModel):
    id: str
    name: str | None = None
    entity_type: str | None = None
    relationship_count: int


class WatchlistResponse(BaseModel):
    watched_entities: list[WatchedEntityItem]
    count: int


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

class SnapshotEntityItem(BaseModel):
    id: str | None = None
    name: str | None = None
    entity_type: str | None = None


class SnapshotResponse(BaseModel):
    """A saved subgraph (bin).

    Open-ended (``extra="allow"``): a listed or fetched snapshot is the
    Snapshot node's stored properties, passed through as stored.
    """
    model_config = ConfigDict(extra="allow")

    id: str
    project_id: str | None = None
    name: str | None = None
    description: str | None = None
    entity_ids: list[str] = []
    entities: list[SnapshotEntityItem] = []
    entity_count: int | None = None
    created_at: str | None = None


class SnapshotListResponse(BaseModel):
    snapshots: list[SnapshotResponse]
    count: int


class SnapshotEdgeItem(BaseModel):
    source_id: str | None = None
    target_id: str | None = None
    rel_type: str
    confidence: float | None = None


class SnapshotDetailResponse(SnapshotResponse):
    """A snapshot with the edges among its entities. Open-ended like ``SnapshotResponse``."""
    edges: list[SnapshotEdgeItem]
    edge_count: int


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

class LlmQueryResponse(BaseModel):
    content: str
    skill_applied: str | None = None
    # "none" when no provider is configured (``content`` then says so).
    model: str
    tokens_used: int
    # Stated by the model; present only for assessment skills that state one.
    probability: float | None = None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

class SearchResultItem(BaseModel):
    id: str | None = None
    name: str | None = None
    entity_type: str
    # Documents only.
    reliability: str | None = None
    # Documents and reports: the first 200 characters of the content.
    preview: str | None = None
    # Reports only.
    report_type: str | None = None


class SearchResponse(BaseModel):
    entities: list[SearchResultItem]
    documents: list[SearchResultItem]
    reports: list[SearchResultItem]
    # Every row of this page in order: the three lists above, interleaved.
    results: list[SearchResultItem]
    count: int
    total: int
    truncated: bool


class SemanticSearchHit(BaseModel):
    chunk_text: str
    document_id: str
    chunk_index: int
    similarity: float
    metadata: dict[str, Any]


class SemanticSearchResponse(BaseModel):
    results: list[SemanticSearchHit]
    total: int


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

class TimelineEventItem(BaseModel):
    id: str | None = None
    name: str | None = None
    entity_type: str | None = None
    # The real event date when extraction found one, else ingestion time.
    timestamp: str
    # "event" (event_datetime) or "entity_created" (created_at).
    event_type: str
    date_precision: str | None = None
    date_text: str | None = None


class TimelineResponse(BaseModel):
    events: list[TimelineEventItem]
    count: int
    total: int
    truncated: bool
    types_present: list[str]
    offset: int
    project_exists: bool


class HistogramBinItem(BaseModel):
    key: str
    count: int
    by_type: dict[str, int]


class TimelineHistogramResponse(BaseModel):
    bucket: str
    bins: list[HistogramBinItem]
    dated: int
    undated: int
    earliest: str | None = None
    latest: str | None = None
    project_exists: bool
