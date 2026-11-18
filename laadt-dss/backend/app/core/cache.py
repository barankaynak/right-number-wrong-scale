"""
Redis-based simulation result caching.
Cache key: SHA256 of request parameters.
TTL: 1 hour.
"""
import hashlib
import json
import redis
from typing import Optional, Any
from app.core.config import settings


def _get_redis_client() -> Optional[redis.Redis]:
    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def make_cache_key(params: dict) -> str:
    """SHA256 hash of sorted JSON params."""
    serialized = json.dumps(params, sort_keys=True, default=str)
    return "sim:" + hashlib.sha256(serialized.encode()).hexdigest()


def get_cached(params: dict) -> Optional[Any]:
    """Returns cached result or None."""
    client = _get_redis_client()
    if client is None:
        return None
    key = make_cache_key(params)
    try:
        cached = client.get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass
    return None


def set_cached(params: dict, result: Any, ttl_seconds: int = 3600) -> None:
    """Stores result in cache with TTL."""
    client = _get_redis_client()
    if client is None:
        return
    key = make_cache_key(params)
    try:
        client.setex(key, ttl_seconds, json.dumps(result, default=str))
    except Exception:
        pass
