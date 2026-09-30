"""Temporal views over a project's graph.

`/timeline` is the chronological list. `/timeline/histogram` buckets the same
data for the brush filter above the network graph, and reports how much of the
graph carries a real date at all — without that number a sparse histogram looks
like a quiet period rather than an undated corpus.
"""
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from intel_platform.api.deps import get_graph_store, project_exists, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.text_utils import normalize_datetime

router = APIRouter(dependencies=[Depends(verify_api_key)])

# Buckets coarser than a day, because most extracted dates are month- or
# year-precision. Bucketing those by day puts every month-only date on the 1st.
_BUCKETS = ("day", "month", "year")

_SYSTEM_TYPES = frozenset({"Document", "Topic", "Report", "Collection"})


_TIMELINE_MAX_PAGE = 5000


def _timeline_page(store: GraphStore, project_id: str, limit: int, offset: int) -> tuple[list[dict], int, list[str]]:
    """One page of the project's timeline, newest first, plus the true total and every type present.

    Ordered in Cypher by ``coalesce(event_datetime, created_at)``. The route
    used to take `search_entities(limit=500)` — ordered by *name* — and sort
    that slice by date, so on a large project the timeline was the newest of an
    alphabetical sample and `count` described the sample. Dates are stored as
    ISO-8601 strings, which order chronologically as text; an entity with
    neither date sorts last. Only the fields the timeline shows are returned,
    never a Document's content.

    `search_entities` takes no ordering, hence the direct read.
    """
    with store._driver.session() as session:
        summary = session.run(
            """
            MATCH (n:Entity) WHERE n.project_id = $project_id
            RETURN count(n) AS total, collect(DISTINCT n.entity_type) AS types
            """,
            project_id=project_id,
        ).single()
        rows = session.run(
            """
            MATCH (n:Entity) WHERE n.project_id = $project_id
            WITH n, coalesce(n.event_datetime, n.created_at, '') AS ts
            ORDER BY ts DESC, n.id
            SKIP $offset LIMIT $limit
            RETURN n.id AS id, n.name AS name, n.entity_type AS entity_type,
                   n.event_datetime AS event_datetime, n.created_at AS created_at,
                   n.date_precision AS date_precision, n.date_text AS date_text
            """,
            project_id=project_id, limit=limit, offset=offset,
        )
        entities = [dict(r) for r in rows]
    total = summary["total"] if summary else 0
    types = sorted(t for t in (summary["types"] if summary else []) if t)
    return entities, total, types


@router.get("/timeline")
def get_timeline(
    project_id: str,
    limit: int = Query(500, ge=1, le=_TIMELINE_MAX_PAGE),
    offset: int = Query(0, ge=0),
    store: GraphStore = Depends(get_graph_store),
):
    """Get a timeline of entities and events, newest first by real event date when known.

    Entities with a populated ``event_datetime`` (extraction resolved a real-world
    date from the source text) are timestamped and labeled by that; everything
    else falls back to ``created_at`` (ingestion time) — the same fallback
    pattern geo.py's entity-timeline endpoint uses.

    Returns one page (`count`) of the whole project (`total`), `truncated` when
    more exist past this page, and `types_present` across the whole project so a
    type filter can offer every type rather than a fixed list or the page's.
    """
    entities, total, types_present = _timeline_page(store, project_id, limit, offset)

    timeline_events = []
    for e in entities:
        event_dt = normalize_datetime(e.get("event_datetime"))
        if event_dt:
            timestamp = event_dt
            event_type = "event"
        else:
            timestamp = normalize_datetime(e.get("created_at"))
            event_type = "entity_created"

        timeline_events.append({
            "id": e.get("id", ""),
            "name": e.get("name", ""),
            "entity_type": e.get("entity_type", ""),
            "timestamp": timestamp,
            "event_type": event_type,
            "date_precision": e.get("date_precision", ""),
            "date_text": e.get("date_text", ""),
        })

    # Already in order: sorted server-side across the whole project.
    return {
        "events": timeline_events,
        "count": len(timeline_events),
        "total": total,
        "truncated": offset + len(timeline_events) < total,
        "types_present": types_present,
        "offset": offset,
        # Lets a caller tell "this project has nothing" from "this project is
        # not a project" without changing the response shape.
        "project_exists": project_exists(store, project_id),
    }


def _bucket_key(dt: datetime, bucket: str) -> str:
    if bucket == "year":
        return f"{dt.year:04d}"
    if bucket == "month":
        return f"{dt.year:04d}-{dt.month:02d}"
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


@router.get("/timeline/histogram")
def get_timeline_histogram(
    project_id: str,
    bucket: str = Query("month", pattern="^(day|month|year)$"),
    limit: int = Query(2000, ge=1, le=10000),
    store: GraphStore = Depends(get_graph_store),
):
    """Bucket a project's dated entities for the network-graph brush filter.

    Only entities carrying a real `event_datetime` are counted — ingestion time
    is not a fact about the subject, and including it would draw a histogram of
    when the crawler ran. `undated` is returned alongside so the caller can say
    "42 of 380 entities are dated" rather than implying the rest are absent from
    the period.
    """
    if bucket not in _BUCKETS:
        raise HTTPException(400, f"bucket must be one of {list(_BUCKETS)}")

    entities = store.search_entities(project_id=project_id, limit=limit)

    counts: Counter[str] = Counter()
    by_type: dict[str, Counter[str]] = {}
    dated = 0
    undated = 0
    earliest: datetime | None = None
    latest: datetime | None = None

    for e in entities:
        if e.get("entity_type") in _SYSTEM_TYPES:
            continue
        raw = normalize_datetime(e.get("event_datetime"))
        if not raw:
            undated += 1
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            undated += 1
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        dated += 1
        key = _bucket_key(dt, bucket)
        counts[key] += 1
        etype = e.get("entity_type", "?")
        by_type.setdefault(key, Counter())[etype] += 1
        earliest = dt if earliest is None or dt < earliest else earliest
        latest = dt if latest is None or dt > latest else latest

    return {
        "bucket": bucket,
        "bins": [
            {"key": k, "count": counts[k], "by_type": dict(by_type.get(k, {}))}
            for k in sorted(counts)
        ],
        "dated": dated,
        "undated": undated,
        "earliest": earliest.isoformat() if earliest else None,
        "latest": latest.isoformat() if latest else None,
        "project_exists": project_exists(store, project_id),
    }
