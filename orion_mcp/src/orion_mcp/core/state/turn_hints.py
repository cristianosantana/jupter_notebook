from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatTurnHints:
    """Hints opcionais por pedido HTTP (one-shot); não persistem fora do `update_state` do turno."""

    query_id: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    limit: int | None = None
    offset: int | None = None
    summarize: bool | None = None
