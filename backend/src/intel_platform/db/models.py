"""SQLAlchemy models for collection management system.

Tables:
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
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PlanStatus(str):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


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
