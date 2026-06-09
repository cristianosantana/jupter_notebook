"""Contratos da memória remissiva materializada pelo comando externo."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class RemissiveKnowledgeItem:
    """Conteúdo validado único e suas perguntas curtas de índice."""

    user_id: str
    category: str
    context_key: str
    validated_answer: str
    recent_questions: tuple[str, ...] = ()
    key_metrics: Mapping[str, Any] = field(default_factory=dict)
    index_questions: tuple[str, ...] = ()
    consolidated_at: datetime | None = None
    ttl_expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RemissiveEssenceItem:
    """Observação estável extraída de conversas supervisionadas."""

    user_id: str
    theme: str
    observation: str | None = None
    key_finding: str | None = None
    recommendation: str | None = None
    stable_metrics: Mapping[str, Any] = field(default_factory=dict)
    confidence: str | None = None
    last_updated: datetime | None = None


@dataclass(frozen=True, slots=True)
class CompressionLogEntry:
    """Registro de auditoria da destilação de uma janela supervisionada."""

    user_id: str
    from_state: str
    to_state: str
    batch_key: str | None = None
    messages_compressed: int = 0
    compression_ratio: float | None = None
    what_was_kept: str | None = None
    what_was_dropped: str | None = None
    compressed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SupervisedMemoryBatch:
    """Lote materializado pelo comando independente."""

    knowledge: Sequence[RemissiveKnowledgeItem] = ()
    essence: Sequence[RemissiveEssenceItem] = ()
    compression_log: CompressionLogEntry | None = None


@dataclass(frozen=True, slots=True)
class RemissiveConversationWindow:
    """Janela read-only lida das tabelas do processo atual."""

    session_id: str
    user_id: str
    messages: Sequence[Mapping[str, Any]] = ()
    indexed_turns: Sequence[Mapping[str, Any]] = ()
