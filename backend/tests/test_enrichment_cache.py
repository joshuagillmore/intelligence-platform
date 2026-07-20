"""Tests for the enrichment cache + rate limiter (hermetic — no DB, no clock)."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from intel_platform.enrichment.cache import (
    EnrichmentCache,
    RateLimiter,
    TokenBucket,
    _is_fresh,
)

UTC = timezone.utc


# --- freshness / TTL (pure) -------------------------------------------------

def test_is_fresh_no_expiry():
    assert _is_fresh(None, datetime.now(UTC)) is True


def test_is_fresh_future():
    now = datetime.now(UTC)
    assert _is_fresh(now + timedelta(hours=1), now) is True


def test_is_fresh_past():
    now = datetime.now(UTC)
    assert _is_fresh(now - timedelta(seconds=1), now) is False


# --- token bucket / rate limiter (injected clock, deterministic) ------------

def test_token_bucket_allows_up_to_capacity():
    t = [0.0]
    b = TokenBucket(rate_per_sec=1, capacity=2, clock=lambda: t[0])
    assert b.try_acquire() is True
    assert b.try_acquire() is True
    assert b.try_acquire() is False  # empty


def test_token_bucket_refills_over_time():
    t = [0.0]
    b = TokenBucket(rate_per_sec=1, capacity=2, clock=lambda: t[0])
    b.try_acquire()
    b.try_acquire()
    assert b.try_acquire() is False
    t[0] = 1.0  # one second later -> one token back
    assert b.try_acquire() is True


def test_rate_limiter_isolates_keys():
    t = [0.0]
    rl = RateLimiter(clock=lambda: t[0])
    assert rl.try_acquire("a", rate=1, capacity=1) is True
    assert rl.try_acquire("a", rate=1, capacity=1) is False  # a exhausted
    assert rl.try_acquire("b", rate=1, capacity=1) is True   # b independent


async def test_rate_limiter_does_not_hang_on_zero_rate():
    # A misconfigured provider (rate 0) must not make acquire() sleep forever:
    # the first call drains the one token, the second must break out, not hang.
    rl = RateLimiter()
    await asyncio.wait_for(rl.acquire("p", rate=0, capacity=1), timeout=2)
    await asyncio.wait_for(rl.acquire("p", rate=0, capacity=1), timeout=2)


# --- EnrichmentCache get/set (mocked session) -------------------------------

def _factory_with_session(session):
    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    return lambda: _CM()


def _result_returning(row):
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=row)
    return result


async def test_cache_get_returns_fresh_payload():
    row = MagicMock(payload={"ip": "1.2.3.4"}, expires_at=datetime.now(UTC) + timedelta(hours=1))
    session = MagicMock(execute=AsyncMock(return_value=_result_returning(row)))
    cache = EnrichmentCache(session_factory=_factory_with_session(session))
    assert await cache.get("geoip", "1.2.3.4") == {"ip": "1.2.3.4"}


async def test_cache_get_returns_none_when_stale():
    row = MagicMock(payload={"x": 1}, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    session = MagicMock(execute=AsyncMock(return_value=_result_returning(row)))
    cache = EnrichmentCache(session_factory=_factory_with_session(session))
    assert await cache.get("geoip", "1.2.3.4") is None


async def test_cache_get_returns_none_on_miss():
    session = MagicMock(execute=AsyncMock(return_value=_result_returning(None)))
    cache = EnrichmentCache(session_factory=_factory_with_session(session))
    assert await cache.get("geoip", "9.9.9.9") is None


async def test_cache_set_inserts_when_absent():
    session = MagicMock(execute=AsyncMock(return_value=_result_returning(None)),
                        add=MagicMock(), commit=AsyncMock())
    cache = EnrichmentCache(session_factory=_factory_with_session(session))
    await cache.set("geoip", "1.2.3.4", {"asn": "AS1"}, ttl=timedelta(days=1))
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


async def test_cache_set_updates_when_present():
    row = MagicMock()
    session = MagicMock(execute=AsyncMock(return_value=_result_returning(row)),
                        add=MagicMock(), commit=AsyncMock())
    cache = EnrichmentCache(session_factory=_factory_with_session(session))
    await cache.set("geoip", "1.2.3.4", {"asn": "AS2"}, ttl=timedelta(days=1))
    assert row.payload == {"asn": "AS2"}
    session.add.assert_not_called()
    session.commit.assert_awaited_once()
