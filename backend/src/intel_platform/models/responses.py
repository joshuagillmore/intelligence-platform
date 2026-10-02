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

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

# A member's role on a project, weakest last (api/access.py has the rules).
ProjectRole = Literal["owner", "editor", "viewer"]
# "open": no members, every authenticated user may use it; "restricted": members only.
ProjectAccessMode = Literal["open", "restricted"]


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
    # The caller's role: their membership, "owner" for an admin, null when they
    # are not a member (always the case on an open project, which they may still use).
    my_role: ProjectRole | None
    access: ProjectAccessMode


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
    # Computed, not stored: the entity's degree over the knowledge graph, every
    # edge touching it except the Document MENTIONS edges recording where it
    # was extracted from. Set on every row `GraphStore.search_entities` lists,
    # so on every `GET /entities` item; absent where a route reads a node
    # alone (`GET /entities/{id}` lists the edges themselves).
    relationship_count: int | None = None


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


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

class DocumentSummaryItem(BaseModel):
    id: str
    name: str | None = None
    reliability_rating: str
    content_length: int
    entity_count: int
    created_at: str
    summary_json: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummaryItem]
    count: int
    total: int
    truncated: bool
    project_exists: bool


class DocumentEntityItem(BaseModel):
    id: str | None = None
    name: str | None = None
    entity_type: str | None = None
    relationship: str


class DocumentHighlightItem(BaseModel):
    start: int
    end: int
    entity_id: str | None = None
    entity_name: str
    entity_type: str | None = None


class DocumentDetailResponse(BaseModel):
    id: str | None = None
    name: str | None = None
    reliability_rating: str | None = None
    content: str
    entities: list[DocumentEntityItem]
    highlights: list[DocumentHighlightItem]
    entity_count: int
    summary_json: str | None = None


class EvidencePassageItem(BaseModel):
    text: str
    # Character offset of the mention in the document's content.
    position: int
    entity_name: str


class DocumentEvidenceResponse(BaseModel):
    document_id: str
    document_name: str | None = None
    entity_name: str
    passages: list[EvidencePassageItem]
    count: int
    total: int
    truncated: bool


# ---------------------------------------------------------------------------
# Entities and traversals
# ---------------------------------------------------------------------------

class EntityTypeHierarchyResponse(BaseModel):
    # Parent category -> its specific entity types.
    hierarchy: dict[str, list[str]]
    categories: list[str]


class EntityDetailResponse(BaseModel):
    entity: EntityProperties
    relationships: list[RelationshipItem]


class SubgraphResponse(BaseModel):
    nodes: list[GraphNodeProperties]
    edges: list[TraversalEdgeItem]
    node_count: int
    edge_count: int
    # Whether the path budget cut the walk short; null when the entity is unknown.
    truncated: bool | None = None


class ShortestPathResponse(BaseModel):
    nodes: list[GraphNodeProperties]
    edges: list[TraversalEdgeItem]
    # -1 when no path was found.
    path_length: int
    found: bool


class EntityMergeResponse(BaseModel):
    primary_id: str
    primary_name: str | None = None
    entities_merged: int
    relationships_transferred: int
    # Edges that could not be recreated on the primary; their entity was kept.
    dropped_edges: int
    entities_not_merged: list[str]
    entities_not_found: list[str]
    complete: bool


class EntityTypeChangedResponse(BaseModel):
    id: str
    name: str | None = None
    old_type: str | None = None
    new_type: str


# ---------------------------------------------------------------------------
# Graph analytics
# ---------------------------------------------------------------------------

class GraphViewNodeItem(BaseModel):
    id: str
    name: str
    entity_type: str
    entity_category: str
    # Louvain community, -1 when the node was not partitioned.
    community_id: int
    pagerank: float
    degree: int
    # When the thing happened ("" when undated), not when it was ingested.
    event_datetime: str
    date_precision: str
    date_text: str


class GraphViewEdgeItem(BaseModel):
    source_id: str
    target_id: str
    rel_type: str
    confidence: float
    evidence: str
    method: str
    source_doc_id: str
    polarity: str
    first_seen: str | None = None
    last_seen: str | None = None


class GraphViewResponse(BaseModel):
    project_exists: bool
    nodes: list[GraphViewNodeItem]
    edges: list[GraphViewEdgeItem]
    node_count: int
    edge_count: int
    # How many entities the project holds in all; `node_count` is this view.
    total_nodes: int
    truncated: bool


class GraphMemberItem(BaseModel):
    id: str
    name: str
    entity_type: str


class CommunityItem(BaseModel):
    community_id: int
    members: list[GraphMemberItem]
    size: int


class CentralityItem(GraphMemberItem):
    degree: int


class NodeStatisticsItem(GraphMemberItem):
    degree: int
    in_degree: int
    out_degree: int
    betweenness: float
    eigenvector: float
    pagerank: float
    closeness: float


class GraphStatisticsResponse(BaseModel):
    nodes: int
    edges: int
    density: float
    components: int
    # True when the metrics were computed over the budgeted sample.
    truncated: bool
    entities: list[NodeStatisticsItem]
    project_exists: bool


class StructuralHoleItem(GraphMemberItem):
    constraint: float
    effective_size: float
    degree: int
    is_broker: bool


class EgoNodeItem(GraphMemberItem):
    hop_distance: int
    local_pagerank: float
    local_betweenness: float


class EgoEdgeItem(BaseModel):
    source_id: str
    target_id: str
    rel_type: str
    confidence: float | None = None
    weight: float | None = None


class EgoNetworkResponse(BaseModel):
    center: str
    hops: int
    # Null when the entity is not in the project's graph.
    node_count: int | None = None
    edge_count: int | None = None
    nodes: list[EgoNodeItem]
    edges: list[EgoEdgeItem]


class InfluenceStepItem(BaseModel):
    step: int
    newly_activated: list[GraphMemberItem]
    cumulative_count: int


class InfluenceResponse(BaseModel):
    seeds: list[str]
    steps: list[InfluenceStepItem]
    total_activated: int
    reach_ratio: float
    # Null when no seed was in the graph.
    total_nodes: int | None = None


# ---------------------------------------------------------------------------
# Geo
# ---------------------------------------------------------------------------

class GeoRelationshipItem(BaseModel):
    target_name: str | None = None
    rel_type: str | None = None
    target_id: str | None = None
    direction: str
    confidence: float | None = None


class GeoLocationItem(BaseModel):
    id: str
    name: str
    entity_type: str
    latitude: float | None = None
    longitude: float | None = None
    geocoded: bool
    # Where the coordinate came from: persisted, geoip, nominatim, gazetteer ("" if none).
    geo_source: str
    geo_confidence: str
    location_type: str
    mgrs: str
    # The node's stored properties, as stored.
    properties: dict[str, Any]
    # Set by /geo/locations only.
    relationships: list[GeoRelationshipItem] | None = None
    connection_count: int | None = None


class GeoEdgeItem(BaseModel):
    """Two places joined through the entities they share."""
    source_id: str
    target_id: str
    source_name: str
    target_name: str
    weight: int
    # Up to ten of the shared entities, by name.
    shared_entities: list[str | None]
    # [lat, lng], present when both places are geocoded.
    source_coords: list[float] | None = None
    target_coords: list[float] | None = None


class GeoLocationsResponse(BaseModel):
    locations: list[GeoLocationItem]
    edges: list[GeoEdgeItem]
    total: int
    geocoded: int
    edge_count: int


class BoundingBoxItem(BaseModel):
    min_lat: float
    min_lng: float
    max_lat: float
    max_lng: float


class GeoWithinResponse(BaseModel):
    entities: list[GeoLocationItem]
    count: int
    bbox: BoundingBoxItem


class GeoPointItem(BaseModel):
    lat: float
    lng: float


class NearbyFeatureItem(BaseModel):
    name: str
    # airfield, military, port, power, infrastructure, government, emergency, neighbourhood, feature
    category: str
    lat: float
    lon: float
    # The OSM tags kept for display.
    tags: dict[str, Any]


class NearbyFeaturesResponse(BaseModel):
    features: list[NearbyFeatureItem]
    count: int
    # Null, with `error`, when the entity has no coordinates.
    center: GeoPointItem | None = None
    radius: int | None = None
    error: str | None = None


class EntityTimelineEventItem(BaseModel):
    date: str
    # entity_created, event, relationship, event_date, document_ingested
    type: str
    label: str


class DateCountItem(BaseModel):
    date: str
    count: int


class DateRangeItem(BaseModel):
    start: str
    end: str


class EntityTimelineResponse(BaseModel):
    # Null when the entity is unknown (the lists are then empty).
    entity_id: str | None = None
    entity_name: str | None = None
    events: list[EntityTimelineEventItem]
    buckets: list[DateCountItem]
    date_range: DateRangeItem | None = None
    total_events: int | None = None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class GraphExportResponse(BaseModel):
    """The project graph as stored: node and edge property maps."""
    nodes: list[GraphNodeProperties]
    edges: list[GraphEdgeProperties]
    node_count: int
    edge_count: int
    truncated: bool


class EntityCsvExportResponse(BaseModel):
    # id,name,entity_type rows; formula-leading cells are quoted literal.
    csv: str
    count: int


class ReportExportResponse(BaseModel):
    title: str
    content: str
    report_type: str


class MindmapTextExportResponse(BaseModel):
    # "markdown" or "mermaid"
    format: str
    content: str


class StixBundleResponse(BaseModel):
    """A STIX 2.1 bundle; ``objects`` are STIX objects of mixed types."""
    type: str
    id: str
    objects: list[dict[str, Any]]
    # Entity types left out because STIX has no faithful equivalent, with counts.
    x_sentinel_omitted_entity_types: dict[str, int] | None = None


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

class ReportSavedResponse(BaseModel):
    report_id: str
    title: str
    report_type: str
    content_length: int
    linked_entities: int


class ReportResponse(EntityProperties):
    """A saved report: a Report node's stored properties.

    Open-ended (``extra="allow"``) as every ``EntityProperties`` is; the fields
    the products view reads are declared.
    """
    content: str | None = None
    report_type: str | None = None
    status: str | None = None
    created_at: str | None = None


class EvidenceEdgeItem(BaseModel):
    """A relationship a product was drawn from, with its provenance."""
    source_name: str | None = None
    target_name: str | None = None
    rel_type: str
    confidence: float | None = None
    evidence: str
    source_doc_id: str
    admiralty_rating: str
    corroboration_count: int
    corroboration_agreement: str
    method: str


class GeneratedReportResponse(BaseModel):
    content: str
    model: str
    tokens_used: int
    skill_applied: str
    # "grounded" when graph or document evidence was retrieved, else "ungrounded".
    retrieval_mode: str
    context_nodes: int
    context_edges: int
    evidence: list[EvidenceEdgeItem]
    # Assessment skills only: the stated probability, and whether one was stated.
    probability: float | None = None
    probability_parsed: bool | None = None


# ---------------------------------------------------------------------------
# Graph-RAG query
# ---------------------------------------------------------------------------

class GraphRagQueryResponse(BaseModel):
    query: str
    # Empty when no model answered; `llm_error` then says why.
    answer: str
    model: str
    tokens_used: int
    llm_error: str | None = None
    context: str
    context_nodes: int
    context_edges: int
    # "hybrid" (graph + vector) or "graph".
    retrieval_mode: str
    # Hybrid mode only: how many document passages vector search contributed.
    vector_results: int | None = None


# ---------------------------------------------------------------------------
# Structured analytic techniques
# ---------------------------------------------------------------------------

class SourceEvaluationItem(BaseModel):
    document_id: str
    name: str | None = None
    current_rating: str
    # Parsed from the model's RATINGS block; "" when it gave none.
    admiralty_rating: str
    entity_count: int
    corroborating_documents: int


class SourceMetricItem(BaseModel):
    document_id: str
    name: str | None = None
    url: str
    current_rating: str
    created_at: str
    content_length: int
    entity_count: int
    entity_names: list[str]
    corroborating_documents: int


class SourceEvaluationResponse(BaseModel):
    analysis: str
    skill_applied: str
    model: str
    tokens_used: int
    retrieval_mode: str
    documents_evaluated: int
    evaluations: list[SourceEvaluationItem]
    metrics: list[SourceMetricItem]
    ratings_applied: int


class HypothesisItem(BaseModel):
    id: str
    statement: str
    probability: float
    probability_label: str


class HypothesesResponse(BaseModel):
    question: str
    analysis: str
    hypotheses: list[HypothesisItem]
    skill_applied: str
    model: str
    tokens_used: int
    retrieval_mode: str
    context_nodes: int
    context_edges: int
    vector_hits: int
    focus_entities: list[str]
    # Set when the leading hypothesis was saved as an Assessment.
    assessment_id: str | None = None
    probability: float | None = None
    probability_label: str | None = None


class CoverageItem(BaseModel):
    entities: int
    isolated: int
    single_link: int
    unsourced: int
    isolated_names: list[str]
    single_link_names: list[str]
    unsourced_names: list[str]
    documents: int
    unrated_documents: int
    unrated_document_names: list[str]
    locations: int
    ungeocoded_locations: int
    ungeocoded_names: list[str]
    entity_type_counts: dict[str, int]
    relationship_type_counts: dict[str, int]
    relationships: int


class StructuralGapItem(BaseModel):
    kind: str
    title: str
    detail: str
    priority: str
    count: int
    examples: list[str]


class GapAnalysisResponse(BaseModel):
    analysis: str
    skill_applied: str
    model: str
    tokens_used: int
    retrieval_mode: str
    coverage: CoverageItem
    structural_gaps: list[StructuralGapItem]
    context_nodes: int
    context_edges: int
    focus_entities: list[str]


# ---------------------------------------------------------------------------
# Assessments
# ---------------------------------------------------------------------------

class AssessmentCreatedResponse(BaseModel):
    assessment_id: str
    entity_id: str
    entity_name: str
    judgment: str
    probability: float
    probability_label: str


class AssessmentErrorItem(BaseModel):
    """An assessment that could not be made (its entity is gone)."""
    error: str


class GeneratedAssessmentResponse(BaseModel):
    assessment: str
    model: str
    tokens_used: int
    # The saved Assessment. Null, with `error`, only when the entity vanished
    # between the read and the save.
    assessment_id: str | None = None
    entity_id: str | None = None
    entity_name: str | None = None
    judgment: str | None = None
    probability: float | None = None
    probability_label: str | None = None
    error: str | None = None
    # False when the reply stated no readable probability and the request's
    # fallback was stored instead.
    probability_parsed: bool


class EntityContextItem(BaseModel):
    entity: EntityProperties
    relationships: list[RelationshipItem]
    relationship_count: int


class MultiAssessmentResponse(BaseModel):
    entities: list[EntityContextItem]
    assessments: list[AssessmentCreatedResponse | AssessmentErrorItem]
    entity_count: int


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

class GraphBuildStats(BaseModel):
    """What one graph build did with an extraction's entities and relationships.

    Open-ended (``extra="allow"``): the build's counters are spread into the
    response as the graph builder reports them, and that set grows as the
    extraction pipeline learns to count new outcomes.
    """
    model_config = ConfigDict(extra="allow")

    entities_created: int = 0
    entities_merged: int = 0
    entities_filtered: int = 0
    dates_absorbed: int = 0
    dates_orphaned: int = 0
    relationships_retired: int = 0
    relationships_created: int = 0
    relationships_dropped: int = 0
    relationships_dropped_by_type: dict[str, int] = {}
    relationships_dropped_by_reason: dict[str, int] = {}
    dropped_attributes: int = 0
    mentions_recorded: int = 0


class IngestResponse(GraphBuildStats):
    """One stored document and the graph build over it. Open-ended like ``GraphBuildStats``."""
    document_id: str
    document_name: str
    chunks: int
    # The document was cut to MAX_DOCUMENT_CHARS for storage and extraction.
    content_truncated: bool
    embeddings_stored: int
    # False when the document is in the graph but not findable by meaning.
    indexed_for_search: bool


class BatchIngestResponse(BaseModel):
    documents_processed: int
    total_entities_created: int
    total_relationships_created: int
    results: list[IngestResponse]


# ---------------------------------------------------------------------------
# Legacy collections (/collections)
# ---------------------------------------------------------------------------

class LegacyCollectionResponse(BaseModel):
    """A legacy collection: the Collection node's stored properties, with its
    plan decoded from ``plan_json``.

    Open-ended (``extra="allow"``): the node's properties are passed through as
    stored, and the runner adds its own (``progress``, ``updated_at``).
    """
    model_config = ConfigDict(extra="allow")

    id: str
    project_id: str | None = None
    pir: str | None = None
    refined_pir: str | None = None
    refinement: str | None = None
    plan: list[dict[str, Any]]
    status: str | None = None
    documents_acquired: int | None = None
    # 0..1 while a run is going; written by the runner.
    progress: float | None = None
    created_at: str | None = None
    updated_at: str | None = None


class LegacyCollectionStatusResponse(BaseModel):
    status: str | None = None
    progress: float
    documents_acquired: int


class LegacyCollectionProgressResponse(BaseModel):
    collection_id: str
    status: str
    progress: float
    documents_acquired: int
    # Documents the run stored in the graph.
    documents_in_graph: int


class LegacyCollectionStartedResponse(BaseModel):
    collection_id: str
    status: str


class CollectionCountResponse(BaseModel):
    project_id: str
    count: int


class ParsedPlanItem(BaseModel):
    id: int
    description: str
    source_type: str
    status: str
    approved: bool


class ParsedPlanResponse(BaseModel):
    items: list[ParsedPlanItem]
    count: int


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

class EnrichmentProviderItem(BaseModel):
    name: str
    supported_types: list[str]
    requires_key: bool
    has_key: bool
    # Runs on ingest when auto-enrich is on.
    auto: bool


class EnrichmentProviderListResponse(BaseModel):
    providers: list[EnrichmentProviderItem]


class ProviderOutcomeItem(BaseModel):
    # ok, cached, skipped, error or timeout
    status: str
    reason: str | None = None
    # ok only: the properties the provider wrote, and how many related nodes it added.
    properties: dict[str, Any] | None = None
    related: int | None = None


class EnrichmentRunResponse(BaseModel):
    entity_id: str | None = None
    observable: str | None = None
    # Per provider that ran.
    providers: dict[str, ProviderOutcomeItem]


class CachedEnrichmentResponse(BaseModel):
    entity_id: str
    observable: str
    # Provider name -> its cached payload; only providers with a cached entry appear.
    cached: dict[str, dict[str, Any]]


# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

class TopicNodeItem(BaseModel):
    """One node of the topic tree: a branch, a topic cluster, a category, a
    document or an entity leaf.

    Open-ended (``extra="allow"``): each kind of node carries its own keys
    (``keywords`` and ``doc_ids`` on clusters, ``reliability`` on documents,
    ``connections`` on actors, ``user_created``/``edited`` after an analyst's
    edit ...). A leaf has only ``id``, ``name`` and ``entity_type``.
    """
    model_config = ConfigDict(extra="allow")

    id: str
    name: str | None = None
    entity_type: str | None = None
    count: int | None = None
    children: list[TopicNodeItem] | None = None


class TopicCrossReferenceItem(BaseModel):
    """A document that sits in more than one topic cluster."""
    doc_id: str
    doc_name: str
    topic_ids: list[str]


class TopicTreeResponse(BaseModel):
    name: str
    id: str
    entity_count: int
    document_count: int
    children: list[TopicNodeItem]
    # Whether topic names came from a model ("llm") or keyword extraction.
    label_source: str | None = None
    labels_refined: int | None = None
    labels_failed: int | None = None
    cross_references: list[TopicCrossReferenceItem] | None = None
    # Set by an analyst's edit of the root.
    description: str | None = None
    edited: bool | None = None
    # /topics only: how many stored edits applied, how many no longer match a
    # node, and whether the edits could be read ("applied"/"unavailable").
    edits_applied: int | None = None
    edits_unmatched: int | None = None
    edits_overlay: str | None = None


class TopicContextEntityItem(BaseModel):
    id: str | None = None
    name: str | None = None
    entity_type: str | None = None


class RelevantExcerptItem(BaseModel):
    """A sentence that mentions a topic cluster's keywords."""
    text: str
    # How many of the keywords it mentions.
    score: float
    matched_keywords: list[str]


class TopicDocumentItem(BaseModel):
    id: str | None = None
    name: str | None = None
    reliability_rating: str | None = None
    content_preview: str
    # Topic clusters only: passages matching the cluster's keywords.
    relevant_excerpts: list[RelevantExcerptItem] | None = None
    keyword_matches: dict[str, int] | None = None
    relevance_score: int | None = None


class DocumentExcerptItem(BaseModel):
    name: str
    content: str


class TopicConnectedEntityItem(BaseModel):
    id: str | None = None
    name: str | None = None
    entity_type: str | None = None
    rel_type: str | None = None
    confidence: float | None = None


class TopicContextResponse(BaseModel):
    entity: TopicContextEntityItem
    documents: list[TopicDocumentItem]
    # The same list as `documents`, kept under both names.
    source_documents: list[TopicDocumentItem]
    document_excerpts: list[DocumentExcerptItem]
    connected_entities: list[TopicConnectedEntityItem]
    keywords: list[str]
    document_count: int
    # Entities only (not topic clusters).
    relationship_count: int | None = None


class ErrorMessageResponse(BaseModel):
    """A 200 that carries only an error message, e.g. ``{"error": "Entity not found"}``."""
    error: str


class TopicNodeUpdatedResponse(BaseModel):
    node_id: str
    updated: bool


class TopicChildCreatedResponse(BaseModel):
    node_id: str
    parent_id: str
    name: str


class TopicNodeDeletedResponse(BaseModel):
    node_id: str
    deleted: bool


# ---------------------------------------------------------------------------
# MITRE ATT&CK
# ---------------------------------------------------------------------------

class AttackCountsItem(BaseModel):
    tactics: int
    techniques: int
    groups: int
    software: int
    mitigations: int


class VulnChainStatusItem(BaseModel):
    ingested: bool
    cwes: int


class AttackStatusResponse(BaseModel):
    ingested: bool
    version: str | None = None
    counts: AttackCountsItem
    vuln_chain: VulnChainStatusItem


class AttackIngestResponse(BaseModel):
    ingested: bool
    version: str
    counts: AttackCountsItem


class VulnChainIngestResponse(BaseModel):
    cwes: int
    edges: int


class CveResolutionResponse(BaseModel):
    vulnerabilities: int
    techniques_linked: int


class AttackEmbedResponse(BaseModel):
    embedded: int
    # When nothing was embedded: a machine reason and a sentence for the analyst.
    reason: str | None = None
    detail: str | None = None


class AttackMapResponse(BaseModel):
    mapped: int
    skipped: int
    # Reason -> how many TTPs were skipped for it.
    skip_reasons: dict[str, int]
    # With `remap` only: earlier model mappings the model no longer confirms.
    stale_removed: int | None = None
    # When the whole batch could not run.
    reason: str | None = None
    detail: str | None = None


class AttackResolveResponse(BaseModel):
    mapped: int


class AttackRefItem(BaseModel):
    id: str
    name: str | None = None


class AttributionGroupItem(BaseModel):
    id: str
    name: str | None = None
    shared_count: int
    # shared / observed_total, 0..1.
    coverage: float
    shared_techniques: list[AttackRefItem]


class AttributionResponse(BaseModel):
    """Groups ranked by technique overlap: suggestive, never confirmed attribution."""
    observed_total: int
    groups: list[AttributionGroupItem]


class AttackSubtechniqueItem(BaseModel):
    id: str
    name: str | None = None
    observed_count: int
    # How the project's entities were mapped to it: "tcode" and/or "llm".
    methods: list[str]


class AttackTechniqueCellItem(BaseModel):
    id: str
    name: str | None = None
    is_subtechnique: bool
    # Includes the sub-techniques' counts.
    observed_count: int
    methods: list[str]
    subtechniques: list[AttackSubtechniqueItem]


class AttackTacticItem(BaseModel):
    id: str
    name: str | None = None
    shortname: str | None = None
    techniques: list[AttackTechniqueCellItem]


class AttackMatrixResponse(BaseModel):
    version: str | None = None
    ingested: bool
    tactics: list[AttackTacticItem]


class AttackTacticRefItem(BaseModel):
    id: str
    name: str | None = None
    shortname: str | None = None


class AttackMappedEntityItem(BaseModel):
    id: str
    name: str | None = None
    entity_type: str | None = None
    # "tcode" (an explicit T-code, confidence 1.0) or "llm" (the model's confidence).
    method: str
    confidence: float | None = None


class AttackTechniqueResponse(BaseModel):
    # The technique's ATT&CK id (the one asked for).
    id: str
    name: str
    description: str
    is_subtechnique: bool
    parent_id: str | None = None
    tactics: list[AttackTacticRefItem]
    platforms: list[str]
    detection: str
    mitigations: list[AttackRefItem]
    groups: list[AttackRefItem]
    related_entities: list[AttackMappedEntityItem]
    # Project CVEs whose weaknesses could enable the technique (not observed use).
    enabling_cves: list[AttackRefItem]


class D3fendCountermeasureItem(BaseModel):
    # D3FEND code, e.g. "D3-DI".
    id: str
    label: str
    # The d3f: local name, e.g. "DataInventory".
    name: str | None = None


class D3fendResponse(BaseModel):
    countermeasures: list[D3fendCountermeasureItem]
    # The live lookup failed, so an empty list means "unknown", not "none".
    degraded: bool | None = None


class ObservedTechniqueItem(BaseModel):
    id: str
    name: str | None = None
    observed_count: int
    methods: list[str]


class ObservedTacticItem(BaseModel):
    tactic_id: str
    tactic_name: str | None = None
    techniques: list[ObservedTechniqueItem]


class AttributionSummaryItem(BaseModel):
    id: str
    name: str | None = None
    shared_count: int
    coverage: float


class KeyMitigationItem(BaseModel):
    id: str | None = None
    name: str | None = None
    technique_count: int


class CveEnabledTechniqueItem(BaseModel):
    technique_id: str | None = None
    technique_name: str | None = None
    cves: list[AttackRefItem]


class AttackReportResponse(BaseModel):
    project_id: str
    observed_by_tactic: list[ObservedTacticItem]
    attribution: list[AttributionSummaryItem]
    key_mitigations: list[KeyMitigationItem]
    cve_enabled: list[CveEnabledTechniqueItem]
    # A short model-written summary; null when no model was reachable.
    narrative: str | None = None
    markdown: str


class NavigatorTechniqueItem(BaseModel):
    techniqueID: str
    score: int
    color: str
    comment: str
    enabled: bool
    # The tactic shortname; absent when the technique has none.
    tactic: str | None = None


class NavigatorGradientItem(BaseModel):
    colors: list[str]
    minValue: int
    maxValue: int


class NavigatorLayerResponse(BaseModel):
    """A MITRE ATT&CK Navigator layer (v4.5), served as a download."""
    name: str
    versions: dict[str, str]
    domain: str
    description: str
    techniques: list[NavigatorTechniqueItem]
    gradient: NavigatorGradientItem
    legendItems: list[Any]
    showTacticRowBackground: bool
    hideDisabled: bool


# ---------------------------------------------------------------------------
# Collection plans
# ---------------------------------------------------------------------------

class CollectionSourceResponse(BaseModel):
    id: str
    plan_id: str
    name: str
    source_type: str
    config: dict[str, Any]
    # pending, resolving, queued, collecting, succeeded or failed.
    collection_status: str
    schedule_cron: str
    enabled: bool
    last_success_at: str | None = None
    last_failure_at: str | None = None
    last_error: str
    total_records_acquired: int
    acquisition_count: int
    next_run_at: str | None = None
    created_at: str | None = None


class CollectionPlanResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: str
    requirement: str
    pir: str
    pir_id: str | None = None
    refined_pir: str
    # A lifecycle flag an analyst sets; whether a run is in flight is
    # /execution-status, never this.
    status: str
    routing_rules: dict[str, Any]
    created_by: str
    assigned_to: str
    schedule_cron: str
    next_run_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    sources: list[CollectionSourceResponse]
    source_count: int


class LlmRequirementsItem(BaseModel):
    message: str
    supported_providers: list[str]
    configuration: str
    minimum_capability: str


class PlanFromPirResponse(CollectionPlanResponse):
    """A plan generated from a PIR, with how the generation went."""
    llm_plan_text: str
    llm_available: bool
    llm_status: str
    # Why generation produced less than it should have.
    generation_failures: list[str]
    # Essential elements captured onto the requirement.
    eeis_captured: int
    # Present when no LLM provider could be used.
    llm_requirements: LlmRequirementsItem | None = None


class PlanExecutionStartedResponse(CollectionPlanResponse):
    """``POST /execute`` (202): the plan, and how its run started."""
    # Null when nothing could run.
    job_id: str | None = None
    # "inline" (this process runs it) or "worker" (queued for the worker).
    worker_mode: str
    # started, queued or no_executable_sources.
    execution_status: str
    message: str
    sources_queued: int
    sources_manual: int
    sources_missing_config: int
    source_limit: int | None = None
    sources_over_budget: int
    warnings: list[str]


class PlanExecutionStatusResponse(BaseModel):
    """Whether a run is in flight and how it is going, from the job table and the
    activity trail. Keys about the trail are absent before it has any events, and
    keys about the job row are absent before the plan's first run."""
    plan_id: str
    # idle, running, stalled, completed, failed or cancelled.
    status: str
    message: str
    last_event: str | None = None
    sources_succeeded: int
    sources_failed: int
    updated_at: str | None = None
    seconds_since_last_event: int | None = None
    job_id: str | None = None
    # queued, running, succeeded, failed or cancelled.
    job_status: str | None = None
    heartbeat_at: str | None = None
    seconds_since_heartbeat: int | None = None
    # Why the run failed, sanitised.
    error: str | None = None
    # This run's degraded outcomes, {subsystem: {reason: count}}.
    degraded: dict[str, dict[str, int]] | None = None


class PlanCancelResponse(BaseModel):
    plan_id: str
    job_id: str
    status: str
    previous_status: str
    # True when the run was mid-flight and stops before its next source.
    stopping: bool
    message: str


class CollectionActivityItem(BaseModel):
    id: str
    plan_id: str
    source_id: str | None = None
    event: str
    message: str
    created_at: str


class UploadRoutingItem(BaseModel):
    document_id: str
    entities_created: int
    relationships_created: int


class FileUploadResponse(BaseModel):
    catalog_id: str
    plan_id: str
    source_id: str
    filename: str
    file_format: str
    record_count: int
    column_count: int
    # Column names, inferred types and sample values, as the parser reports them.
    schema_info: dict[str, Any]
    profiling: dict[str, Any]
    preview_rows: list[dict[str, Any]]
    routing_results: UploadRoutingItem


class AcquisitionLogItem(BaseModel):
    id: str
    source_id: str
    plan_id: str
    result: str
    record_count: int
    error_message: str
    source_type: str
    entities_created: int
    relationships_created: int
    document_id: str
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int


class DataCatalogItem(BaseModel):
    id: str
    plan_id: str
    source_id: str
    name: str
    file_format: str
    original_filename: str
    file_size_bytes: int
    row_count: int
    column_count: int
    schema_info: dict[str, Any]
    profiling: dict[str, Any]
    preview_rows: list[dict[str, Any]]
    ingested_at: str | None = None


class CatalogPreviewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rows: list[dict[str, Any]]
    total: int
    offset: int
    # Sent as `schema` (a name BaseModel reserves).
    schema_info: dict[str, Any] = Field(alias="schema")


class SourceHealthItem(BaseModel):
    healthy: int
    unhealthy: int
    disabled: int
    total: int


class CollectionDashboardResponse(BaseModel):
    project_id: str
    # Plan status -> how many plans have it.
    plan_counts: dict[str, int]
    total_plans: int
    source_health: SourceHealthItem
    total_records_acquired: int
    recent_acquisitions: list[AcquisitionLogItem]


class ConnectorTypeItem(BaseModel):
    source_type: str
    description: str


# ---------------------------------------------------------------------------
# PIRs
# ---------------------------------------------------------------------------

class RequirementElementItem(BaseModel):
    ordinal: int
    text: str
    # pending (still open), satisfied, or unmet (tried and given up on).
    status: str
    attempts: int
    queries_tried: list[str]
    # What the assessor said is still absent.
    missing: str
    confidence: str


class PirRequirementsResponse(BaseModel):
    pir_id: str
    project_id: str
    total: int
    # Element status -> count; pending, satisfied and unmet are always present.
    counts: dict[str, int]
    elements: list[RequirementElementItem]


class EeiAssessmentItem(BaseModel):
    index: int
    eei: str
    # SATISFIED, PARTIAL, UNMET or UNASSESSED.
    verdict: str
    justification: str


class UnmetCriterionItem(BaseModel):
    eei: str
    verdict: str
    why: str


class PirEvidenceItem(BaseModel):
    """What the verdicts were judged from."""
    # "graph+passages" or "graph-only".
    substrate: str
    dated_entities: int
    passages_retrieved: int
    elements_with_passages: list[int]
    elements_without_passages: list[int]
    retrieval_failed_for: list[int]
    budget_starved_elements: list[int]
    embedding_fallback: bool
    embedding_failed: bool
    embedding_dim_mismatch: bool
    retrieval_unavailable: bool
    retrieval_degraded: bool


class PirAssessmentResponse(BaseModel):
    pir_id: str
    # The stored status after the assessment.
    status: str
    # What this assessment concluded; null when nothing was judged.
    assessed_status: str | None = None
    eeis_total: int
    eeis_satisfied: int
    assessments: list[EeiAssessmentItem]
    unmet_criteria: list[UnmetCriterionItem]
    entities_considered: int
    entities_total: int
    evidence: PirEvidenceItem
    # Succeeded sources in the latest plan, and in every plan for the PIR.
    sources_used: int
    sources_used_all_plans: int
    sources_configured: int
    source_limit: int | None = None
    stopped_on_source_limit: bool
    recommendation: str
    model: str
    narrative: str


# ---------------------------------------------------------------------------
# Project members (contract 3)
# ---------------------------------------------------------------------------

class ProjectMemberItem(BaseModel):
    username: str
    role: ProjectRole
    # Who added them, and when (ISO 8601). A role change keeps both.
    added_by: str
    added_at: str


class ProjectMembersResponse(BaseModel):
    """A project's members, owners first. Admins are implicit owners and never listed."""
    members: list[ProjectMemberItem]
    access: ProjectAccessMode
    my_role: ProjectRole | None
