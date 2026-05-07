"""Unidade formal de contexto (Fase 0.2 — sem allocator, truncagem nem scoring)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ContextSource(Enum):
    """Origem coarse do texto (rastreio e políticas futuras)."""

    USER_INPUT = "user_input"
    SYSTEM = "system"
    MEMORY = "memory"
    ESSENCE = "essence"
    TOOL = "tool"
    BROKER = "broker"
    OTHER = "other"


class ContextRole(Enum):
    """Papel semântico ao montar prompts ou registos estruturados."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    NEUTRAL = "neutral"


@dataclass(frozen=True, slots=True)
class ContextBlock:
    """
    Bloco autocontido de contexto textual + metadados leves.

    ``relevance_score`` é usado pelo :mod:`budget_allocator` (Fase 1); valores
    mais altos entram primeiro na fracção não reservada a system/essence.
    """

    text: str
    role: ContextRole
    source: ContextSource
    block_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    relevance_score: float = 0.0
