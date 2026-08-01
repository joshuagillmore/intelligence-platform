"""SQLAlchemy models for collection management system.

Tables:
- pirs: Priority Intelligence Requirements — the requirements spine a project's
  collection hangs off (PIR → collection plan → graph → product)
- collection_plans: The nerve center — tracks requirements, status, ownership
- collection_sources: Source assignments per plan (file, web, db, api)
- acquisition_log: Every fetch attempt with result and provenance
- data_catalog: Metadata for ingested datasets (schema, profiling, row counts)
- connector_configs: Reusable connector configurations with encrypted credentials
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

try:
    from pgvector.sqlalchemy import Vector
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment,misc]


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# API Keys — per-provider credential storage
# ---------------------------------------------------------------------------

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True,
        comment="anthropic | openai | cohere | ollama")
    label: Mapped[str] = mapped_column(String(128), nullable=False,
        comment="User-friendly label, e.g. 'Personal Key', 'Team Key'")
    api_key: Mapped[str] = mapped_column(Text, nullable=False,
        comment="The raw API key value")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False,
        comment="Only one key per provider should be active at a time")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_apikey_provider_active", "provider", "is_active"),
    )


# ---------------------------------------------------------------------------
# App Settings — small key/value store for runtime config that must survive
# restarts (e.g. the active collection-egress proxy mode).
# ---------------------------------------------------------------------------

class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True,
        comment="Setting key, e.g. 'collection_proxy_mode'")
    value: Mapped[str] = mapped_column(Text, default="",
        comment="Setting value as a string")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Enrichment cache — external-lookup results for a cyber observable, keyed by
# (provider, observable). Doubles as the cache that spares repeat external
# calls AND the audit trail of every enrichment call made.
# ---------------------------------------------------------------------------

class EnrichmentRecord(Base):
    __tablename__ = "enrichment_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(32), nullable=False,
        comment="Enrichment provider name, e.g. 'rdap' | 'dns' | 'geoip'")
    observable: Mapped[str] = mapped_column(String(512), nullable=False,
        comment="Normalized (refanged) observable value that was looked up")
    entity_type: Mapped[str] = mapped_column(String(32), default="",
        comment="Entity type of the observable, e.g. 'IPAddress'")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict,
        comment="Provider result payload — cache value + audit record")
    source_url: Mapped[str] = mapped_column(Text, default="",
        comment="Provider source URL, carried as relationship evidence")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Freshness horizon; NULL = never expires")

    __table_args__ = (
        UniqueConstraint("provider", "observable", name="uq_enrichment_provider_observable"),
        Index("ix_enrichment_provider_observable", "provider", "observable"),
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PlanStatus(str):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class PirStatus(str):
    """Lifecycle of a Priority Intelligence Requirement.

    OPEN → the question is still outstanding; PARTIAL → some EEIs answered;
    SATISFIED → the requirement has been answered; ARCHIVED → retired.
    """
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    SATISFIED = "SATISFIED"
    ARCHIVED = "ARCHIVED"


PIR_STATUSES = (PirStatus.OPEN, PirStatus.PARTIAL, PirStatus.SATISFIED, PirStatus.ARCHIVED)
PIR_PRIORITIES = ("critical", "high", "medium", "low")


class SourceType(str):
    FILE_UPLOAD = "file_upload"
    WEB_SCRAPE = "web_scrape"
    API_FEED = "api_feed"
    DATABASE = "database"
    RSS_FEED = "rss_feed"
    WATCHED_DIR = "watched_dir"


class AcquisitionResult(str):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"


# ---------------------------------------------------------------------------
# PIR — Priority Intelligence Requirement, the requirements spine
#
# A PIR is what the project is trying to answer. It lives next to the collection
# plans it drives (same store, same lifecycle language) so the chain
# PIR → collection plan → acquisition is a single join rather than a
# cross-datastore lookup. Projects themselves live in Neo4j; project_id is
# carried here as a plain string exactly as CollectionPlan/ChunkEmbedding do.
# ---------------------------------------------------------------------------

class Pir(Base):
    __tablename__ = "pirs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True,
        comment="Neo4j Project id this requirement belongs to")

    title: Mapped[str] = mapped_column(String(256), default="",
        comment="Short analyst-facing label, e.g. 'PIR-1 — Actor infrastructure'")
    text: Mapped[str] = mapped_column(Text, default="",
        comment="The intelligence question as written by the analyst")
    refined_text: Mapped[str] = mapped_column(Text, default="",
        comment="LLM-refined restatement of the PIR (written back by /collection-plans/from-pir)")
    eeis: Mapped[list] = mapped_column(JSONB, default=list,
        comment="Essential Elements of Information — the sub-questions, as a list of strings")

    priority: Mapped[str] = mapped_column(String(16), default="medium", nullable=False,
        comment="critical | high | medium | low — mirrors Project.priority vocabulary")
    status: Mapped[str] = mapped_column(
        String(20), default=PirStatus.OPEN, nullable=False, index=True,
        comment="OPEN | PARTIAL | SATISFIED | ARCHIVED")

    created_by: Mapped[str] = mapped_column(String(128), default="analyst")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_pir_project_status", "project_id", "status"),
    )


# Requirement state, one row per EEI.
#
# `Pir.eeis` is a list of strings, which is enough to *display* the criteria and
# enough to judge them once at the end — but not enough to collect against them.
# Driving collection needs somewhere to record, per element, whether it is
# answered yet, how many times it has been tried, what the assessor said was
# missing, and which queries to run next. Without that the assessment is a
# report: a live run ended "3 element(s) still unanswered and collection budget
# remains — continue collection" and nothing continued it, because there was no
# per-element state for a loop to iterate over.
#
# `eeis` stays the source of truth for the criteria *text* (every existing
# consumer reads it); these rows carry the state that text acquires.

REQUIREMENT_STATUSES = ("pending", "satisfied", "unmet")


class PirRequirement(Base):
    __tablename__ = "pir_requirements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pir_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
        comment="Position in Pir.eeis — the element this row carries state for")
    text: Mapped[str] = mapped_column(Text, default="",
        comment="The EEI as written, copied from Pir.eeis so a renamed element is detectable")

    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True,
        comment="pending | satisfied | unmet — unmet means tried and given up on, not untried")
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False,
        comment="Collection attempts spent. The circuit breaker: an element still "
                "unanswered after the cap is marked unmet and the run moves on.")
    next_queries: Mapped[list] = mapped_column(JSONB, default=list,
        comment="Search queries the assessor proposed for the gap, used by the next pass")

    assessment_missing: Mapped[str] = mapped_column(Text, default="",
        comment="What the assessor said is still absent — the analyst-facing gap")
    assessment_confidence: Mapped[str] = mapped_column(String(16), default="",
        comment="high | medium | low | unknown")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_pir_requirements_pir_status", "pir_id", "status"),
    )


# ---------------------------------------------------------------------------
# Collection Plan — the nerve center
# ---------------------------------------------------------------------------

class CollectionPlan(Base):
    __tablename__ = "collection_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")

    # Intelligence requirement
    requirement: Mapped[str] = mapped_column(Text, default="",
        comment="The intelligence question or gap this collection addresses")
    pir: Mapped[str] = mapped_column(Text, default="",
        comment="Priority Intelligence Requirement text")
    refined_pir: Mapped[str] = mapped_column(Text, default="")
    # Link back to the first-class PIR this plan was raised against. Deliberately
    # a bare UUID (no FK constraint): collection_plans predates the pirs table on
    # existing deployments, where the column is added by the additive migration in
    # db/engine.py — a constraint would only exist on freshly created databases.
    # Unlinking on PIR delete is done explicitly in api/routes/pirs.py.
    pir_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True,
        comment="pirs.id this plan was generated for, if any")

    # Status lifecycle
    status: Mapped[str] = mapped_column(
        String(20), default=PlanStatus.DRAFT, nullable=False, index=True)

    # Routing rules — where does acquired data go?
    routing_rules: Mapped[dict | None] = mapped_column(JSONB, default=dict,
        comment="e.g. {extract_entities: true, target_project: 'xxx', store_documents: true}")

    # Ownership
    created_by: Mapped[str] = mapped_column(String(128), default="system")
    assigned_to: Mapped[str] = mapped_column(String(128), default="")

    # Schedule (for the plan as a whole — individual sources can override)
    schedule_cron: Mapped[str] = mapped_column(String(128), default="",
        comment="Cron expression for recurring collection, empty for one-time")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    sources: Mapped[list[CollectionSource]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", lazy="selectin")

    __table_args__ = (
        Index("ix_plan_project_status", "project_id", "status"),
    )


# ---------------------------------------------------------------------------
# Collection Source — a source assigned to a plan
# ---------------------------------------------------------------------------

class CollectionSource(Base):
    __tablename__ = "collection_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection_plans.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False,
        comment="file_upload | web_scrape | api_feed | database | rss_feed | watched_dir")

    # Source-specific configuration (schema varies by type)
    config: Mapped[dict] = mapped_column(JSONB, default=dict,
        comment="Type-specific params: url, selectors, query, file_format, etc.")

    # Per-source scheduling (overrides plan schedule if set)
    schedule_cron: Mapped[str] = mapped_column(String(128), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Collection status tracking
    collection_status: Mapped[str] = mapped_column(
        String(20), default="pending",
        comment="pending | queued | collecting | succeeded | failed | skipped | awaiting_upload")

    # Coverage tracking
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    total_records_acquired: Mapped[int] = mapped_column(Integer, default=0)
    acquisition_count: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    plan: Mapped[CollectionPlan] = relationship(back_populates="sources")
    acquisitions: Mapped[list[AcquisitionLog]] = relationship(
        back_populates="source", cascade="all, delete-orphan", lazy="noload")

    __table_args__ = (
        Index("ix_source_plan", "plan_id"),
        Index("ix_source_type", "source_type"),
    )


# ---------------------------------------------------------------------------
# Acquisition Log — every fetch attempt
# ---------------------------------------------------------------------------

class AcquisitionLog(Base):
    __tablename__ = "acquisition_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection_sources.id", ondelete="CASCADE"), nullable=False)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection_plans.id", ondelete="CASCADE"), nullable=False)

    result: Mapped[str] = mapped_column(String(20), nullable=False,
        comment="SUCCESS | FAILURE | PARTIAL | SKIPPED")
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")

    # Provenance
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_config_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict,
        comment="Snapshot of config at acquisition time for reproducibility")
    data_catalog_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_catalog.id", ondelete="SET NULL"), nullable=True)

    # Downstream routing results
    entities_created: Mapped[int] = mapped_column(Integer, default=0)
    relationships_created: Mapped[int] = mapped_column(Integer, default=0)
    document_id: Mapped[str] = mapped_column(String(64), default="",
        comment="Neo4j Document entity ID if routed to graph")

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    source: Mapped[CollectionSource] = relationship(back_populates="acquisitions")

    __table_args__ = (
        Index("ix_acqlog_source", "source_id"),
        Index("ix_acqlog_plan", "plan_id"),
        Index("ix_acqlog_started", "started_at"),
    )


# ---------------------------------------------------------------------------
# Collection Activity — event log for collection progress tracking
# ---------------------------------------------------------------------------

class CollectionActivity(Base):
    __tablename__ = "collection_activity"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection_plans.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection_sources.id", ondelete="CASCADE"), nullable=True)

    event: Mapped[str] = mapped_column(String(32), nullable=False,
        comment="plan_started | source_queued | source_collecting | source_succeeded | source_failed | plan_completed")
    message: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_activity_plan", "plan_id"),
        Index("ix_activity_created", "created_at"),
    )


# ---------------------------------------------------------------------------
# Data Catalog — metadata for ingested structured datasets
# ---------------------------------------------------------------------------

class DataCatalog(Base):
    __tablename__ = "data_catalog"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection_plans.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collection_sources.id", ondelete="CASCADE"), nullable=False)

    # Dataset identity
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    file_format: Mapped[str] = mapped_column(String(32), default="",
        comment="csv, xlsx, json, jsonl, xml, parquet")
    original_filename: Mapped[str] = mapped_column(String(512), default="")
    file_size_bytes: Mapped[int] = mapped_column(Integer, default=0)

    # Schema and profiling
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    column_count: Mapped[int] = mapped_column(Integer, default=0)
    schema_info: Mapped[dict] = mapped_column(JSONB, default=dict,
        comment="Column names, inferred types, sample values")
    profiling: Mapped[dict] = mapped_column(JSONB, default=dict,
        comment="Null rates, value distributions, date ranges, uniqueness")
    preview_rows: Mapped[list] = mapped_column(JSONB, default=list,
        comment="First N rows for analyst preview")

    # Storage reference
    storage_path: Mapped[str] = mapped_column(String(1024), default="",
        comment="Path to stored data (local file or blob reference)")
    storage_format: Mapped[str] = mapped_column(String(32), default="jsonl",
        comment="Internal storage format")

    # Provenance
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_catalog_plan", "plan_id"),
        Index("ix_catalog_source", "source_id"),
    )


# ---------------------------------------------------------------------------
# Chunk Embeddings — pgvector-backed semantic search
# ---------------------------------------------------------------------------

class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True,
        comment="Neo4j Document entity ID")
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1536), nullable=False) if Vector else mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict,
        comment="source_url, chunk_size, etc.")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_chunk_project", "project_id"),
        Index("ix_chunk_document", "document_id"),
    )


# ---------------------------------------------------------------------------
# ATT&CK Technique Embeddings — pgvector index of the global MITRE ATT&CK®
# technique catalog, for RAG text→technique mapping (Phase 2). Keyed by the
# canonical technique id (global reference data, not per-project); upserted by
# POST /attack/embed. Mirrors ChunkEmbedding's Vector(1536) dimension handling.
# ---------------------------------------------------------------------------

class AttackTechniqueEmbedding(Base):
    __tablename__ = "attack_technique_embeddings"

    technique_id: Mapped[str] = mapped_column(String(32), primary_key=True,
        comment="Canonical ATT&CK technique id, e.g. T1566 or T1566.001")
    text: Mapped[str] = mapped_column(Text, nullable=False,
        comment="Embedded text: '<name>. <description>'")
    embedding = mapped_column(Vector(1536), nullable=False) if Vector else mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# ATT&CK D3FEND cache — per-technique defensive countermeasures fetched lazily
# from D3FEND (Phase 3b). Keyed by the canonical technique id; the parsed
# countermeasures are cached with a fetched_at stamp and re-fetched once older
# than attack_d3fend_ttl_days. Mirrors the enrichment cache's fetch-spare role.
# ---------------------------------------------------------------------------

class AttackD3fendCache(Base):
    __tablename__ = "attack_d3fend_cache"

    technique_id: Mapped[str] = mapped_column(String(32), primary_key=True,
        comment="Canonical ATT&CK technique id, e.g. T1566 or T1566.001")
    countermeasures: Mapped[list] = mapped_column(JSONB, default=list,
        comment="Parsed D3FEND countermeasures: [{id, label}]")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        comment="When this technique's D3FEND mapping was last fetched (TTL basis)")


# ---------------------------------------------------------------------------
# Topic Edits — user modifications overlaid on algorithmic topic tree
# ---------------------------------------------------------------------------

class TopicEdit(Base):
    __tablename__ = "topic_edits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    node_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True,
        comment="Algorithmic topic node ID (e.g. topic-0-1)")
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    edit_type: Mapped[str] = mapped_column(String(20), nullable=False,
        comment="rename | add | delete | move")
    name: Mapped[str] = mapped_column(String(512), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[str] = mapped_column(String(128), default="",
        comment="For move/add operations — target parent node ID")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_topic_edit_node_project", "node_id", "project_id"),
    )
