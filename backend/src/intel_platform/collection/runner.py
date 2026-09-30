from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from intel_platform.collection.search import web_search
from intel_platform.collection.crawler import crawl_urls
from intel_platform.collection.proxy import get_active_proxy_config
from intel_platform.config import settings
from intel_platform.graph.store import GraphStore
from intel_platform.models.entities import Document
from intel_platform.services.extraction import extract_entities_nlp
from intel_platform.services.graph_builder import build_graph_from_extractions
from intel_platform.services.ingestion import ingest_text

logger = logging.getLogger(__name__)

# Written only when the analyst cancels. The runner checks for it between items
# and never writes over it.
REVOKED = "REVOKED"


class CollectionRunner:
    """Executes a collection plan: search → crawl → ingest → extract → graph."""

    def __init__(self, store: GraphStore):
        self._store = store

    async def execute(
        self,
        collection_id: str,
        project_id: str,
        plan: list[dict],
        extraction_mode: str = "nlp",
        on_progress: callable = None,
    ) -> dict:
        # A new run replaces whatever an earlier one left, including REVOKED.
        # Every store call here is the sync Neo4j driver, so it runs in a
        # thread: on the loop it stalls every request the API is serving.
        await asyncio.to_thread(self._update_status, collection_id, "STARTED", new_run=True)
        approved_items = [item for item in plan if item.get("approved", False)]
        total_items = len(approved_items)

        # Resolve the active collection-egress proxy once for this run. crawl_urls
        # reads it itself; web_search is sync, so pass the resolved URL through.
        proxy_url = (await get_active_proxy_config()).get_proxy_url()

        all_urls: list[str] = []
        total_docs_crawled = 0
        total_entities = 0
        total_relationships = 0
        errors: list[dict] = []
        items_run = 0
        cancelled = False

        for idx, item in enumerate(approved_items):
            # Cancel sets REVOKED; before this check nothing read it, so every
            # item still ran and SUCCESS was written over the cancellation.
            if await asyncio.to_thread(self._read_status, collection_id) == REVOKED:
                cancelled = True
                logger.info("Collection %s cancelled after %d of %d item(s)", collection_id, idx, total_items)
                break
            items_run += 1

            item_desc = item.get("description", "")
            source_type = item.get("source_type", "web_search")
            item_docs = 0

            try:
                # Stage 1: Search (sync, and it sleeps on rate limits)
                urls = await asyncio.to_thread(self._search_for_item, item_desc, source_type, proxy_url)
                all_urls.extend(urls)

                # Stage 2: Crawl
                documents = await crawl_urls(urls, timeout_ms=30000)

                # Stage 3: Ingest each crawled doc into the graph
                for doc_data in documents:
                    result = await self._ingest_document(
                        doc_data, project_id, collection_id, extraction_mode,
                    )
                    total_docs_crawled += 1
                    item_docs += 1
                    total_entities += result.get("entities_created", 0)
                    total_relationships += result.get("relationships_created", 0)

                if not item_docs:
                    # Search found nothing, or nothing it found could be
                    # crawled. Either way this item collected nothing, and a
                    # run of such items is a failure, not an empty success.
                    reason = "search returned no results" if not urls else f"none of {len(urls)} page(s) could be crawled"
                    errors.append({"item_id": item.get("id", idx), "description": item_desc, "reason": reason})

            except Exception as exc:
                logger.exception("Plan item %d failed: %s", item.get("id", idx), item_desc)
                errors.append({
                    "item_id": item.get("id", idx), "description": item_desc,
                    "reason": type(exc).__name__,
                })

            # Update progress
            progress = (idx + 1) / total_items if total_items > 0 else 1.0
            await asyncio.to_thread(
                self._update_status, collection_id, "PROGRESS",
                progress=progress, documents_acquired=total_docs_crawled,
            )
            if on_progress:
                on_progress(collection_id, progress, total_docs_crawled)

        if cancelled:
            status = REVOKED
        elif items_run and len(errors) == items_run:
            status = "FAILURE"
        elif errors:
            status = "PARTIAL"
        else:
            status = "SUCCESS"

        await asyncio.to_thread(
            self._update_status, collection_id, status,
            progress=1.0 if status != REVOKED else (items_run / total_items if total_items else 1.0),
            documents_acquired=total_docs_crawled,
        )

        return {
            "collection_id": collection_id,
            "status": status,
            "items_processed": items_run,
            "urls_found": len(all_urls),
            "documents_crawled": total_docs_crawled,
            "entities_created": total_entities,
            "relationships_created": total_relationships,
            "errors": errors,
        }

    def _search_for_item(self, description: str, source_type: str, proxy: str | None = None) -> list[str]:
        """Run a web search for a plan item and return URLs."""
        results = web_search(description, max_results=10, proxy=proxy)
        return [r["url"] for r in results if r.get("url")]

    async def _ingest_document(
        self, doc_data: dict, project_id: str, collection_id: str, extraction_mode: str,
    ) -> dict:
        """Create a Document node and run entity extraction."""
        content = doc_data.get("content", "")
        if not content.strip():
            return {"entities_created": 0, "relationships_created": 0}

        # One bound for storage and extraction, as on the agentic path: an
        # unbounded page is hundreds of sequential extraction calls.
        max_chars = getattr(settings, "max_document_chars", 50000)
        if len(content) > max_chars:
            content = content[:max_chars]

        doc = Document(
            name=doc_data.get("title", "") or doc_data.get("url", "untitled"),
            content=content,
            url=doc_data.get("url", ""),
            reliability_rating="C4",
            project_id=project_id,
            source_doc_id=collection_id,
        )
        await asyncio.to_thread(self._store.create_entity, doc)

        chunks = ingest_text(content, chunk_size=settings.chunk_size, overlap=settings.chunk_overlap)

        all_entities: list[dict] = []
        all_relationships: list[dict] = []
        for chunk in chunks:
            if extraction_mode == "llm":
                from intel_platform.services.extraction import extract_entities_llm
                ents, rels = await extract_entities_llm(chunk["content"], doc.id)
            elif extraction_mode == "hybrid":
                from intel_platform.services.extraction import extract_entities_hybrid
                ents, rels = await extract_entities_hybrid(chunk["content"], doc.id)
            else:
                ents, rels = await asyncio.to_thread(extract_entities_nlp, chunk["content"], doc.id)
            all_entities.extend(ents)
            all_relationships.extend(rels)

        result = await asyncio.to_thread(
            build_graph_from_extractions,
            self._store, all_entities, all_relationships, project_id, source_doc_id=doc.id,
        )
        if result.get("dropped_attributes"):
            logger.warning(
                "Graph build for %s dropped %d invalid attribute value(s)",
                doc_data.get("url", "?"), result["dropped_attributes"],
            )
        return result

    def _read_status(self, collection_id: str) -> str | None:
        with self._store._driver.session() as session:
            record = session.run(
                "MATCH (c:Collection {id: $id}) RETURN c.status AS status", id=collection_id,
            ).single()
        return record["status"] if record else None

    def _update_status(
        self, collection_id: str, status: str,
        progress: float = 0.0, documents_acquired: int = 0, new_run: bool = False,
    ) -> None:
        """Persist collection status to Neo4j, never overwriting a cancellation.

        The check and the write are one statement: a cancel landing while an
        item runs must not be replaced by that item's PROGRESS update. Only the
        write that starts a new run (`new_run`) replaces REVOKED.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._store._driver.session() as session:
            session.run(
                """
                MATCH (c:Collection {id: $id})
                SET c.status = CASE WHEN c.status = $revoked AND NOT $new_run
                                    THEN c.status ELSE $status END,
                    c.progress = $progress,
                    c.documents_acquired = $docs, c.updated_at = $now
                """,
                id=collection_id, status=status, revoked=REVOKED, new_run=new_run,
                progress=progress, docs=documents_acquired, now=now,
            )
