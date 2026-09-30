from __future__ import annotations
import asyncio
import threading
import time
from collections import OrderedDict
from functools import wraps
from typing import Any

# key -> (expires_at, value), oldest insertion first. Sync endpoints run in the
# threadpool, so every read and write goes through _lock.
_cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
_lock = threading.Lock()
_MISS = object()
DEFAULT_TTL = 30  # seconds
_CACHE_MAX_SIZE = 500  # a hard cap: past it, expired entries go first, then the oldest


def _key_part(value: Any) -> str:
    """How one argument contributes to a cache key.

    Only values that identify the *request* may appear verbatim. FastAPI passes
    dependency-injected services as arguments too — `get_graph_store` returns a
    new `GraphStore(driver)` per request — and their default repr carries the
    object's memory address. Including that made every key unique, so the cache
    stored a copy of every response and never once returned one: `/api/topics`
    took ~20s on all three of three back-to-back calls with `@cached(ttl=60)`
    applied.

    It hid because an address is reused as often as not when the object is
    freed immediately, so a naive check does see hits.

    Non-primitives contribute their type name: two endpoints with different
    service signatures stay distinct, without the identity churn.
    """
    if isinstance(value, (str, int, float, bool, type(None))):
        return repr(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_key_part(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}:{_key_part(v)}" for k, v in sorted(value.items())) + "}"
    return f"<{type(value).__name__}>"


def _make_key(func, args: tuple, kwargs: dict) -> str:
    parts = [func.__module__, func.__qualname__]
    parts += [_key_part(a) for a in args]
    parts += [f"{k}={_key_part(v)}" for k, v in sorted(kwargs.items())]
    return "|".join(parts)


def _lookup(key: str, now: float) -> Any:
    """The cached value, or _MISS when absent or expired (None is a valid value)."""
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return _MISS
        expires_at, value = entry
        if now < expires_at:
            return value
        del _cache[key]
        return _MISS


def _store(key: str, value: Any, ttl: int, now: float) -> None:
    """Insert, then hold the cap: drop expired entries, then the oldest.

    The old eviction removed only expired entries, judged by the inserting
    decorator's TTL, so a burst of fresh keys grew the cache past its cap; and it
    iterated the dict while threadpool calls inserted into it.
    """
    with _lock:
        _cache[key] = (now + ttl, value)
        _cache.move_to_end(key)
        if len(_cache) > _CACHE_MAX_SIZE:
            for expired in [k for k, (expires_at, _) in _cache.items() if expires_at <= now]:
                del _cache[expired]
            while len(_cache) > _CACHE_MAX_SIZE:
                _cache.popitem(last=False)


def cached(ttl: int = DEFAULT_TTL):
    """Simple in-memory cache decorator for endpoint responses.

    Works with both sync and async functions.
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                key = _make_key(func, args, kwargs)
                now = time.time()
                hit = _lookup(key, now)
                if hit is not _MISS:
                    return hit
                result = await func(*args, **kwargs)
                _store(key, result, ttl, now)
                return result
            return async_wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                key = _make_key(func, args, kwargs)
                now = time.time()
                hit = _lookup(key, now)
                if hit is not _MISS:
                    return hit
                result = func(*args, **kwargs)
                _store(key, result, ttl, now)
                return result
            return wrapper
    return decorator


def clear_cache():
    """Clear all cached values."""
    with _lock:
        _cache.clear()
