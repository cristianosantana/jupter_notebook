"""Eventos de ciclo do runtime (Fase 0.4 — payloads opacos)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class RuntimeEventType(Enum):
    DIGEST_CREATED = "digest_created"
    MEMORY_PROMOTED = "memory_promoted"
    BUDGET_EXCEEDED = "budget_exceeded"
    CONFLICT_DETECTED = "conflict_detected"


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    """Evento imutável; consumidores interpretam ``payload`` mais tarde."""

    event_type: RuntimeEventType
    payload: Mapping[str, Any] = field(default_factory=dict)
    trace_id: str | None = None
