"""
Resolve :class:`~EvidenceSeriesSpec` por :class:`~AnalyticsResult` (templates vs plano compilado).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from orion_mcp_v3.broker.executor import AnalyticsResult
from orion_mcp_v3.contracts.evidence_series_spec import EvidenceSeriesSpec

if TYPE_CHECKING:
    from orion_mcp_v3.broker.query_templates import QueryTemplateRegistry


def infer_value_key_from_compiled_plan(result: AnalyticsResult, *, default: str) -> str:
    """Heurística para planos sem template (alias em ``sql_order_by``, ângulos ``metric.*`` / ``baseline``)."""
    slug = result.plan.intent_slug
    if slug.startswith("metric.") and "ticket" in slug:
        return "ticket_count"
    if slug == "baseline":
        return "avg_faturamento"
    hints = result.plan.hints
    if isinstance(hints.get("sql_order_by"), Mapping):
        alias = hints["sql_order_by"].get("alias")
        if isinstance(alias, str) and alias:
            return alias
    return default


def resolve_evidence_series_specs(
    results: Sequence[AnalyticsResult],
    *,
    templates: "QueryTemplateRegistry | None" = None,
    default_value_key: str = "total_faturamento",
    default_time_key: str | None = None,
    default_grain: str = "month",
    default_id_key: str | None = "id",
) -> tuple[EvidenceSeriesSpec, ...]:
    """
    Produz uma :class:`EvidenceSeriesSpec` alinhada a cada resultado (ordem preservada).

    * Se ``hints`` contiver ``template_slug`` e o registo existir em ``templates``,
      usam-se ``value_key``, ``time_key`` e ``grain`` do template.
    * Caso contrário, aplica-se :func:`infer_value_key_from_compiled_plan` e os
      defaults de tempo/granularidade.
    """
    out: list[EvidenceSeriesSpec] = []
    for r in results:
        hints = r.plan.hints if isinstance(r.plan.hints, Mapping) else {}
        tpl_slug = hints.get("template_slug")
        tpl = None
        if templates is not None and isinstance(tpl_slug, str) and tpl_slug:
            tpl = templates.get(tpl_slug)
        if tpl is not None:
            value_key = tpl.value_key
            value_kind = "money"
            selected_metric = hints.get("selected_metric")
            capability = getattr(tpl, "capability", None)
            if isinstance(selected_metric, str) and capability is not None:
                measure = capability.measures.get(selected_metric)
                if measure is not None:
                    value_key = measure.column
                    value_kind = measure.kind
            elif capability is not None:
                for measure in capability.measures.values():
                    if measure.column == value_key:
                        value_kind = measure.kind
                        break
            out.append(
                EvidenceSeriesSpec(
                    value_key=value_key,
                    value_kind=value_kind,
                    time_key=tpl.time_key,
                    grain=tpl.grain,
                    id_key=default_id_key,
                    label_key=tpl.label_key,
                    template_slug=tpl.slug,
                    intent_slug=r.plan.intent_slug,
                )
            )
            continue
        vk = infer_value_key_from_compiled_plan(r, default=default_value_key)
        out.append(
            EvidenceSeriesSpec(
                value_key=vk,
                value_kind="money",
                time_key=default_time_key,
                grain=default_grain,
                id_key=default_id_key,
                label_key=None,
                template_slug=None,
                intent_slug=r.plan.intent_slug,
            )
        )
    return tuple(out)
