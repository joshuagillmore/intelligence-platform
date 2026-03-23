from __future__ import annotations
import asyncio
import time
from functools import wraps
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}
DEFAULT_TTL = 30  # seconds


def cached(ttl: int = DEFAULT_TTL):
    """Simple in-memory cache decorator for endpoint responses.

    Works with both sync and async functions.
    """
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
                now = time.time()
                if key in _cache:
                    cached_time, cached_value = _cache[key]
                    if now - cached_time < ttl:
                        return cached_value
                result = await func(*args, **kwargs)
                _cache[key] = (now, result)
                return result
            return async_wrapper
        else:
            @wraps(func)
            def wrapper(*args, **kwargs):
                key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"
                now = time.time()
                if key in _cache:
                    cached_time, cached_value = _cache[key]
                    if now - cached_time < ttl:
                        return cached_value
                result = func(*args, **kwargs)
                _cache[key] = (now, result)
                return result
            return wrapper
    return decorator


def clear_cache():
    """Clear all cached values."""
    _cache.clear()
