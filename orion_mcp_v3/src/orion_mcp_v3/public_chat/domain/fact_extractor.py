"""Extracção de facts concretos a partir de memórias resolvidas."""

from __future__ import annotations

import time
from dataclasses import dataclass

from orion_mcp_v3.public_chat.domain.direct_answer_parser import (
    find_section_by_needle,
    format_currency,
    lookup_row_by_entity,
    parse_validated_answer,
    ranking_row,
)
from orion_mcp_v3.public_chat.domain.fact_engine.confidence import (
    MIN_DERIVE_CONFIDENCE,
    MIN_FACT_CONFIDENCE,
    confidence_for_path,
)
from orion_mcp_v3.public_chat.domain.fact_engine.fact_type import FactType
from orion_mcp_v3.public_chat.domain.fact_engine.gap import FactGap, GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.models import ExtractedFact, FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.semantics import AggregationRule, SourcePriority
from orion_mcp_v3.public_chat.domain.fact_engine.fallback_policy import (
    ResolvedMemoryHit,
    _hit_matches_required_keys,
)
from orion_mcp_v3.public_chat.domain.fact_engine.trace import (
    ExtractionPath,
    FactTrace,
    ResolutionRule,
    fact_trace_from_resolution,
)
from orion_mcp_v3.public_chat.domain.key_metrics_reader import (
    aggregate_row,
    lookup_entity,
    lookup_entity_group,
    rows_from_array,
    rows_from_key_metrics_entry,
    scalar_from_key_metrics,
    sum_row_values,
)
from orion_mcp_v3.public_chat.domain.knowledge import KnowledgeHit
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    facts: tuple[ExtractedFact, ...]
    gaps: tuple[FactGap, ...]


class FactExtractor:
    def extract(
        self,
        requirements: tuple[FactRequirement, ...],
        resolved: dict[str, ResolvedMemoryHit],
        *,
        semantics_version: str = "v1",
    ) -> ExtractionResult:
        t0 = time.monotonic()
        facts: list[ExtractedFact] = []
        gaps: list[FactGap] = []
        extracted_by_key: dict[str, ExtractedFact] = {}

        for requirement in requirements:
            if requirement.semantics.aggregation_rule == AggregationRule.DERIVED:
                continue
            resolved_hit = resolved.get(requirement.fact_key)
            if resolved_hit is None:
                continue
            fact, gap = self._extract_one(requirement, resolved_hit, semantics_version=semantics_version)
            if fact is not None:
                facts.append(fact)
                extracted_by_key[fact.fact_key] = fact
            if gap is not None:
                gaps.append(gap)

        derived_facts, derived_gaps = self._compute_derived(requirements, extracted_by_key, semantics_version)
        facts.extend(derived_facts)
        gaps.extend(derived_gaps)

        result = ExtractionResult(facts=tuple(facts), gaps=tuple(gaps))
        log_public_chat_event(
            etapa="fact.extract",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "fact_count": len(result.facts),
                "gap_count": len(result.gaps),
                "facts": [fact.as_mapping() for fact in result.facts],
                "gaps": [gap.as_mapping() for gap in result.gaps],
            },
        )
        return result

    def _extract_one(
        self,
        requirement: FactRequirement,
        resolved_hit: ResolvedMemoryHit,
        *,
        semantics_version: str,
    ) -> tuple[ExtractedFact | None, FactGap | None]:
        hit = resolved_hit.hit
        resolution_trace = resolved_hit.resolution_trace
        semantics = requirement.semantics

        if not _hit_matches_required_keys(hit, requirement):
            return None, FactGap(
                fact_key=requirement.fact_key,
                reason=GapReason.MEMORY_EXISTS_BUT_NO_MATCH,
                detail="hit missing required key_metrics keys",
                origin_ids_attempted=(hit.origin_id,),
                attempted_rules=(resolution_trace.rule_applied.value,),
                resolution_trace=resolution_trace,
            )

        for source in semantics.source_priority:
            if source == SourcePriority.KEY_METRICS:
                fact = self._from_key_metrics(requirement, hit, resolution_trace)
                if fact is not None:
                    return fact, None
            elif source in (SourcePriority.STRUCTURED, SourcePriority.PARSED_TEXT):
                fact = self._from_parsed_text(requirement, hit, resolution_trace)
                if fact is not None:
                    return fact, None

        return None, FactGap(
            fact_key=requirement.fact_key,
            reason=GapReason.EXTRACTION_FAILED,
            detail="all source_priority paths failed",
            origin_ids_attempted=(hit.origin_id,),
            attempted_rules=(resolution_trace.rule_applied.value,),
            resolution_trace=resolution_trace,
        )

    def _from_key_metrics(
        self,
        requirement: FactRequirement,
        hit: KnowledgeHit,
        resolution_trace,
    ) -> ExtractedFact | None:
        semantics = requirement.semantics
        keys = semantics.key_metrics_keys or ("faturamento_liquido",)

        scalar = scalar_from_key_metrics(hit.key_metrics, keys)
        if scalar is not None and semantics.aggregation_rule == AggregationRule.LOOKUP and not requirement.entity:
            key, value = scalar
            return self._build_key_metrics_fact(
                requirement,
                hit,
                resolution_trace,
                label=key,
                value=value,
            )

        entity_fields = (semantics.key_metrics_entity_field, "tipo", "label", "metric")
        value_fields = (semantics.key_metrics_value_field, "valor", "value")
        _ = (entity_fields, value_fields)

        for key in keys:
            raw = hit.key_metrics.get(key)
            if raw is None:
                continue
            rows = rows_from_key_metrics_entry(key, raw)
            if not rows:
                continue

            value_field = semantics.key_metrics_value_field
            if value_field == "percentual":
                rows = _rows_with_percentual_values(rows)

            if semantics.aggregation_rule == AggregationRule.LOOKUP:
                if requirement.entity:
                    row = lookup_entity_group(rows, requirement.entity) or lookup_entity(rows, requirement.entity)
                    if row is None:
                        continue
                    display = row.percentual or row.raw_value if value_field == "percentual" else row.raw_value
                    return self._build_key_metrics_fact(
                        requirement,
                        hit,
                        resolution_trace,
                        label=row.label,
                        value=row.value,
                        display_value=display,
                        unit="pct" if value_field == "percentual" else "BRL",
                    )
                if semantics.fact_key == "faturamento_total_periodo":
                    total = sum_row_values(rows)
                    if total is not None:
                        return self._build_key_metrics_fact(
                            requirement,
                            hit,
                            resolution_trace,
                            label=key,
                            value=total,
                        )
                continue

            if semantics.aggregation_rule in (AggregationRule.MIN, AggregationRule.MAX):
                ascending = semantics.aggregation_rule == AggregationRule.MIN
                row = aggregate_row(rows, ascending=ascending)
                if row is None:
                    continue
                display = row.percentual or row.raw_value if value_field == "percentual" else row.raw_value
                return self._build_key_metrics_fact(
                    requirement,
                    hit,
                    resolution_trace,
                    label=row.label,
                    value=row.value,
                    display_value=display,
                    unit="pct" if value_field == "percentual" else "BRL",
                )

        return None

    def _build_key_metrics_fact(
        self,
        requirement: FactRequirement,
        hit: KnowledgeHit,
        resolution_trace,
        *,
        label: str,
        value: float,
        display_value: str | None = None,
        unit: str = "BRL",
    ) -> ExtractedFact | None:
        confidence = confidence_for_path(ExtractionPath.KEY_METRICS)
        if confidence < MIN_FACT_CONFIDENCE:
            return None
        return ExtractedFact(
            fact_key=requirement.fact_key,
            label=label,
            value=display_value or format_currency(value),
            unit=unit,
            fact_type=FactType.RAW,
            confidence=confidence,
            origin_id=hit.origin_id,
            context_key=hit.context_key,
            trace=fact_trace_from_resolution(resolution_trace, ExtractionPath.KEY_METRICS),
        )

    def _from_parsed_text(
        self,
        requirement: FactRequirement,
        hit: KnowledgeHit,
        resolution_trace,
    ) -> ExtractedFact | None:
        sections = parse_validated_answer(hit.validated_answer)
        semantics = requirement.semantics

        if semantics.fact_key.startswith("ranking_forma_pagamento"):
            section = find_section_by_needle(sections, "forma de pagamento", "formas de pagamento")
            if section is None:
                return None
            ascending = semantics.comparator.value == "asc"
            row = ranking_row(section, ascending=ascending)
            if row is None:
                return None
            path = ExtractionPath.RANKING_DERIVED
            confidence = confidence_for_path(path)
            return ExtractedFact(
                fact_key=requirement.fact_key,
                label=row.label,
                value=row.raw_value,
                unit="BRL",
                fact_type=FactType.RAW,
                confidence=confidence,
                origin_id=hit.origin_id,
                context_key=hit.context_key,
                trace=fact_trace_from_resolution(resolution_trace, path),
            )

        if semantics.aggregation_rule == AggregationRule.LOOKUP:
            for key in semantics.key_metrics_keys:
                raw = hit.key_metrics.get(key)
                if raw is not None:
                    try:
                        value = float(raw)
                    except (TypeError, ValueError):
                        continue
                    return ExtractedFact(
                        fact_key=requirement.fact_key,
                        label="faturamento_liquido",
                        value=format_currency(value),
                        unit="BRL",
                        fact_type=FactType.RAW,
                        confidence=confidence_for_path(ExtractionPath.STRUCTURED_PARSER),
                        origin_id=hit.origin_id,
                        context_key=hit.context_key,
                        trace=fact_trace_from_resolution(
                            resolution_trace,
                            ExtractionPath.STRUCTURED_PARSER,
                        ),
                    )
        return None

    def _compute_derived(
        self,
        requirements: tuple[FactRequirement, ...],
        extracted: dict[str, ExtractedFact],
        semantics_version: str,
    ) -> tuple[list[ExtractedFact], list[FactGap]]:
        facts: list[ExtractedFact] = []
        gaps: list[FactGap] = []
        for requirement in requirements:
            if requirement.semantics.aggregation_rule != AggregationRule.DERIVED:
                continue
            parents = requirement.semantics.derived_from
            parent_facts = [extracted.get(key) for key in parents]
            if any(item is None for item in parent_facts):
                gaps.append(
                    FactGap(
                        fact_key=requirement.fact_key,
                        reason=GapReason.EXTRACTION_FAILED,
                        detail="missing parent facts for derivation",
                    )
                )
                continue
            assert all(item is not None for item in parent_facts)
            parent_values = [self._numeric_value(item) for item in parent_facts if item is not None]
            if len(parent_values) != 2 or parent_values[1] == 0:
                gaps.append(
                    FactGap(
                        fact_key=requirement.fact_key,
                        reason=GapReason.EXTRACTION_FAILED,
                        detail="invalid parent values for derivation",
                    )
                )
                continue
            if any(item.confidence < MIN_DERIVE_CONFIDENCE for item in parent_facts if item):
                gaps.append(
                    FactGap(
                        fact_key=requirement.fact_key,
                        reason=GapReason.LOW_CONFIDENCE,
                        detail=f"parents below {MIN_DERIVE_CONFIDENCE}",
                    )
                )
                continue
            ratio = (parent_values[0] / parent_values[1]) * 100.0
            origin_ids = tuple(item.origin_id for item in parent_facts if item)
            context_keys = tuple(item.context_key for item in parent_facts if item)
            facts.append(
                ExtractedFact(
                    fact_key=requirement.fact_key,
                    label="participação oficina",
                    value=f"{ratio:.2f}%",
                    unit="pct",
                    fact_type=FactType.DERIVED,
                    confidence=confidence_for_path(ExtractionPath.DERIVED_COMPUTE),
                    origin_id=origin_ids[0],
                    context_key=context_keys[0],
                    trace=FactTrace(
                        fact_key=requirement.fact_key,
                        resolved_from=origin_ids,
                        context_keys=context_keys,
                        rule_applied=ResolutionRule.JOIN_PLAN,
                        extraction_path=ExtractionPath.DERIVED_COMPUTE,
                        semantics_version=semantics_version,
                    ),
                )
            )
        return facts, gaps

    def _numeric_value(self, fact: ExtractedFact) -> float:
        text = fact.value.replace("R$", "").replace("%", "").strip()
        text = text.replace(".", "").replace(",", ".")
        return float(text)


def _rows_with_percentual_values(rows: tuple) -> tuple:
    from orion_mcp_v3.public_chat.domain.key_metrics_reader import KeyMetricsRow, parse_metric_value

    converted: list[KeyMetricsRow] = []
    for row in rows:
        if row.percentual:
            value = parse_metric_value(row.percentual)
            if value is not None:
                converted.append(
                    KeyMetricsRow(
                        label=row.label,
                        value=value,
                        raw_value=row.percentual,
                        percentual=row.percentual,
                    )
                )
    return tuple(converted) if converted else rows
