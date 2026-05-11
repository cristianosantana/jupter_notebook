from __future__ import annotations

from openai import AsyncOpenAI

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.llm.model_config import resolve_embedding_model_id


async def embed_text(settings: Settings, text: str) -> list[float]:
    if not settings.openai_api_key:
        # Deterministic tiny vector for tests (wrong dim for pg - only used when long memory off)
        return [0.01] * settings.embedding_dimensions
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_http_timeout_seconds,
    )
    res = await client.embeddings.create(
        model=resolve_embedding_model_id(settings),
        input=text[:8000],
        dimensions=settings.embedding_dimensions,
    )
    return list(res.data[0].embedding)
