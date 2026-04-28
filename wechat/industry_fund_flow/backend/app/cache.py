"""用途：可选 Redis；无 REDIS_URL 时用进程内 TTL 缓存。"""
import json
import time
from typing import Any, Optional

from app.config import get_settings

_local: dict[str, tuple[float, str]] = {}


def get_json(key: str) -> Optional[Any]:
    s = get_settings()
    if s.redis_url:
        try:
            import redis

            r = redis.from_url(s.redis_url, decode_responses=True)
            v = r.get(key)
            return json.loads(v) if v else None
        except Exception:
            pass
    if key in _local:
        exp, raw = _local[key]
        if exp > time.time():
            return json.loads(raw)
        del _local[key]
    return None


def set_json(key: str, value: Any, ttl_sec: int = 60) -> None:
    s = get_settings()
    raw = json.dumps(value, ensure_ascii=False, default=str)
    if s.redis_url:
        try:
            import redis

            r = redis.from_url(s.redis_url, decode_responses=True)
            r.setex(key, ttl_sec, raw)
            return
        except Exception:
            pass
    _local[key] = (time.time() + ttl_sec, raw)
