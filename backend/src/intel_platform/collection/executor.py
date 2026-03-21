from __future__ import annotations

from intel_platform.collection.proxy import ProxyConfig
from intel_platform.collection.scraper import WebScraper
from intel_platform.collection.tasks import CollectionManager, TaskStatus


class CollectionExecutor:
    def __init__(self, manager: CollectionManager, proxy_config: ProxyConfig | None = None):
        self._manager = manager
        self._scraper = WebScraper(proxy_config)

    async def execute_plan(self, task_id: str) -> dict:
        task = self._manager.get_task(task_id)
        if not task:
            return {"error": "Task not found"}

        self._manager.update_task(task_id, status=TaskStatus.STARTED)
        results = []
        total = len(task.plan)

        for i, item in enumerate(task.plan):
            try:
                url = item.get("url", "")
                if not url:
                    continue
                result = await self._scraper.scrape_url(url)
                results.append(result)
                progress = (i + 1) / total if total > 0 else 1.0
                self._manager.update_task(
                    task_id,
                    progress=progress,
                    documents_acquired=len(results),
                    status=TaskStatus.PROGRESS,
                )
            except Exception as e:
                results.append({"url": item.get("url", ""), "error": str(e)})

        self._manager.update_task(
            task_id,
            status=TaskStatus.SUCCESS,
            progress=1.0,
            results=results,
            documents_acquired=len([r for r in results if "error" not in r]),
        )
        return {"task_id": task_id, "documents_acquired": len(results), "results": results}
