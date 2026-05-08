"""Contrato para mini-resumos por chunk na destilação (Fase 4.2)."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence


class SummarizerProtocol(Protocol):
    """
    Implementação concreta pode chamar LLM, heurísticas ou extractivo fixo.

    ``chunk_index`` identifica a posição do chunk na sequência (0-based).
    """

    def summarize_chunk(
        self,
        rows: Sequence[Mapping[str, Any]],
        chunk_index: int,
    ) -> str:
        ...
