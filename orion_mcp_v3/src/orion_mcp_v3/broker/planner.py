"""
Planner heurístico (Fase 3.1 + MySQL integrado): :class:`~CognitivePlan` → :class:`~SemanticQueryPlan`.

Texto cru só entra como refinamento opcional (hints de agregação); o eixo principal é o plano cognitivo.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.query_plan import AnalyticsStrategy, RetrievalStrategy, SemanticQueryPlan

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


def infer_analytics_strategy(
    cognitive: CognitivePlan,
    nl_hints: Mapping[str, Any] | None = None,
) -> AnalyticsStrategy | None:
    """
    Deriva o modo de análise a partir do cognitivo + fragmentos NL já inferidos.

    Prioridade: sinais explícitos de agregação no texto, depois flags do ``CognitivePlan``,
    depois tipo de intenção (ex.: monitorização → anomalia).
    """
    h = nl_hints or {}
    kind = h.get("aggregation_kind")
    if kind == "ranking":
        return AnalyticsStrategy.RANKING
    if kind == "temporal":
        return AnalyticsStrategy.TEMPORAL
    if kind == "mixed":
        return AnalyticsStrategy.TREND

    if cognitive.needs_comparison:
        return AnalyticsStrategy.COMPARISON
    if cognitive.intent_type == IntentType.MONITORING:
        return AnalyticsStrategy.ANOMALY
    if cognitive.needs_trend_analysis:
        return AnalyticsStrategy.TREND
    if cognitive.needs_temporal_context:
        return AnalyticsStrategy.TEMPORAL
    if cognitive.needs_analytics:
        return AnalyticsStrategy.RANKING
    return None


def _execution_retrieval_strategy(
    cognitive: CognitivePlan,
    nl_hints: dict[str, Any],
) -> RetrievalStrategy:
    """Camada de dados analíticos usa fan-out; resto segue o cognitivo."""
    if cognitive.needs_analytics or bool(nl_hints.get("aggregation_kind")):
        return RetrievalStrategy.BROKER_FANOUT
    return cognitive.retrieval_strategy


def build_query_plan(
    cognitive: CognitivePlan,
    *,
    query_text: str | None = None,
    intent_slug: str | None = None,
    base: SemanticQueryPlan | None = None,
    correlation_id: str | None = None,
) -> SemanticQueryPlan:
    """
    Constrói :class:`SemanticQueryPlan` a partir de :class:`CognitivePlan` (caminho principal).

    ``query_text`` é opcional: quando presente, funde :func:`infer_aggregation_hints` no plano.
    """
    nl_raw = (query_text or "").strip()
    nl_hints = infer_aggregation_hints(nl_raw) if nl_raw else {}
    analytics = infer_analytics_strategy(cognitive, nl_hints)
    strategy = _execution_retrieval_strategy(cognitive, nl_hints)

    merged_cognitive_hints = _merge_hints(dict(cognitive.hints), nl_hints)
    merged_cognitive_hints["cognitive"] = {
        "intent_type": cognitive.intent_type.value,
        "confidence": cognitive.confidence,
        "time_scope": cognitive.time_scope,
        "metrics": cognitive.metrics,
    }
    if analytics is not None:
        merged_cognitive_hints["analytics_strategy"] = analytics.value

    slug = intent_slug or f"analytics.{cognitive.intent_type.value}"
    cid = correlation_id

    if base is None:
        return SemanticQueryPlan(
            intent_slug=slug,
            strategy=strategy,
            target_collections=(),
            hints=merged_cognitive_hints,
            correlation_id=cid,
            analytics_strategy=analytics,
        )

    merged_hints = _merge_hints(dict(base.hints), merged_cognitive_hints)
    return replace(
        base,
        intent_slug=slug,
        strategy=strategy,
        hints=merged_hints,
        correlation_id=cid if cid is not None else base.correlation_id,
        analytics_strategy=analytics if analytics is not None else base.analytics_strategy,
    )


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
    cognitive: CognitivePlan | None = None,
) -> SemanticQueryPlan:
    """
    Compatibilidade: texto → :class:`CognitivePlan` (heurística) → :func:`build_query_plan`.

    Se ``cognitive`` for passado, esse plano é usado em vez de resolver de novo a partir do texto.
    """
    from orion_mcp_v3.runtime.intent_resolver import IntentResolver

    cp = cognitive if cognitive is not None else IntentResolver().resolve(query_text)
    return build_query_plan(
        cp,
        query_text=query_text,
        intent_slug=intent_slug,
        base=base,
        correlation_id=correlation_id,
    )
