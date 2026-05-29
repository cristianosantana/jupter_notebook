"""
Agrega vários :class:`~AnalyticsResult` num único :class:`~EvidenceBlock`.

Usa :class:`~EvidenceBuilder` por ângulo e funde sumários, insights, métricas,
proveniência e cobertura. Cada ângulo usa um :class:`~EvidenceSeriesSpec` para
alinhar ``value_key`` / ``time_key`` / ``grain`` (ex.: vários templates no fan-out).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from orion_mcp_v3.broker.answer_projector import build_projected_answer, filter_rows_for_entity_filters
from orion_mcp_v3.broker.evidence_builder import EvidenceBuilder
from orion_mcp_v3.broker.evidence_series_resolve import resolve_evidence_series_specs
from orion_mcp_v3.broker.executor import AnalyticsResult
from orion_mcp_v3.contracts.cognitive_artifact import artifact_provenance_anchor
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.evidence_series_spec import EvidenceSeriesSpec
from orion_mcp_v3.runtime.provenance import merge_coverage_infos, merge_provenance_anchors

if TYPE_CHECKING:
    from orion_mcp_v3.broker.query_templates import QueryTemplateRegistry


class EvidenceAggregator:
    """Funde N resultados analíticos numa única evidência para o narrador / fusão."""

    def __init__(self, *, builder: EvidenceBuilder | None = None) -> None:
        self._builder = builder or EvidenceBuilder()

    def merge(
        self,
        results: Sequence[AnalyticsResult],
        *,
        value_key: str = "total_faturamento",
        time_key: str | None = None,
        grain: str = "month",
        id_key: str | None = "id",
        series_specs: Sequence[EvidenceSeriesSpec] | None = None,
        templates: "QueryTemplateRegistry | None" = None,
        query_text: str | None = None,
    ) -> EvidenceBlock:
        """
        :param series_specs: Uma especificação por resultado (mesma ordem). Se ``None``,
            são derivadas via :func:`~resolve_evidence_series_specs` (recomendado
            passar ``templates`` quando houver ``template_slug`` nos hints).
        :param templates: Registo de templates (ex. :data:`ANALYTICS_TEMPLATES`).
        :param query_text: Pergunta original. Quando presente, projeta uma resposta direta
            antes da narração LLM.
        """
        if not results:
            raise ValueError("results must be non-empty")

        if series_specs is not None:
            if len(series_specs) != len(results):
                raise ValueError(
                    f"series_specs length ({len(series_specs)}) must match results ({len(results)})",
                )
            specs = tuple(series_specs)
        else:
            specs = resolve_evidence_series_specs(
                results,
                templates=templates,
                default_value_key=value_key,
                default_time_key=time_key,
                default_grain=grain,
                default_id_key=id_key,
            )

        if len(results) == 1:
            s0 = specs[0]
            rows = _rows_filtered_by_entity(results[0], templates=templates)
            block = self._builder.build(
                rows,
                value_key=s0.value_key,
                value_kind=s0.value_kind,
                label_key=s0.label_key,
                time_key=s0.time_key,
                grain=s0.grain,
                id_key=s0.id_key if s0.id_key is not None else id_key,
            )
            return _with_projected_answer(
                block,
                query_text=query_text,
                results=results,
                templates=templates,
            )

        partials: list[tuple[str, EvidenceBlock]] = []
        for r, spec in zip(results, specs):
            kid = spec.id_key if spec.id_key is not None else id_key
            rows = _rows_filtered_by_entity(r, templates=templates)
            eb = self._builder.build(
                rows,
                value_key=spec.value_key,
                value_kind=spec.value_kind,
                label_key=spec.label_key,
                time_key=spec.time_key,
                grain=spec.grain,
                id_key=kid,
            )
            partials.append((r.plan.intent_slug, eb))

        summary = "\n\n".join(f"[{slug}] {eb.summary}" for slug, eb in partials)

        primary_slug, primary_eb = partials[0]
        insights: dict[str, Any] = dict(primary_eb.insights)
        insights["fanout"] = {
            "primary_intent_slug": primary_slug,
            "angles": {
                slug: {
                    "summary": eb.summary,
                    "trends": eb.insights.get("trends"),
                    "baseline": eb.insights.get("baseline"),
                    "comparisons": eb.insights.get("comparisons"),
                }
                for slug, eb in partials
            },
        }

        for slug, eb in partials[1:]:
            if slug == "prior_period":
                insights["prior_period"] = eb.insights
            elif slug.startswith("metric."):
                insights[f"angle_{slug.replace('.', '_')}"] = eb.insights
            elif slug == "baseline":
                insights["baseline_window"] = eb.insights

        weights = [max(1, r.row_count) for r in results]
        wsum = float(sum(weights))
        conf_weighted = sum(eb.confidence * w for (_, eb), w in zip(partials, weights)) / wsum

        total_rows = sum(r.row_count for r in results)
        metrics: dict[str, Any] = dict(primary_eb.metrics)
        metrics["fanout"] = {
            "intent_slugs": [r.plan.intent_slug for r in results],
            "total_input_rows": total_rows,
            "per_angle": tuple(
                {
                    "intent_slug": r.plan.intent_slug,
                    "template_slug": (r.plan.hints or {}).get("template_slug")
                    if isinstance(r.plan.hints, Mapping)
                    else None,
                    "value_key": spec.value_key,
                    "value_kind": spec.value_kind,
                    "time_key": spec.time_key,
                    "grain": spec.grain,
                    "rows": r.row_count,
                    "sql": r.sql[:200],
                }
                for r, spec in zip(results, specs)
            ),
        }
        cs = metrics.get("confidence_scoring")
        if isinstance(cs, Mapping):
            cs_m = dict(cs)
            cs_m["combined"] = conf_weighted
            cs_m["fanout_row_weighted_mean"] = conf_weighted
            metrics["confidence_scoring"] = cs_m

        merged_cov = merge_coverage_infos(*(eb.coverage for _, eb in partials), notes="broker.evidence_aggregator.fanout")
        bundles = tuple(eb.provenance for _, eb in partials)
        fanout_anchor = (
            artifact_provenance_anchor(
                kind="evidence.fanout",
                step="merge",
                source="broker.evidence_aggregator",
            ),
        )
        merged_prov = merge_provenance_anchors(*bundles, fanout_anchor)

        refs: list[str] = []
        for _, eb in partials:
            refs.extend(eb.sample_refs)
        sample_refs = tuple(dict.fromkeys(refs))

        supporting: dict[str, Any] = dict(primary_eb.supporting_data)
        supporting["fanout_by_angle"] = {slug: dict(eb.supporting_data) for slug, eb in partials}

        block = EvidenceBlock(
            summary=summary,
            insights=insights,
            metrics=metrics,
            confidence=min(0.95, conf_weighted),
            coverage=merged_cov,
            provenance=merged_prov,
            sample_refs=sample_refs,
            supporting_data=supporting,
        )
        return _with_projected_answer(
            block,
            query_text=query_text,
            results=results,
            templates=templates,
        )


def _with_projected_answer(
    block: EvidenceBlock,
    *,
    query_text: str | None,
    results: Sequence[AnalyticsResult],
    templates: "QueryTemplateRegistry | None",
) -> EvidenceBlock:
    if not query_text or templates is None:
        return block
    projected = build_projected_answer(query_text, results, templates=templates)
    if projected is None:
        return block

    projected_dict = projected.as_dict()
    suppress_complementary = _should_suppress_complementary(projected_dict)
    complementary_summary = (
        "Resumo estatístico complementar (não substitui a resposta direta):\n"
        f"{block.summary}"
    )
    summary = (
        projected.summary
        if suppress_complementary
        else f"{projected.summary}\n\n{complementary_summary}"
    )
    metrics = {**dict(block.metrics), "answer_plan": projected_dict["plan"]}
    if suppress_complementary:
        metrics["complementary_summary_suppressed"] = True
    return EvidenceBlock(
        summary=summary,
        insights={**dict(block.insights), "direct_answer": projected_dict},
        metrics=metrics,
        confidence=block.confidence,
        coverage=block.coverage,
        provenance=block.provenance,
        sample_refs=block.sample_refs,
        supporting_data={**dict(block.supporting_data), "direct_answer": projected_dict},
    )


def _should_suppress_complementary(projected: Mapping[str, Any]) -> bool:
    plan = projected.get("plan")
    if not isinstance(plan, Mapping):
        return False
    scope = plan.get("result_scope")
    mode = scope.get("mode") if isinstance(scope, Mapping) else None
    measure = str(plan.get("measure") or "")
    operation = str(plan.get("operation") or "")
    if mode == "all" and operation == "list":
        return True
    return measure in {"ticket_medio_item", "ticket_medio_os"} and operation == "list"


def _rows_filtered_by_entity(
    result: AnalyticsResult,
    *,
    templates: "QueryTemplateRegistry | None",
) -> tuple[Mapping[str, Any], ...]:
    hints = result.plan.hints if isinstance(result.plan.hints, Mapping) else {}
    filters = hints.get("entity_filters")
    if not isinstance(filters, (list, tuple)) or templates is None:
        return tuple(result.rows)
    slug = hints.get("template_slug")
    if not isinstance(slug, str):
        return tuple(result.rows)
    template = templates.get(slug)
    capability = getattr(template, "capability", None)
    if capability is None:
        return tuple(result.rows)
    return filter_rows_for_entity_filters(
        result.rows,
        entity_filters=filters,
        capability=capability,
    )
