"""Protocolo de embeddings do Chat Público."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingService(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
