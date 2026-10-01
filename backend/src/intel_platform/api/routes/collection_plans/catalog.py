"""What collection plans have acquired: the acquisition log, the data catalog,
the project dashboard and the connector types a source can use.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from intel_platform.api.routes.collection_plans.plans import _parse_uuid
from intel_platform.connectors.base import CONNECTOR_REGISTRY
from intel_platform.db.engine import get_db
from intel_platform.db.models import AcquisitionLog, CollectionPlan, CollectionSource, DataCatalog

# Mounted by the package router, which carries the API-key dependency.
router = APIRouter()


def _log_to_dict(log: AcquisitionLog) -> dict:
    return {
        "id": str(log.id),
        "source_id": str(log.source_id),
        "plan_id": str(log.plan_id),
        "result": log.result,
        "record_count": log.record_count,
        "error_message": log.error_message,
        "source_type": log.source_type,
        "entities_created": log.entities_created,
        "relationships_created": log.relationships_created,
        "document_id": log.document_id,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        "duration_ms": log.duration_ms,
    }


def _catalog_to_dict(cat: DataCatalog) -> dict:
    return {
        "id": str(cat.id),
        "plan_id": str(cat.plan_id),
        "source_id": str(cat.source_id),
        "name": cat.name,
        "file_format": cat.file_format,
        "original_filename": cat.original_filename,
        "file_size_bytes": cat.file_size_bytes,
        "row_count": cat.row_count,
        "column_count": cat.column_count,
        "schema_info": cat.schema_info or {},
        "profiling": cat.profiling or {},
        "preview_rows": cat.preview_rows or [],
        "ingested_at": cat.ingested_at.isoformat() if cat.ingested_at else None,
    }


# ---------------------------------------------------------------------------
# Acquisition log
# ---------------------------------------------------------------------------

@router.get("/collection-plans/{plan_id}/acquisitions")
async def list_acquisitions(
    plan_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(AcquisitionLog)
        .where(AcquisitionLog.plan_id == _parse_uuid(plan_id, "plan_id"))
        .order_by(AcquisitionLog.started_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [_log_to_dict(log) for log in result.scalars().all()]


@router.get("/collection-plans/{plan_id}/sources/{source_id}/acquisitions")
async def list_source_acquisitions(
    plan_id: str,
    source_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(AcquisitionLog)
        .where(AcquisitionLog.source_id == _parse_uuid(source_id, "source_id"))
        .order_by(AcquisitionLog.started_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [_log_to_dict(log) for log in result.scalars().all()]


# ---------------------------------------------------------------------------
# Data catalog
# ---------------------------------------------------------------------------

@router.get("/collection-plans/{plan_id}/catalog")
async def list_catalog(plan_id: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(DataCatalog)
        .where(DataCatalog.plan_id == _parse_uuid(plan_id, "plan_id"))
        .order_by(DataCatalog.ingested_at.desc())
    )
    result = await db.execute(stmt)
    return [_catalog_to_dict(c) for c in result.scalars().all()]


@router.get("/data-catalog/{catalog_id}")
async def get_catalog_entry(catalog_id: str, db: AsyncSession = Depends(get_db)):
    entry = await db.get(DataCatalog, _parse_uuid(catalog_id, "catalog_id"))
    if not entry:
        raise HTTPException(404, "Catalog entry not found")
    return _catalog_to_dict(entry)


@router.get("/data-catalog/{catalog_id}/preview")
async def get_catalog_preview(
    catalog_id: str,
    offset: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(DataCatalog, _parse_uuid(catalog_id, "catalog_id"))
    if not entry:
        raise HTTPException(404, "Catalog entry not found")
    rows = entry.preview_rows or []
    return {
        "rows": rows[offset:offset + limit],
        "total": len(rows),
        "offset": offset,
        "schema": entry.schema_info,
    }


# ---------------------------------------------------------------------------
# Collection dashboard — summary stats across all plans for a project
# ---------------------------------------------------------------------------

@router.get("/collection-dashboard")
async def collection_dashboard(project_id: str, db: AsyncSession = Depends(get_db)):
    """Dashboard summary: plan counts, recent acquisitions, source health."""
    # Plan counts by status
    plan_counts_stmt = (
        select(CollectionPlan.status, func.count())
        .where(CollectionPlan.project_id == project_id)
        .group_by(CollectionPlan.status)
    )
    plan_counts_result = await db.execute(plan_counts_stmt)
    plan_counts = {row[0]: row[1] for row in plan_counts_result}

    # Total sources and their health
    sources_stmt = (
        select(CollectionSource)
        .join(CollectionPlan)
        .where(CollectionPlan.project_id == project_id)
    )
    sources_result = await db.execute(sources_stmt)
    sources = sources_result.scalars().all()

    healthy_sources = sum(1 for s in sources if s.enabled and not s.last_error)
    unhealthy_sources = sum(1 for s in sources if s.enabled and s.last_error)
    disabled_sources = sum(1 for s in sources if not s.enabled)

    # Recent acquisitions (last 10)
    recent_acq_stmt = (
        select(AcquisitionLog)
        .join(CollectionPlan, AcquisitionLog.plan_id == CollectionPlan.id)
        .where(CollectionPlan.project_id == project_id)
        .order_by(AcquisitionLog.started_at.desc())
        .limit(10)
    )
    recent_acq_result = await db.execute(recent_acq_stmt)
    recent_acquisitions = [_log_to_dict(a) for a in recent_acq_result.scalars().all()]

    # Total records acquired
    total_records_stmt = (
        select(func.sum(CollectionSource.total_records_acquired))
        .join(CollectionPlan)
        .where(CollectionPlan.project_id == project_id)
    )
    total_records_result = await db.execute(total_records_stmt)
    total_records = total_records_result.scalar() or 0

    return {
        "project_id": project_id,
        "plan_counts": plan_counts,
        "total_plans": sum(plan_counts.values()),
        "source_health": {
            "healthy": healthy_sources,
            "unhealthy": unhealthy_sources,
            "disabled": disabled_sources,
            "total": len(sources),
        },
        "total_records_acquired": total_records,
        "recent_acquisitions": recent_acquisitions,
    }


# ---------------------------------------------------------------------------
# Connector info
# ---------------------------------------------------------------------------

@router.get("/connector-types")
async def list_connector_types():
    """List available connector types and their capabilities."""
    result = []
    for type_name, cls in CONNECTOR_REGISTRY.items():
        result.append({
            "source_type": type_name,
            "description": cls.__doc__ or "",
        })
    return result
