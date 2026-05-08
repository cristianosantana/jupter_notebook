"""
Planner heurístico (Fase 3.1): texto natural → metadados no :class:`~SemanticQueryPlan`.

Sem LLM: padrões PT/EN para agregação temporal e ranking.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan

_TEMPORAL_RX = re.compile(
    r"(últimos?\s+\d+\s*meses?|"
    r"último\s+mês|"
    r"last\s+\d+\s*months?|"
    r"past\s+\d+\s*months?|"
    r"últimos?\s+meses?)",
    re.IGNORECASE,
)

_RANKING_RX = re.compile(
    r"(top\s+\d+\s+clientes?|"
    r"top\s+clientes?|"
    r"maiores?\s+clientes?|"
    r"ranking\s+de\s+clientes?|"
    r"top\s+\d+\s+customers?|"
    r"top\s+customers?)",
    re.IGNORECASE,
)


def _merge_hints(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    out.update(extra)
    return out


def infer_aggregation_hints(query_text: str) -> dict[str, Any]:
    """
    Devolve fragmentos para fundir em ``SemanticQueryPlan.hints`` conforme o texto.
    """
    t = (query_text or "").strip()
    if not t:
        return {}

    hints: dict[str, Any] = {}
    temporal = bool(_TEMPORAL_RX.search(t))
    ranking = bool(_RANKING_RX.search(t))

    if temporal:
        hints["time_grain"] = "month"
        m = re.search(r"(?:últimos?|last|past)\s+(\d+)\s*(?:meses?|months?)", t, re.IGNORECASE)
        if m:
            hints["lookback_months"] = int(m.group(1))

    if ranking:
        hints["rank_dimension"] = "client"
        hints["rank_metric"] = "revenue"
        mtop = re.search(r"top\s+(\d+)\b", t, re.IGNORECASE)
        if mtop:
            hints["top_n"] = int(mtop.group(1))

    if temporal and ranking:
        hints["aggregation_kind"] = "mixed"
    elif temporal:
        hints["aggregation_kind"] = "temporal"
    elif ranking:
        hints["aggregation_kind"] = "ranking"

    return hints


def plan_from_natural_language(
    query_text: str,
    *,
    intent_slug: str = "analytics.generic",
    base: SemanticQueryPlan | None = None,
    correlation_id: str | None = None,
) -> SemanticQueryPlan:
    """
    Constrói ou enriquece um plano semântico com heurísticas de agregação.
    """
    inferred = infer_aggregation_hints(query_text)
    if base is None:
        merged = inferred
        cid = correlation_id
        return SemanticQueryPlan(
            intent_slug=intent_slug,
            strategy=RetrievalStrategy.BROKER_FANOUT,
            target_collections=(),
            hints=merged,
            correlation_id=cid,
        )

    merged_hints = _merge_hints(dict(base.hints), inferred)
    return replace(
        base,
        hints=merged_hints,
        strategy=RetrievalStrategy.BROKER_FANOUT,
        correlation_id=correlation_id if correlation_id is not None else base.correlation_id,
    )
