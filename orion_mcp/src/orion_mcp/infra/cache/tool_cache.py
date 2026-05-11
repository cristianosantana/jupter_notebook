from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Protocol

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore

_logger = logging.getLogger(__name__)


def tool_key(name: str, args: dict[str, Any]) -> str:
    canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    h = hashlib.sha256(f"{name}|{canonical}".encode("utf-8")).hexdigest()
    return f"tool:{h}"


class ToolCache(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_seconds: int = 3600) -> None: ...


class RedisToolCache:
    def __init__(self, client: Any):
        self._r = client

    async def get(self, key: str) -> str | None:
        v = await self._r.get(key)
        if v is None:
            return None
        if isinstance(v, bytes | bytearray):
            return v.decode("utf-8")
        return str(v)

    async def set(self, key: str, value: str, ttl_seconds: int = 3600) -> None:
        await self._r.set(key, value, ex=ttl_seconds)


class MemoryToolCache:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._d.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int = 3600) -> None:
        _ = ttl_seconds
        self._d[key] = value
