"""Mapa de modelos (Secção 2.6): fast / reasoning / embeddings → IDs via Settings."""

from __future__ import annotations

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.strategy import Strategy


def resolve_chat_model_id(settings: Settings, strategy: Strategy) -> str:
    """Modelo de chat completions conforme estratégia (único eixo permitido para o grafo)."""
    return settings.llm_model_fast if strategy == Strategy.fast else settings.llm_model_reasoning


def resolve_embedding_model_id(settings: Settings) -> str:
    """ID do modelo de embeddings (mesmo mapa de config; API distinta de chat)."""
    return settings.embedding_model


# Alias histórico
resolve_model = resolve_chat_model_id
