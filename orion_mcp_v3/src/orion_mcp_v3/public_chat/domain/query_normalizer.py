"""Normalização de perguntas para cache de intent (P2)."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.intent_parser import _normalize_text


def normalize_query_for_intent_cache(message: str) -> str:
    """Forma canônica da pergunta — ignora acento, caixa e espaços extras."""
    return _normalize_text(message or "")
