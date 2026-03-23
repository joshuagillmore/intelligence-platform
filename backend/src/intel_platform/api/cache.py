from __future__ import annotations
import time
from functools import wraps
from typing import Any

_cache: dict[str, tuple[float, Any]] = {}
DEFAULT_TTL = 30  # seconds
_CACHE_MAX_SIZE = 500  # PERF: cap to prevent unbounded growth


def cached(ttl: int = DEFAULT_TTL):
    """Simple in-memory cache decorator for endpoint responses."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Create cache key from function name and args
            key = f"{func.__name__}:{str(args)}:{str(sorted(kwargs.items()))}"

            now = time.time()
            if key in _cache:
                cached_time, cached_value = _cache[key]
                if now - cached_time < ttl:
                    return cached_value

            result = func(*args, **kwargs)
            # Evict expired entries when cache grows large
            if len(_cache) >= _CACHE_MAX_SIZE:
                stale = [k for k, (t, _) in _cache.items() if now - t >= ttl]
                for k in stale:
                    del _cache[k]
            _cache[key] = (now, result)
            return result
        return wrapper
    return decorator


def clear_cache():
    """Clear all cached values."""
    _cache.clear()
