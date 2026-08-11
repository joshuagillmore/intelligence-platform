from __future__ import annotations
import asyncio
import time
from functools import wraps
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}
DEFAULT_TTL = 30  # seconds
_CACHE_MAX_SIZE = 500  # PERF: cap to prevent unbounded growth


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


def _evict_stale(ttl: int) -> None:
    """Evict expired entries when cache grows large."""
    now = time.time()
    if len(_cache) >= _CACHE_MAX_SIZE:
        stale = [k for k, (t, _) in _cache.items() if now - t >= ttl]
        for k in stale:
            del _cache[k]


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
                if key in _cache:
                    cached_time, cached_value = _cache[key]
                    if now - cached_time < ttl:
                        return cached_value
                result = await func(*args, **kwargs)
                _evict_stale(ttl)
                _cache[key] = (now, result)
                return result
            return async_wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                key = _make_key(func, args, kwargs)
                now = time.time()
                if key in _cache:
                    cached_time, cached_value = _cache[key]
                    if now - cached_time < ttl:
                        return cached_value
                result = func(*args, **kwargs)
                _evict_stale(ttl)
                _cache[key] = (now, result)
                return result
            return wrapper
    return decorator


def clear_cache():
    """Clear all cached values."""
    _cache.clear()
