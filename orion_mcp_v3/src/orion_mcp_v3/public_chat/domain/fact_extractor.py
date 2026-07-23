"""Extracção de facts concretos a partir de memórias resolvidas."""

from __future__ import annotations

import re
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
from orion_mcp_v3.public_chat.domain.key_metrics_introspection import (
    partition_scope_entities,
    scope_axes_from_hit_meta,
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

PARTIAL_RANKING_CONFIDENCE = 0.4
_PERIOD_DELTA_OPERATIONS = frozenset(
    {"period_growth", "period_decline"},
)
_RANKING_OPERATIONS = frozenset(
    {"ranking_asc", "ranking_desc", "min", "max", "leader_change", "period_growth", "period_decline", "time_series", "cumulative"},
)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    facts: tuple[ExtractedFact, ...]
    gaps: tuple[FactGap, ...]
    ranking_base_rows: int | None = None
    source_truncated: bool = False


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
        ranking_base_rows: int | None = None
        source_truncated = False

        cross_period_keys = _period_delta_fact_keys(requirements, resolved)
        for requirement in requirements:
            if requirement.semantics.aggregation_rule == AggregationRule.DERIVED:
                continue
            if requirement.fact_key in cross_period_keys:
                continue
            resolved_hit = resolved.get(requirement.fact_key)
            if resolved_hit is None:
                continue
            if _key_metrics_truncated(resolved_hit.hit, requirement):
                source_truncated = True
            fact, gap, base_rows = self._extract_one(
                requirement,
                resolved_hit,
                semantics_version=semantics_version,
            )
            if fact is not None:
                facts.append(fact)
                extracted_by_key[fact.fact_key] = fact
                if base_rows is not None:
                    ranking_base_rows = (
                        base_rows
                        if ranking_base_rows is None
                        else min(ranking_base_rows, base_rows)
                    )
            if gap is not None:
                gaps.append(gap)

        # Growth/leader composition moved to KnowledgeComposer — extractor só resolve leafs.
        derived_facts, derived_gaps = self._compute_derived(requirements, extracted_by_key, semantics_version)
        facts.extend(derived_facts)
        gaps.extend(derived_gaps)

        result = ExtractionResult(
            facts=tuple(facts),
            gaps=tuple(gaps),
            ranking_base_rows=ranking_base_rows,
            source_truncated=source_truncated,
        )
        discarded_scope = [
            item
            for fact in result.facts
            for item in fact.trace.discarded_scope
        ]
        log_public_chat_event(
            etapa="fact.extract",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "fact_count": len(result.facts),
                "gap_count": len(result.gaps),
                "ranking_base_rows": result.ranking_base_rows,
                "source_truncated": result.source_truncated,
                "facts": [fact.as_mapping() for fact in result.facts],
                "gaps": [gap.as_mapping() for gap in result.gaps],
                "discarded_scope": discarded_scope,
            },
        )
        return result

    def _extract_one(
        self,
        requirement: FactRequirement,
        resolved_hit: ResolvedMemoryHit,
        *,
        semantics_version: str,
    ) -> tuple[ExtractedFact | None, FactGap | None, int | None]:
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
            ), None

        for source in semantics.source_priority:
            if source == SourcePriority.KEY_METRICS:
                fact, base_rows = self._from_key_metrics(requirement, hit, resolution_trace)
                if fact is not None:
                    return fact, None, base_rows
            elif source in (SourcePriority.STRUCTURED, SourcePriority.PARSED_TEXT):
                fact = self._from_parsed_text(requirement, hit, resolution_trace)
                if fact is not None:
                    return fact, None, 1 if requirement.entity else None

        return None, FactGap(
            fact_key=requirement.fact_key,
            reason=GapReason.EXTRACTION_FAILED,
            detail="all source_priority paths failed",
            origin_ids_attempted=(hit.origin_id,),
            attempted_rules=(resolution_trace.rule_applied.value,),
            resolution_trace=resolution_trace,
        ), None

    def _from_key_metrics(
        self,
        requirement: FactRequirement,
        hit: KnowledgeHit,
        resolution_trace,
    ) -> tuple[ExtractedFact | None, int | None]:
        semantics = requirement.semantics
        keys = semantics.key_metrics_keys or ("faturamento_liquido",)
        axes = scope_axes_from_hit_meta(hit, requirement.matched_key)
        applicable_scope, extract_discarded = partition_scope_entities(
            requirement.scope_entities,
            axes,
        )
        discarded_scope = _merge_discarded_scope(
            requirement.discarded_scope,
            extract_discarded,
        )

        scalar = scalar_from_key_metrics(hit.key_metrics, keys)
        if scalar is not None and semantics.aggregation_rule == AggregationRule.LOOKUP and not requirement.entity:
            key, value = scalar
            return self._build_key_metrics_fact(
                requirement,
                hit,
                resolution_trace,
                label=key,
                value=value,
                discarded_scope=discarded_scope,
            ), 1

        for key in keys:
            raw = hit.key_metrics.get(key)
            if raw is None:
                continue
            rows = rows_from_key_metrics_entry(key, raw)
            if not rows:
                continue

            if applicable_scope:
                rows = _filter_rows_by_scope(rows, applicable_scope)

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
                        discarded_scope=discarded_scope,
                    ), 1
                if semantics.fact_key == "faturamento_total_periodo":
                    total = sum_row_values(rows)
                    if total is not None:
                        return self._build_key_metrics_fact(
                            requirement,
                            hit,
                            resolution_trace,
                            label=key,
                            value=total,
                            discarded_scope=discarded_scope,
                        ), len(rows)
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
                    discarded_scope=discarded_scope,
                ), len(rows)

        return None, None

    def _compute_cross_period_ranking(
        self,
        requirements: tuple[FactRequirement, ...],
        resolved: dict[str, ResolvedMemoryHit],
        *,
        semantics_version: str,
        skip_keys: frozenset[str],
    ) -> tuple[list[ExtractedFact], list[FactGap], int | None, bool]:
        if not skip_keys:
            return [], [], None, False
        groups: dict[str, list[FactRequirement]] = {}
        for requirement in requirements:
            if requirement.fact_key not in skip_keys:
                continue
            key = requirement.matched_key or ""
            groups.setdefault(key, []).append(requirement)

        facts: list[ExtractedFact] = []
        gaps: list[FactGap] = []
        comparable_rows: int | None = None
        truncated = False
        for matched_key, group in groups.items():
            if len(group) < 2 or not matched_key:
                continue
            period_rows: list[tuple[FactRequirement, ResolvedMemoryHit, tuple]] = []
            for requirement in group:
                resolved_hit = resolved.get(requirement.fact_key)
                if resolved_hit is None:
                    continue
                if _key_metrics_truncated(resolved_hit.hit, requirement):
                    truncated = True
                rows = _rows_for_requirement(requirement, resolved_hit.hit)
                if rows:
                    period_rows.append((requirement, resolved_hit, rows))
            if len(period_rows) < 2:
                continue
            # Ordena por período para crescimento = final - inicial
            period_rows.sort(key=lambda item: item[0].period or "")
            first_req, first_hit, first_rows = period_rows[0]
            last_req, last_hit, last_rows = period_rows[-1]
            growth = _growth_by_label(first_rows, last_rows)
            if not growth:
                gaps.append(
                    FactGap(
                        fact_key=f"dynamic:{matched_key}@growth",
                        reason=GapReason.EXTRACTION_FAILED,
                        detail="no intersecting entities across periods for ranking growth",
                    )
                )
                continue
            ascending = (first_req.operation or "").lower() in (
                "ranking_asc",
                "min",
            )
            ranked = sorted(growth.items(), key=lambda item: item[1], reverse=not ascending)
            winner_label, winner_pct = ranked[0]
            comparable_rows = len(growth) if comparable_rows is None else min(comparable_rows, len(growth))
            confidence = confidence_for_path(ExtractionPath.RANKING_DERIVED)
            if comparable_rows <= 1 or truncated:
                confidence = min(confidence, PARTIAL_RANKING_CONFIDENCE)
            fact_key = f"dynamic:{matched_key}@growth:{first_req.period or ''}:{last_req.period or ''}"
            facts.append(
                ExtractedFact(
                    fact_key=fact_key,
                    label=winner_label,
                    value=f"{winner_pct:.2f}%",
                    unit="pct",
                    fact_type=FactType.DERIVED,
                    confidence=confidence,
                    origin_id=last_hit.hit.origin_id,
                    context_key=last_hit.hit.context_key,
                    trace=FactTrace(
                        fact_key=fact_key,
                        resolved_from=(first_hit.hit.origin_id, last_hit.hit.origin_id),
                        context_keys=(first_hit.hit.context_key, last_hit.hit.context_key),
                        rule_applied=ResolutionRule.JOIN_PLAN,
                        extraction_path=ExtractionPath.RANKING_DERIVED,
                        semantics_version=semantics_version,
                    ),
                )
            )
        return facts, gaps, comparable_rows, truncated

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
        discarded_scope: tuple[dict[str, str], ...] = (),
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
            trace=fact_trace_from_resolution(
                resolution_trace,
                ExtractionPath.KEY_METRICS,
                discarded_scope=discarded_scope,
            ),
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


def _merge_discarded_scope(
    *groups: tuple[dict[str, str], ...],
) -> tuple[dict[str, str], ...]:
    merged: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for group in groups:
        for item in group:
            key = (item.get("dimension", ""), item.get("value", ""), item.get("reason", ""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return tuple(merged)


def _filter_rows_by_scope(
    rows: tuple,
    scope_entities: tuple[tuple[str, str] | tuple[str, str, str], ...],
) -> tuple:
    from orion_mcp_v3.public_chat.domain.key_metrics_reader import KeyMetricsRow, label_matches_scope

    filtered = rows
    for item in scope_entities:
        value = item[1]
        match = item[2] if len(item) >= 3 else "exact"
        filtered = tuple(
            row
            for row in filtered
            if isinstance(row, KeyMetricsRow)
            and label_matches_scope(row.label, value, match=match)
        )
    return filtered


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


def _period_delta_fact_keys(
    requirements: tuple[FactRequirement, ...],
    resolved: dict[str, ResolvedMemoryHit],
) -> frozenset[str]:
    """Só period_growth/period_decline colapsam em delta — nunca leader_change/ranking_*."""
    buckets: dict[str, list[FactRequirement]] = {}
    for requirement in requirements:
        operation = (requirement.operation or "").lower()
        if operation not in _PERIOD_DELTA_OPERATIONS:
            continue
        if requirement.entity:
            continue
        if requirement.fact_key not in resolved:
            continue
        matched = requirement.matched_key or ""
        if not matched:
            continue
        buckets.setdefault(matched, []).append(requirement)
    keys: set[str] = set()
    for group in buckets.values():
        periods = {req.period for req in group if req.period}
        if len(periods) < 2:
            continue
        for req in group:
            keys.add(req.fact_key)
    return frozenset(keys)


# Compat alias (testes/imports legados)
def _cross_period_ranking_fact_keys(
    requirements: tuple[FactRequirement, ...],
    resolved: dict[str, ResolvedMemoryHit],
) -> frozenset[str]:
    return _period_delta_fact_keys(requirements, resolved)


def _rows_for_requirement(requirement: FactRequirement, hit: KnowledgeHit) -> tuple:
    keys = requirement.semantics.key_metrics_keys or ()
    for key in keys:
        raw = hit.key_metrics.get(key)
        if raw is None:
            continue
        meta = raw.get("_meta") if isinstance(raw, dict) else None
        truncated = isinstance(meta, dict) and meta.get("truncated_head_tail") is True
        if truncated and hit.validated_answer:
            rebuilt = _rows_from_validated_answer(hit.validated_answer)
            total = meta.get("total_original_rows") if isinstance(meta, dict) else None
            if rebuilt and _reconstruction_covers_total(rebuilt, total):
                return rebuilt
        rows = rows_from_key_metrics_entry(key, raw)
        if rows:
            return rows
    if hit.validated_answer:
        rebuilt = _rows_from_validated_answer(hit.validated_answer)
        if rebuilt:
            return rebuilt
    return ()


def _reconstruction_covers_total(rows: tuple, total: object) -> bool:
    if total is None:
        return len(rows) > 1
    try:
        return len(rows) >= int(total)
    except (TypeError, ValueError):
        return len(rows) > 1


def _rows_from_validated_answer(text: str) -> tuple:
    """Reconstrói ranked_list a partir do texto completo (evita truncated_head_tail)."""
    from orion_mcp_v3.public_chat.domain.key_metrics_reader import KeyMetricsRow, parse_metric_value

    pattern = re.compile(
        r"(?:(?<=^)|(?<=\n)|(?<=\s))(?:\d+\.\s*)?"
        r"(?P<name>[A-Za-zÀ-ÿ][^:\n]{0,80}?):\s*"
        r"(?P<raw>R\$\s*[\d.]+,\d{2}(?:\s*\([\d.,]+%\))?)",
        re.MULTILINE,
    )
    rows: list[KeyMetricsRow] = []
    seen: set[str] = set()
    for match in pattern.finditer(text or ""):
        name = match.group("name").strip()
        if name.upper().startswith("COMISS") or "PERIODO" in name.upper():
            continue
        raw = match.group("raw")
        value = parse_metric_value(raw)
        if value is None or not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        pct_match = re.search(r"\(([\d.,]+)%\)", raw)
        percentual = f"{pct_match.group(1)}%" if pct_match else None
        rows.append(
            KeyMetricsRow(
                label=name,
                value=value,
                raw_value=raw,
                percentual=percentual,
            )
        )
    return tuple(rows)


def _normalize_row_label(label: str) -> str:
    return "".join(ch for ch in label.lower().strip() if ch.isalnum())


def _growth_by_label(first_rows: tuple, last_rows: tuple) -> dict[str, float]:
    first_map = {_normalize_row_label(row.label): row for row in first_rows if row.label}
    last_map = {_normalize_row_label(row.label): row for row in last_rows if row.label}
    growth: dict[str, float] = {}
    for key, first_row in first_map.items():
        last_row = last_map.get(key)
        if last_row is None:
            continue
        if first_row.value == 0:
            continue
        pct = ((last_row.value - first_row.value) / first_row.value) * 100.0
        growth[first_row.label] = pct
    return growth


def _key_metrics_truncated(hit: KnowledgeHit, requirement: FactRequirement) -> bool:
    for key in requirement.semantics.key_metrics_keys or ():
        raw = hit.key_metrics.get(key)
        if not isinstance(raw, dict):
            continue
        meta = raw.get("_meta")
        if not (isinstance(meta, dict) and meta.get("truncated_head_tail") is True):
            continue
        # Reconstrução completa a partir de validated_answer anula o truncamento.
        if hit.validated_answer:
            rebuilt = _rows_from_validated_answer(hit.validated_answer)
            if rebuilt and _reconstruction_covers_total(rebuilt, meta.get("total_original_rows")):
                continue
        return True
    return False
