from __future__ import annotations

from typing import Any

from orion_mcp_v2.core.aggregators.cross_selling_compute import compute_cross_selling_aggregate

_EXPECTED = frozenset(
    {
        "servico_A_id",
        "servico_B_id",
        "frequencia_combo",
        "receita_combo",
    }
)


class CrossSellingAggregator:
    """Adaptador: valida colunas mínimas e delega ao compute puro."""

    def __init__(self, *, top_n: int = 20) -> None:
        self._top_n = top_n

    def enrich(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        if rows:
            keys = set(rows[0].keys())
            missing = sorted(_EXPECTED - keys)
            if missing:
                raise ValueError(
                    "cross_selling: colunas em falta no resultado da query: " + ", ".join(missing)
                )
        return compute_cross_selling_aggregate(rows, top_n=self._top_n)
