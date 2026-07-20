"""Enrichment cache + rate limiter.

``EnrichmentCache`` persists external-lookup results in Postgres
(``EnrichmentRecord``) keyed by ``(provider, observable)`` with a per-provider
TTL — it is both the cache that spares repeat external calls and the audit
trail of every call made.

``RateLimiter`` is an in-process token-bucket limiter keyed by provider name,
so a quota-limited API (ip-api.com at 45/min, NVD's small keyless window) is
not hammered. It is deliberately in-process — no Redis is wired into this
deployment; a future Redis-backed limiter can replace it behind ``acquire()``.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_fresh(expires_at: datetime | None, now: datetime) -> bool:
    """A cached record is fresh if it never expires or expires in the future."""
    return expires_at is None or expires_at > now


class TokenBucket:
    """Classic token bucket. ``clock`` is injectable for deterministic tests."""

    def __init__(self, rate_per_sec: float, capacity: float, clock=time.monotonic):
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = float(capacity)
        self._clock = clock
        self._updated = clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._updated
        if elapsed > 0:
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self._updated = now

    def try_acquire(self, n: float = 1) -> bool:
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def time_until(self, n: float = 1) -> float:
        """Seconds until ``n`` tokens are available (0 if available now)."""
        self._refill()
        if self.tokens >= n:
            return 0.0
        return (n - self.tokens) / self.rate if self.rate > 0 else float("inf")


class RateLimiter:
    """Per-key token buckets. ``acquire`` awaits until a token is available."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._buckets: dict[str, TokenBucket] = {}

    def _bucket(self, key: str, rate: float, capacity: float) -> TokenBucket:
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(rate, capacity, clock=self._clock)
            self._buckets[key] = bucket
        return bucket

    def try_acquire(self, key: str, *, rate: float, capacity: float, n: float = 1) -> bool:
        return self._bucket(key, rate, capacity).try_acquire(n)

    async def acquire(self, key: str, *, rate: float, capacity: float, n: float = 1) -> None:
        bucket = self._bucket(key, rate, capacity)
        while not bucket.try_acquire(n):
            await asyncio.sleep(bucket.time_until(n))


class EnrichmentCache:
    """Postgres-backed cache/audit for enrichment lookups.

    ``session_factory`` is injectable for tests; defaults to the app factory.
    """

    def __init__(self, session_factory=None):
        self._factory = session_factory

    def _get_factory(self):
        if self._factory is not None:
            return self._factory
        from intel_platform.db.engine import get_session_factory
        return get_session_factory()

    async def get(self, provider: str, observable: str) -> dict | None:
        """Return the cached payload if present and fresh, else None."""
        from sqlalchemy import select

        from intel_platform.db.models import EnrichmentRecord

        factory = self._get_factory()
        async with factory() as session:
            result = await session.execute(
                select(EnrichmentRecord).where(
                    EnrichmentRecord.provider == provider,
                    EnrichmentRecord.observable == observable,
                )
            )
            row = result.scalar_one_or_none()
        if row is not None and _is_fresh(row.expires_at, _now()):
            return row.payload
        return None

    async def set(self, provider: str, observable: str, payload: dict, *,
                  entity_type: str = "", source_url: str = "",
                  ttl: timedelta | None = None) -> None:
        """Upsert a lookup result, stamping fetched_at and (ttl → expires_at)."""
        from sqlalchemy import select

        from intel_platform.db.models import EnrichmentRecord

        now = _now()
        expires = now + ttl if ttl is not None else None
        factory = self._get_factory()
        async with factory() as session:
            result = await session.execute(
                select(EnrichmentRecord).where(
                    EnrichmentRecord.provider == provider,
                    EnrichmentRecord.observable == observable,
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                row.payload = payload
                row.entity_type = entity_type or row.entity_type
                row.source_url = source_url or row.source_url
                row.fetched_at = now
                row.expires_at = expires
            else:
                session.add(EnrichmentRecord(
                    provider=provider, observable=observable, payload=payload,
                    entity_type=entity_type, source_url=source_url,
                    fetched_at=now, expires_at=expires,
                ))
            await session.commit()
