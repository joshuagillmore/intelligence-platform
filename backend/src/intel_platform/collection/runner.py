from __future__ import annotations

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
        self._update_status(collection_id, "STARTED")
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

        for idx, item in enumerate(approved_items):
            item_desc = item.get("description", "")
            source_type = item.get("source_type", "web_search")

            try:
                # Stage 1: Search
                urls = self._search_for_item(item_desc, source_type, proxy_url)
                all_urls.extend(urls)

                # Stage 2: Crawl
                documents = await crawl_urls(urls, timeout_ms=30000)

                # Stage 3: Ingest each crawled doc into the graph
                for doc_data in documents:
                    result = await self._ingest_document(
                        doc_data, project_id, collection_id, extraction_mode,
                    )
                    total_docs_crawled += 1
                    total_entities += result.get("entities_created", 0)
                    total_relationships += result.get("relationships_created", 0)

            except Exception:
                logger.exception("Plan item %d failed: %s", item.get("id", idx), item_desc)
                errors.append({"item_id": item.get("id", idx), "description": item_desc})

            # Update progress
            progress = (idx + 1) / total_items if total_items > 0 else 1.0
            self._update_status(
                collection_id, "PROGRESS",
                progress=progress, documents_acquired=total_docs_crawled,
            )
            if on_progress:
                on_progress(collection_id, progress, total_docs_crawled)

        self._update_status(
            collection_id, "SUCCESS",
            progress=1.0, documents_acquired=total_docs_crawled,
        )

        return {
            "collection_id": collection_id,
            "status": "SUCCESS",
            "items_processed": len(approved_items),
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

        doc = Document(
            name=doc_data.get("title", "") or doc_data.get("url", "untitled"),
            content=content,
            url=doc_data.get("url", ""),
            reliability_rating="C4",
            project_id=project_id,
            source_doc_id=collection_id,
        )
        self._store.create_entity(doc)

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
                ents, rels = extract_entities_nlp(chunk["content"], doc.id)
            all_entities.extend(ents)
            all_relationships.extend(rels)

        return build_graph_from_extractions(
            self._store, all_entities, all_relationships, project_id, source_doc_id=doc.id,
        )

    def _update_status(
        self, collection_id: str, status: str,
        progress: float = 0.0, documents_acquired: int = 0,
    ) -> None:
        """Persist collection status to Neo4j."""
        now = datetime.now(timezone.utc).isoformat()
        with self._store._driver.session() as session:
            session.run(
                """
                MATCH (c:Collection {id: $id})
                SET c.status = $status, c.progress = $progress,
                    c.documents_acquired = $docs, c.updated_at = $now
                """,
                id=collection_id, status=status,
                progress=progress, docs=documents_acquired, now=now,
            )
