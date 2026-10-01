"""Countable degraded outcomes.

A degraded outcome is a request or a job that completed, but worse than asked:
a chunk extracted by NLP because the model failed, a document stored without
its embeddings, an enrichment provider that errored, a topic left with its
algorithmic label. Each call site already logs it; what was missing was a count
an operator can read without grepping logs, so a quiet provider outage shows up
as a number rather than as results that are merely thinner than they should be.

Counts are per process and since process start (`since`): they reset on
restart, and the collection worker keeps its own. ``/health`` exposes totals
per subsystem; ``GET /api/admin/degraded`` the full breakdown by reason.

Subsystems in use: ``extraction``, ``embeddings``, ``enrichment``, ``llm``,
``topics``, ``attack_mapping``, ``collection``.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SUBSYSTEMS = ("extraction", "embeddings", "enrichment", "llm", "topics", "attack_mapping", "collection")

# Reasons are meant to be a small vocabulary ("provider_error", "unparsed", an
# exception type). A caller that passes something unbounded must not grow the
# table without limit, so past this many distinct reasons in one subsystem the
# rest are counted under OVERFLOW_REASON.
MAX_REASONS_PER_SUBSYSTEM = 50
MAX_REASON_LENGTH = 80
OVERFLOW_REASON = "other"

_lock = threading.Lock()
_counts: dict[str, dict[str, int]] = {}
_since = datetime.now(timezone.utc)


def _clean(value: str, fallback: str) -> str:
    value = " ".join(str(value or "").split())[:MAX_REASON_LENGTH]
    return value or fallback


def record_degraded(subsystem: str, reason: str, *, detail: str = "") -> None:
    """Count one degraded outcome of ``subsystem`` for ``reason``.

    ``reason`` is what is counted, so keep it short and stable (no ids, no
    exception messages). ``detail`` goes to the log line only — it is never
    counted or returned by the API. Never raises: telemetry must not turn a
    degraded outcome into a failed one.
    """
    try:
        subsystem = _clean(subsystem, "unknown")
        reason = _clean(reason, "unspecified")
        with _lock:
            reasons = _counts.setdefault(subsystem, {})
            if reason not in reasons and len(reasons) >= MAX_REASONS_PER_SUBSYSTEM:
                reason = OVERFLOW_REASON
            reasons[reason] = reasons.get(reason, 0) + 1
        logger.info("degraded %s: %s%s", subsystem, reason, f" ({detail})" if detail else "")
    except Exception:  # pragma: no cover - defensive
        logger.debug("record_degraded failed", exc_info=True)


def snapshot() -> dict[str, dict[str, int] | str]:
    """Every count since process start: ``{subsystem: {reason: count}}`` plus
    ``since`` (ISO-8601, UTC). Only subsystems that degraded at least once appear."""
    with _lock:
        out: dict[str, dict[str, int] | str] = {name: dict(reasons) for name, reasons in _counts.items()}
    out["since"] = _since.isoformat()
    return out


def totals() -> dict[str, int]:
    """``{subsystem: total}`` across reasons — the /health summary."""
    with _lock:
        return {name: sum(reasons.values()) for name, reasons in _counts.items()}


def reset() -> None:
    """Forget every count and restart ``since`` (tests)."""
    global _since
    with _lock:
        _counts.clear()
        _since = datetime.now(timezone.utc)
