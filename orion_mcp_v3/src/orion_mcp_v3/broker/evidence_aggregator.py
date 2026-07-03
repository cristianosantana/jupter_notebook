"""
Agrega vários :class:`~AnalyticsResult` num único :class:`~EvidenceBlock`.

Usa :class:`~EvidenceBuilder` por ângulo e funde sumários, insights, métricas,
proveniência e cobertura. Cada ângulo usa um :class:`~EvidenceSeriesSpec` para
alinhar ``value_key`` / ``time_key`` / ``grain`` (ex.: vários templates no fan-out).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from orion_mcp_v3.broker.answer_projector import (
    build_full_list_summary,
    build_full_section_detail,
    build_projected_answer,
    build_projected_answer_set,
    filter_rows_for_entity_filters,
)
from orion_mcp_v3.broker.evidence_builder import EvidenceBuilder
from orion_mcp_v3.broker.evidence_series_resolve import resolve_evidence_series_specs
from orion_mcp_v3.broker.executor import AnalyticsResult
from orion_mcp_v3.contracts.cognitive_artifact import artifact_provenance_anchor
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.evidence_contract import (
    EvidenceContract,
    EvidencePriority,
    OperationalConfidence,
)
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
        metrics["input_rows"] = total_rows
        metrics["coverage_scoring"] = 1.0 if total_rows > 0 else 0.0
        fanout_contract = _merge_evidence_contracts(
            [eb for _, eb in partials],
            row_count=total_rows,
            source_priority=EvidencePriority.AGGREGATED_METRICS,
        )
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
        supporting["evidence_contract"] = fanout_contract.as_dict()
        metrics["evidence_contract"] = fanout_contract.as_dict()

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
    collection_slug = _collection_slug(results)
    if collection_slug is not None:
        projected_set = build_projected_answer_set(query_text, results, templates=templates)
        if projected_set is not None:
            projected_set_dict = projected_set.as_dict()
            full_section_detail = build_full_section_detail(
                projected_set,
                templates=templates,
            )
            if full_section_detail:
                projected_set_dict["full_section_detail"] = full_section_detail
            metrics = {**dict(block.metrics), "answer_set": projected_set_dict}
            contract = EvidenceContract.from_mapping(block.supporting_data.get("evidence_contract"))
            if contract.status.value == "present":
                contract = EvidenceContract.present(
                    row_count=contract.row_count,
                    full_dataset_available=contract.full_dataset_available,
                    source_priority=EvidencePriority.DIRECT_ANSWER,
                    operational_confidence=_direct_answer_confidence(contract),
                    safe_for_record_level_claims=contract.safe_for_record_level_claims,
                )
                metrics["evidence_contract"] = contract.as_dict()
            summary = str(projected_set_dict.get("section_detail") or projected_set.summary)
            return EvidenceBlock(
                summary=summary,
                insights={**dict(block.insights), "direct_answer_set": projected_set_dict},
                metrics=metrics,
                confidence=block.confidence,
                coverage=block.coverage,
                provenance=block.provenance,
                sample_refs=block.sample_refs,
                supporting_data={
                    **dict(block.supporting_data),
                    "direct_answer_set": projected_set_dict,
                    "evidence_contract": contract.as_dict(),
                },
            )

    projected = build_projected_answer(query_text, results, templates=templates)
    if projected is None:
        return block

    projected_dict = projected.as_dict()
    if templates is not None:
        full_summary = build_full_list_summary(projected, templates=templates)
        if full_summary and full_summary.strip() != projected.summary.strip():
            projected_dict["full_summary"] = full_summary
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
    contract = EvidenceContract.from_mapping(block.supporting_data.get("evidence_contract"))
    if contract.status.value == "present":
        contract = EvidenceContract.present(
            row_count=contract.row_count,
            full_dataset_available=contract.full_dataset_available,
            source_priority=EvidencePriority.DIRECT_ANSWER,
            operational_confidence=_direct_answer_confidence(contract),
            safe_for_record_level_claims=contract.safe_for_record_level_claims,
        )
        metrics["evidence_contract"] = contract.as_dict()
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
        supporting_data={
            **dict(block.supporting_data),
            "direct_answer": projected_dict,
            "evidence_contract": contract.as_dict(),
        },
    )


def _collection_slug(results: Sequence[AnalyticsResult]) -> str | None:
    slugs: list[str] = []
    for result in results:
        hints = result.plan.hints if isinstance(result.plan.hints, Mapping) else {}
        raw = hints.get("collection_slug")
        if isinstance(raw, str) and raw.strip():
            slugs.append(raw.strip())
    if not slugs:
        return None
    first = slugs[0]
    return first if all(slug == first for slug in slugs) else None


def _direct_answer_confidence(contract: EvidenceContract) -> OperationalConfidence:
    """Dataset completo em resposta direta → cobertura plena para o narrador."""
    current = contract.operational_confidence
    if not contract.full_dataset_available:
        return current
    return OperationalConfidence(
        data_coverage=1.0,
        aggregation_reliability=current.aggregation_reliability,
        pipeline_integrity=current.pipeline_integrity,
        narrative_confidence=max(current.narrative_confidence, 0.8),
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


def _merge_evidence_contracts(
    blocks: Sequence[EvidenceBlock],
    *,
    row_count: int,
    source_priority: EvidencePriority,
) -> EvidenceContract:
    contracts = [EvidenceContract.from_mapping(b.supporting_data.get("evidence_contract")) for b in blocks]
    if not contracts:
        return EvidenceContract.empty_result(row_count=row_count)
    data_coverage = sum(c.operational_confidence.data_coverage for c in contracts) / len(contracts)
    aggregation = sum(c.operational_confidence.aggregation_reliability for c in contracts) / len(contracts)
    pipeline = min(c.operational_confidence.pipeline_integrity for c in contracts)
    narrative = sum(c.operational_confidence.narrative_confidence for c in contracts) / len(contracts)
    return EvidenceContract.present(
        row_count=row_count,
        full_dataset_available=all(c.full_dataset_available for c in contracts),
        source_priority=source_priority,
        operational_confidence=OperationalConfidence(
            data_coverage=data_coverage,
            aggregation_reliability=min(0.95, aggregation),
            pipeline_integrity=pipeline,
            narrative_confidence=narrative,
        ),
        safe_for_record_level_claims=all(c.safe_for_record_level_claims for c in contracts),
    )


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
