"""Contrato de resultado da rotina de destilação."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DistillationResult:
    """Resultado de uma execução do comando de destilação."""

    windows_read: int
    knowledge_written: int
    origin_ids: list[int]
