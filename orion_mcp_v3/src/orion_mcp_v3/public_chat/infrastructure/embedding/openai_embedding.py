"""Embeddings OpenAI isolados do Chat Público."""

from __future__ import annotations

from typing import Sequence


class OpenAIPublicEmbeddingService:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        base_url: str | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key é obrigatório para OpenAIPublicEmbeddingService")
        try:
            import openai  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "O pacote 'openai' é necessário para embeddings. Instale com: pip install openai"
            ) from exc

        self._model = model
        self._dimensions = dimensions
        self._client = openai.AsyncOpenAI(api_key=api_key.strip(), base_url=base_url or None)

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        kwargs: dict = {"model": self._model, "input": texts}
        if self._dimensions:
            kwargs["dimensions"] = self._dimensions
        response = await self._client.embeddings.create(**kwargs)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]

    @staticmethod
    def to_pgvector(values: Sequence[float]) -> str:
        from orion_mcp_v3.public_chat.infrastructure.embedding.pgvector import to_pgvector

        return to_pgvector(values)
