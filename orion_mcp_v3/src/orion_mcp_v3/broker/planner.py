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
from orion_mcp_v3.contracts.semantic_retrieval_plan import SemanticRetrievalPlan

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

_DECLINE_OR_DROP_RX = re.compile(
    r"(queda|quedas|desacelera|declínio|declinio|drop|decline|desceu|caiu|baixa\s+de)",
    re.IGNORECASE,
)
_ANOMALY_LEX_RX = re.compile(r"(anomalia|anomalias|outlier|atípic|atipic)", re.IGNORECASE)
_BASELINE_LEX_RX = re.compile(
    r"(baseline|linha\s+de\s+base|referência|média\s+hist|media\s+hist)",
    re.IGNORECASE,
)
_COMPARE_LEX_RX = re.compile(r"(\bvs\.?\b|versus|compar|frente\s+a|em\s+relação\s+a)", re.IGNORECASE)


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


def infer_retrieval_mode_flags(
    cognitive: CognitivePlan,
    nl_hints: Mapping[str, Any] | None,
    *,
    query_text: str = "",
) -> dict[str, bool]:
    """
    Infere modos de recuperação cognitiva (Fase 2.1) a partir do plano + NL + hints de agregação.

    Campos: ``trend_analysis``, ``ranking``, ``comparison``, ``baseline``, ``monitoring``, ``anomaly_scan``.
    """
    nl = dict(nl_hints or {})
    raw = (query_text or "").strip()
    tlow = raw.lower()
    agg = nl.get("aggregation_kind")

    trend_analysis = bool(
        cognitive.needs_trend_analysis
        or cognitive.needs_temporal_context
        or agg in ("temporal", "mixed")
        or (raw and _TEMPORAL_RX.search(raw) is not None)
        or (raw and _DECLINE_OR_DROP_RX.search(raw) is not None)
    )
    ranking = bool(agg == "ranking" or (raw and _RANKING_RX.search(raw) is not None))
    comparison = bool(
        cognitive.needs_comparison
        or cognitive.intent_type == IntentType.COMPARATIVE
        or agg == "mixed"
        or (raw and _COMPARE_LEX_RX.search(raw) is not None)
    )
    baseline = bool(
        cognitive.needs_baseline
        or (raw and _BASELINE_LEX_RX.search(raw) is not None)
        or agg == "mixed"
        or (raw and _DECLINE_OR_DROP_RX.search(raw) is not None)
    )
    monitoring = bool(cognitive.intent_type == IntentType.MONITORING or "alerta" in tlow)
    anomaly_scan = bool(
        cognitive.intent_type == IntentType.MONITORING
        or (raw and _ANOMALY_LEX_RX.search(raw) is not None)
        or (raw and _DECLINE_OR_DROP_RX.search(raw) is not None)
    )

    return {
        "trend_analysis": trend_analysis,
        "ranking": ranking,
        "comparison": comparison,
        "baseline": baseline,
        "monitoring": monitoring,
        "anomaly_scan": anomaly_scan,
    }


def order_primary_retrieval_steps(flags: Mapping[str, bool]) -> tuple[str, ...]:
    """Ordena passos cognitivos (pipeline antes da query), p.ex. queda de vendas → série → comparação → baseline → outliers."""
    steps: list[str] = []
    if flags.get("monitoring"):
        steps.append("monitoring")
    if flags.get("trend_analysis"):
        steps.append("temporal_series")
    if flags.get("ranking"):
        steps.append("ranking")
    if flags.get("comparison"):
        steps.append("comparison")
    if flags.get("baseline"):
        steps.append("baseline")
    if flags.get("anomaly_scan"):
        steps.append("anomaly_scan")
    if not steps:
        steps.append("exploratory_scan")
    return tuple(steps)


def build_semantic_retrieval_plan(
    cognitive: CognitivePlan,
    *,
    query_text: str | None = None,
    intent_slug: str | None = None,
    base: SemanticQueryPlan | None = None,
    correlation_id: str | None = None,
) -> SemanticRetrievalPlan:
    """
    Intent → modos de retrieval + :class:`~SemanticQueryPlan` (Fase 2.1).

    Funde ``retrieval_modes`` e ``primary_steps`` em ``query_plan.hints`` para o compilador / digest.
    """
    raw = (query_text or "").strip()
    nl_hints = infer_aggregation_hints(raw) if raw else {}
    qp = build_query_plan(
        cognitive,
        query_text=query_text,
        intent_slug=intent_slug,
        base=base,
        correlation_id=correlation_id,
    )
    flags = infer_retrieval_mode_flags(cognitive, nl_hints, query_text=raw)
    steps = order_primary_retrieval_steps(flags)

    merged = _merge_hints(
        dict(qp.hints),
        {
            "retrieval_modes": flags,
            "primary_steps": list(steps),
        },
    )
    qp_tagged = replace(qp, hints=merged)

    return SemanticRetrievalPlan(
        trend_analysis=flags["trend_analysis"],
        ranking=flags["ranking"],
        comparison=flags["comparison"],
        baseline=flags["baseline"],
        monitoring=flags["monitoring"],
        anomaly_scan=flags["anomaly_scan"],
        primary_steps=steps,
        query_plan=qp_tagged,
    )


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
