"""Temporal views over a project's graph.

`/timeline` is the chronological list. `/timeline/histogram` buckets the same
data for the brush filter above the network graph, and reports how much of the
graph carries a real date at all — without that number a sparse histogram looks
like a quiet period rather than an undated corpus.
"""
from collections import Counter
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from intel_platform.api.deps import get_graph_store, known_project, verify_api_key
from intel_platform.graph.store import GraphStore
from intel_platform.services.text_utils import normalize_datetime

router = APIRouter(dependencies=[Depends(verify_api_key)])

# Buckets coarser than a day, because most extracted dates are month- or
# year-precision. Bucketing those by day puts every month-only date on the 1st.
_BUCKETS = ("day", "month", "year")

_SYSTEM_TYPES = frozenset({"Document", "Topic", "Report", "Collection"})


@router.get("/timeline")
def get_timeline(
    project_id: str = Depends(known_project),
    store: GraphStore = Depends(get_graph_store),
):
    """Get a timeline of entities and events, ordered by real event date when known.

    Entities with a populated ``event_datetime`` (extraction resolved a real-world
    date from the source text) are timestamped and labeled by that; everything
    else falls back to ``created_at`` (ingestion time) — the same fallback
    pattern geo.py's entity-timeline endpoint uses.
    """
    entities = store.search_entities(project_id=project_id, limit=500)

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

    # Sort by timestamp
    timeline_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {"events": timeline_events, "count": len(timeline_events)}


def _bucket_key(dt: datetime, bucket: str) -> str:
    if bucket == "year":
        return f"{dt.year:04d}"
    if bucket == "month":
        return f"{dt.year:04d}-{dt.month:02d}"
    return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"


@router.get("/timeline/histogram")
def get_timeline_histogram(
    project_id: str = Depends(known_project),
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
    }
