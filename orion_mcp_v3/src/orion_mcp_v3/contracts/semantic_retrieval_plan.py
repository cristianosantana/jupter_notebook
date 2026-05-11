"""
Plano de recuperação semântica (Fase 2.1) — intenção → modos de retrieval antes da query SQL.

Compõe-se com :class:`~SemanticQueryPlan`: o ``query_plan`` é o contrato executável;
os booleanos descrevem *o quê* inferir (tendência, ranking, comparação, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass

from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan


@dataclass(frozen=True, slots=True)
class SemanticRetrievalPlan:
    """
    Modos cognitivos inferidos + plano semântico já materializado.

    ``primary_steps`` ordena a cadeia cognitiva desejada (ex.: série temporal →
    comparação → baseline → outliers), alinhada ao roadmap (ex.: «queda de vendas»).
    """

    trend_analysis: bool
    ranking: bool
    comparison: bool
    baseline: bool
    monitoring: bool
    anomaly_scan: bool
    primary_steps: tuple[str, ...]
    query_plan: SemanticQueryPlan
