from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RowsAggregator(Protocol):
    """Contrato: linhas tabulares → dict pequeno para `skill_aggregate`."""

    def enrich(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        ...
