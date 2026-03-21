from __future__ import annotations
import time
from functools import wraps

_cache: dict[str, tuple[float, any]] = {}
DEFAULT_TTL = 30  # seconds


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
            _cache[key] = (now, result)
            return result
        return wrapper
    return decorator


def clear_cache():
    """Clear all cached values."""
    _cache.clear()
