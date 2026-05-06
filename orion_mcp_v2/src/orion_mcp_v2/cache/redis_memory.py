from __future__ import annotations

import json
import logging
from typing import Any

_logger = logging.getLogger(__name__)

MEMORY_KEY_PREFIX = "memory:"


class MemoryRedisStore:
    """Hash Redis `memory:{user_id}` com campos por categoria (JSON)."""

    def __init__(self, client: Any | None, *, ttl_seconds: int):
        self._r = client
        self._ttl = ttl_seconds

    @staticmethod
    def key(user_id: str) -> str:
        return f"{MEMORY_KEY_PREFIX}{user_id}"

    async def set_category(self, user_id: str, category: str, payload: dict[str, Any]) -> None:
        if self._r is None:
            return
        key = self.key(user_id)
        await self._r.hset(key, category, json.dumps(payload, ensure_ascii=False))
        await self._r.expire(key, self._ttl)

    async def get_category(self, user_id: str, category: str) -> dict[str, Any] | None:
        if self._r is None:
            return None
        raw = await self._r.hget(self.key(user_id), category)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            _logger.warning("redis_memory_json_invalid", extra={"user_id": user_id})
            return None

    async def get_all_categories(self, user_id: str) -> dict[str, dict[str, Any]]:
        if self._r is None:
            return {}
        key = self.key(user_id)
        blob = await self._r.hgetall(key)
        out: dict[str, dict[str, Any]] = {}
        for field, raw in blob.items():
            fk = field.decode("utf-8") if isinstance(field, bytes) else str(field)
            rv = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            try:
                data = json.loads(rv)
                if isinstance(data, dict):
                    out[fk] = data
            except json.JSONDecodeError:
                continue
        return out
