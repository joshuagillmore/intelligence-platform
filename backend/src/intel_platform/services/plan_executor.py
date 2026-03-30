"""Plan executor — orchestrates autonomous collection for all sources in a plan.

Runs as an asyncio background task. For each enabled source with valid config:
1. Acquire data via the registered connector
2. Store as Document in Neo4j
3. Run entity extraction → build knowledge graph
4. Embed chunks in pgvector for semantic search
5. Log provenance to AcquisitionLog
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from intel_platform.connectors.base import get_connector, CONNECTOR_REGISTRY
from intel_platform.db.models import (
    AcquisitionLog,
    CollectionPlan,
    CollectionSource,
    PlanStatus,
)
from intel_platform.graph.store import GraphStore

logger = logging.getLogger(__name__)

# Module-level execution tracking for status polling
_running_executions: dict[str, dict] = {}


def get_execution_status(plan_id: str) -> dict | None:
    """Get the current execution status for a plan."""
    return _running_executions.get(plan_id)


async def execute_plan(
    plan_id: str,
    db_factory: async_sessionmaker[AsyncSession],
    store: GraphStore,
    extraction_mode: str = "nlp",
) -> dict:
    """Execute all sources in a collection plan autonomously.

    Designed to run as asyncio.create_task() — creates its own DB session
    since the request session is closed after the response is sent.
    """
    execution_id = str(uuid.uuid4())
    _running_executions[plan_id] = {
        "execution_id": execution_id,
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "sources_total": 0,
        "sources_completed": 0,
        "sources_failed": 0,
        "sources_skipped": 0,
        "total_records": 0,
        "total_entities": 0,
        "total_relationships": 0,
        "errors": [],
        "source_results": [],
    }

    try:
        async with db_factory() as db:
            plan = await db.get(CollectionPlan, uuid.UUID(plan_id))
            if not plan:
                _running_executions[plan_id]["status"] = "error"
                _running_executions[plan_id]["errors"].append("Plan not found")
                return _running_executions[plan_id]

            sources = plan.sources or []
            status = _running_executions[plan_id]
            status["sources_total"] = len(sources)

            for source in sources:
                if not source.enabled:
                    status["sources_skipped"] += 1
                    continue

                # Skip file_upload sources (require manual upload)
                if source.source_type == "file_upload":
                    status["sources_skipped"] += 1
                    status["source_results"].append({
                        "source_id": str(source.id),
                        "source_name": source.name,
                        "result": "skipped",
                        "reason": "file_upload requires manual upload",
                    })
                    continue

                # Check if connector is registered
                if source.source_type not in CONNECTOR_REGISTRY:
                    status["sources_skipped"] += 1
                    status["source_results"].append({
                        "source_id": str(source.id),
                        "source_name": source.name,
                        "result": "skipped",
                        "reason": f"No connector for {source.source_type}",
                    })
                    continue

                # Check if config has required fields
                config = source.config or {}
                if not _has_valid_config(source.source_type, config):
                    status["sources_skipped"] += 1
                    status["source_results"].append({
                        "source_id": str(source.id),
                        "source_name": source.name,
                        "result": "skipped",
                        "reason": "Missing required config (url/feed_url/base_url)",
                    })
                    await _log_acquisition(
                        db, source, plan, "SKIPPED", error_message="Missing required config",
                    )
                    continue

                # Execute this source
                result = await _execute_source(
                    source, plan, db, store, extraction_mode,
                )
                status["source_results"].append(result)

                if result.get("result") == "success":
                    status["sources_completed"] += 1
                    status["total_records"] += result.get("record_count", 0)
                    status["total_entities"] += result.get("entities_created", 0)
                    status["total_relationships"] += result.get("relationships_created", 0)
                else:
                    status["sources_failed"] += 1
                    if result.get("error"):
                        status["errors"].append(f"{source.name}: {result['error']}")

            # Mark plan complete if all sources processed
            plan.status = PlanStatus.COMPLETED
            plan.updated_at = datetime.now(timezone.utc)
            await db.commit()

            status["status"] = "completed"
            status["completed_at"] = datetime.now(timezone.utc).isoformat()

    except Exception as e:
        logger.exception("Plan execution failed for %s", plan_id)
        _running_executions[plan_id]["status"] = "error"
        _running_executions[plan_id]["errors"].append(str(e))

    return _running_executions[plan_id]


async def _execute_source(
    source: CollectionSource,
    plan: CollectionPlan,
    db: AsyncSession,
    store: GraphStore,
    extraction_mode: str,
) -> dict:
    """Execute a single source: acquire → extract → graph → log."""
    start_time = time.time()
    source_result = {
        "source_id": str(source.id),
        "source_name": source.name,
        "source_type": source.source_type,
    }

    try:
        # 1. Acquire data via connector
        connector = get_connector(source.source_type)
        acquire_result = await connector.acquire(
            source.config or {}, since=source.last_success_at,
        )

        if not acquire_result.success:
            source_result["result"] = "failure"
            source_result["error"] = acquire_result.error
            await _log_acquisition(
                db, source, plan, "FAILURE",
                error_message=acquire_result.error,
                start_time=start_time,
            )
            source.last_failure_at = datetime.now(timezone.utc)
            source.last_error = acquire_result.error
            source.acquisition_count += 1
            await db.commit()
            return source_result

        records = acquire_result.records
        if not records:
            source_result["result"] = "success"
            source_result["record_count"] = 0
            await _log_acquisition(
                db, source, plan, "SUCCESS", record_count=0, start_time=start_time,
            )
            return source_result

        # 2. Convert records to text
        text_content = _records_to_text(records, source)

        if not text_content.strip():
            source_result["result"] = "success"
            source_result["record_count"] = len(records)
            await _log_acquisition(
                db, source, plan, "SUCCESS", record_count=len(records), start_time=start_time,
            )
            return source_result

        # 3. Store as Document in Neo4j
        from intel_platform.models.entities import Document
        doc = Document(
            name=f"[Collection] {source.name}",
            content=text_content,
            reliability_rating="C3",
            project_id=plan.project_id,
        )
        await asyncio.to_thread(store.create_entity, doc)

        # 4. Chunk and extract entities
        from intel_platform.services.ingestion import ingest_text
        from intel_platform.config import settings

        chunks = ingest_text(text_content, settings.chunk_size, settings.chunk_overlap)

        all_entities = []
        all_rels = []
        for chunk in chunks:
            ents, rels = await _extract(chunk["content"], doc.id, extraction_mode)
            all_entities.extend(ents)
            all_rels.extend(rels)

        # 5. Build knowledge graph
        entities_created = 0
        relationships_created = 0
        if all_entities or all_rels:
            from intel_platform.services.graph_builder import build_graph_from_extractions
            build_result = await asyncio.to_thread(
                build_graph_from_extractions,
                store, all_entities, all_rels, plan.project_id,
                source_doc_id=doc.id,
            )
            entities_created = build_result.get("entities_created", 0)
            relationships_created = build_result.get("relationships_created", 0)

        # 6. Embed chunks for vector search (non-fatal)
        try:
            from intel_platform.services.vector_search import embed_and_store_chunks
            await embed_and_store_chunks(chunks, doc.id, plan.project_id, db)
        except Exception:
            logger.debug("Embedding failed for source %s — non-fatal", source.name)

        # 7. Log acquisition
        await _log_acquisition(
            db, source, plan, "SUCCESS",
            record_count=len(records),
            entities_created=entities_created,
            relationships_created=relationships_created,
            document_id=doc.id,
            start_time=start_time,
        )

        # 8. Update source tracking
        source.last_success_at = datetime.now(timezone.utc)
        source.last_error = ""
        source.total_records_acquired += len(records)
        source.acquisition_count += 1
        await db.commit()

        source_result["result"] = "success"
        source_result["record_count"] = len(records)
        source_result["entities_created"] = entities_created
        source_result["relationships_created"] = relationships_created
        source_result["document_id"] = doc.id

    except Exception as e:
        logger.exception("Source execution failed: %s", source.name)
        source_result["result"] = "failure"
        source_result["error"] = str(e)
        try:
            await _log_acquisition(
                db, source, plan, "FAILURE",
                error_message=str(e), start_time=start_time,
            )
            source.last_failure_at = datetime.now(timezone.utc)
            source.last_error = str(e)
            source.acquisition_count += 1
            await db.commit()
        except Exception:
            pass

    return source_result


def _records_to_text(records: list[dict], source: CollectionSource) -> str:
    """Convert acquired records to text for entity extraction.

    Web/RSS records have a 'content' field → concatenate directly.
    Structured API records → tabular format.
    """
    parts = []
    for record in records:
        content = record.get("content", "")
        title = record.get("title", "")
        url = record.get("url", "")

        if content:
            header = ""
            if title:
                header += f"Title: {title}\n"
            if url:
                header += f"Source: {url}\n"
            if header:
                parts.append(f"{header}\n{content}")
            else:
                parts.append(content)
        else:
            # Structured record — format as key: value pairs
            kv_parts = []
            for k, v in record.items():
                if k.startswith("_") or v is None or str(v).strip() == "":
                    continue
                kv_parts.append(f"{k}: {v}")
            if kv_parts:
                parts.append(". ".join(kv_parts) + ".")

    return f"\n\n---\n\n".join(parts)


async def _extract(text: str, doc_id: str, mode: str):
    """Run entity extraction — delegates to the configured mode."""
    if mode == "llm":
        from intel_platform.services.extraction import extract_entities_llm
        return await extract_entities_llm(text, doc_id)
    elif mode == "hybrid":
        from intel_platform.services.extraction import extract_entities_hybrid
        return await extract_entities_hybrid(text, doc_id)
    else:
        from intel_platform.services.extraction import extract_entities_nlp
        return extract_entities_nlp(text, doc_id)


async def _log_acquisition(
    db: AsyncSession,
    source: CollectionSource,
    plan: CollectionPlan,
    result: str,
    record_count: int = 0,
    entities_created: int = 0,
    relationships_created: int = 0,
    document_id: str = "",
    error_message: str = "",
    start_time: float | None = None,
) -> None:
    """Create an AcquisitionLog record."""
    now = datetime.now(timezone.utc)
    started = datetime.fromtimestamp(start_time, tz=timezone.utc) if start_time else now
    duration = int((time.time() - start_time) * 1000) if start_time else 0

    log = AcquisitionLog(
        source_id=source.id,
        plan_id=plan.id,
        result=result,
        record_count=record_count,
        error_message=error_message,
        source_type=source.source_type,
        source_config_snapshot=source.config or {},
        entities_created=entities_created,
        relationships_created=relationships_created,
        document_id=document_id,
        started_at=started,
        completed_at=now,
        duration_ms=duration,
    )
    db.add(log)
    await db.flush()


def _has_valid_config(source_type: str, config: dict) -> bool:
    """Check if a source has the minimum required config to execute."""
    if source_type == "web_scrape":
        return bool(config.get("url"))
    elif source_type == "rss_feed":
        return bool(config.get("feed_url"))
    elif source_type == "api_feed":
        return bool(config.get("base_url"))
    elif source_type == "file_upload":
        return True  # always valid, just requires manual upload
    return False
