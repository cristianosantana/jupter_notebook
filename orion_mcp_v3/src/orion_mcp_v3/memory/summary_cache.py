"""
Cache de resumos por sessão (Fase 2.4) — sem invalidação elaborada.

Implementações: noop, memória local, cliente Redis síncrono (``redis.Redis``).
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable


def _normalize_session_id(session_id: str) -> str:
    s = session_id.strip()
    return s or "default"


def _redis_key(session_id: str) -> str:
    return f"orion:v3:summary:{_normalize_session_id(session_id)}"


@runtime_checkable
class SummaryCachePort(Protocol):
    def get_summary(self, session_id: str) -> str | None: ...

    def set_summary(self, session_id: str, text: str, ttl_seconds: int = 3600) -> None: ...


class NullSummaryCache:
    """Sem persistência."""

    def get_summary(self, session_id: str) -> str | None:
        _ = session_id
        return None

    def set_summary(self, session_id: str, text: str, ttl_seconds: int = 3600) -> None:
        _ = (session_id, text, ttl_seconds)


class InMemorySummaryCache:
    """Para testes e ambientes sem Redis (TTL aproximado)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}

    def get_summary(self, session_id: str) -> str | None:
        key = _redis_key(session_id)
        row = self._store.get(key)
        if not row:
            return None
        text, exp = row
        if exp is not None and time.monotonic() > exp:
            del self._store[key]
            return None
        return text

    def set_summary(self, session_id: str, text: str, ttl_seconds: int = 3600) -> None:
        key = _redis_key(session_id)
        exp = None if ttl_seconds <= 0 else time.monotonic() + float(ttl_seconds)
        self._store[key] = (text, exp)


class RedisSummaryCache:
    """
    Espera cliente `redis.Redis` com ``decode_responses=True``::

        import redis

        RedisSummaryCache(redis.Redis.from_url(\"redis://...\", decode_responses=True))
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_summary(self, session_id: str) -> str | None:
        v = self._client.get(_redis_key(session_id))
        if v is None:
            return None
        return str(v)

    def set_summary(self, session_id: str, text: str, ttl_seconds: int = 3600) -> None:
        self._client.set(_redis_key(session_id), text, ex=ttl_seconds)
