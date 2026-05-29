"""Validação determinística do contrato de intenção analítica."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from orion_mcp_v3.broker.query_capability_catalog import QueryCapabilityCatalog
from orion_mcp_v3.contracts.analytical_intent import (
    AnalyticalIntentContract,
    AnalyticalIntentType,
    AnalyticalOperation,
    SourcePeriods,
)
from orion_mcp_v3.contracts.cognitive_plan import AttentionProfile, CognitivePlan, IntentType
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy


@dataclass(frozen=True, slots=True)
class IntentValidationResult:
    accepted: bool
    contract: AnalyticalIntentContract | None = None
    cognitive_plan: CognitivePlan | None = None
    rejected_reason: str | None = None


class IntentContractValidator:
    def __init__(self, catalog: QueryCapabilityCatalog) -> None:
        self._catalog = catalog

    def validate(
        self,
        contract: AnalyticalIntentContract,
        *,
        heuristic_plan: CognitivePlan,
        has_analytical_memory: bool = False,
    ) -> IntentValidationResult:
        if contract.confidence < 0.55:
            return self._reject("confidence_too_low")
        if not _dates_valid(contract):
            return self._reject("invalid_date_range")

        template_slug = contract.template_slug.strip() if contract.template_slug else None
        if template_slug is not None and self._catalog.entry_for_template(template_slug) is None:
            return self._reject("unsupported_template")

        dimension = _resolve_key(contract.dimension, self._dimension_aliases(template_slug))
        metric = self._resolve_metric(contract.metric, dimension=dimension, template_slug=template_slug)
        operation = contract.operation.value
        entity_filters = _normalize_entity_filters(
            contract.entity_filters,
            self._dimension_aliases(template_slug),
        )

        if contract.needs_analytics:
            if metric is not None and not self._catalog.supports(
                template_slug=template_slug,
                metric=metric,
            ):
                return self._reject("unsupported_metric")
            if dimension is not None and not self._catalog.supports(
                template_slug=template_slug,
                dimension=dimension,
            ):
                return self._reject("unsupported_dimension")
            if not self._operation_supported(
                operation,
                template_slug=template_slug,
                metric=metric,
                dimension=dimension,
            ):
                return self._reject("unsupported_operation")
        if contract.needs_comparison and not _comparison_has_sources(contract, has_analytical_memory):
            return self._reject("comparison_without_sources")

        normalized = AnalyticalIntentContract(
            intent_type=contract.intent_type,
            operation=contract.operation,
            needs_analytics=contract.needs_analytics,
            needs_memory=contract.needs_memory,
            needs_comparison=contract.needs_comparison,
            template_slug=template_slug,
            metric=metric,
            dimension=dimension,
            date_ranges=contract.date_ranges,
            source_periods=contract.source_periods,
            inherits_from_previous=contract.inherits_from_previous,
            entity_filters=entity_filters,
            confidence=contract.confidence,
        )
        return IntentValidationResult(
            accepted=True,
            contract=normalized,
            cognitive_plan=_contract_to_plan(normalized, heuristic_plan),
        )

    @staticmethod
    def _reject(reason: str) -> IntentValidationResult:
        return IntentValidationResult(accepted=False, rejected_reason=reason)

    def _resolve_metric(
        self,
        value: str | None,
        *,
        dimension: str | None,
        template_slug: str | None,
    ) -> str | None:
        if value is None:
            return None
        aliases: dict[str, tuple[str, ...]] = {
            "revenue": ("faturamento", "valor_total", "total_recebido", "valor_total_recebido"),
            "sales": ("vendas", "quantidade_os", "total_vendas"),
            "ticket": ("ticket_medio",),
            "recebimento": ("valor_total_recebido", "total_recebido", "faturamento", "valor_total"),
        }
        raw = value.strip().lower()
        candidates = (raw, *aliases.get(raw, ()))
        for candidate in candidates:
            for entry in self._catalog.entries:
                if template_slug is not None and entry.template_slug != template_slug:
                    continue
                if dimension is not None and dimension not in entry.dimensions:
                    continue
                for key, synonyms in entry.metrics.items():
                    values = {key.lower(), *(synonym.lower() for synonym in synonyms)}
                    if candidate.lower() in values:
                        return key
        return value.strip()

    def _dimension_aliases(self, template_slug: str | None = None) -> dict[str, str]:
        aliases: dict[str, str] = {
            "seller": "vendedor",
            "dealership": "concessionaria",
            "payment_method": "forma_pagamento",
        }
        for entry in self._catalog.entries:
            if template_slug is not None and entry.template_slug != template_slug:
                continue
            for key, synonyms in entry.dimensions.items():
                aliases[key.lower()] = key
                for synonym in synonyms:
                    aliases[synonym.lower()] = key
        return aliases

    def _operation_supported(
        self,
        operation: str,
        *,
        template_slug: str | None,
        metric: str | None,
        dimension: str | None,
    ) -> bool:
        if operation in {AnalyticalOperation.COMPARISON.value, AnalyticalOperation.DELTA.value}:
            return self._catalog.supports(
                template_slug=template_slug,
                metric=metric,
                dimension=dimension,
            )
        return self._catalog.supports(
            template_slug=template_slug,
            metric=metric,
            dimension=dimension,
            operation=operation,
        )


def _contract_to_plan(contract: AnalyticalIntentContract, heuristic_plan: CognitivePlan) -> CognitivePlan:
    intent = _intent_type(contract.intent_type)
    time_scope = _time_scope(contract)
    hints = {
        **dict(heuristic_plan.hints or {}),
        "resolver": "llm_intent_interpreter_v1",
        "intent_contract": contract.as_dict(),
    }
    if contract.template_slug:
        hints["template_slug"] = contract.template_slug
    if contract.entity_filters:
        hints["entity_filters"] = contract.entity_filters
    if time_scope:
        date_from, date_to = time_scope.split("/", 1)
        hints.update({"date_from": date_from, "date_to": date_to})

    return CognitivePlan(
        intent_type=intent,
        needs_memory=contract.needs_memory,
        needs_analytics=contract.needs_analytics,
        needs_comparison=contract.needs_comparison,
        needs_temporal_context=bool(time_scope) or heuristic_plan.needs_temporal_context,
        needs_baseline=contract.needs_comparison and contract.needs_analytics,
        needs_trend_analysis=contract.needs_analytics and (bool(time_scope) or contract.needs_comparison),
        needs_entity_resolution=bool(contract.dimension) or heuristic_plan.needs_entity_resolution,
        confidence=contract.confidence,
        entities=(contract.dimension,) if contract.dimension else heuristic_plan.entities,
        metrics=(contract.metric,) if contract.metric else heuristic_plan.metrics,
        time_scope=time_scope or heuristic_plan.time_scope,
        retrieval_strategy=(
            RetrievalStrategy.HYBRID
            if contract.needs_analytics and contract.needs_memory
            else RetrievalStrategy.BROKER_FANOUT
            if contract.needs_analytics
            else RetrievalStrategy.KEYWORD
        ),
        attention_profile=_attention_profile(intent, contract),
        hints=hints,
    )


def _intent_type(value: AnalyticalIntentType) -> IntentType:
    return {
        AnalyticalIntentType.ANALYTICAL: IntentType.ANALYTICAL,
        AnalyticalIntentType.COMPARATIVE: IntentType.COMPARATIVE,
        AnalyticalIntentType.TEMPORAL: IntentType.TEMPORAL,
        AnalyticalIntentType.RECALL: IntentType.RECALL,
        AnalyticalIntentType.MONITORING: IntentType.MONITORING,
        AnalyticalIntentType.EXECUTION: IntentType.EXECUTION,
        AnalyticalIntentType.HYBRID: IntentType.HYBRID,
        AnalyticalIntentType.CONVERSATIONAL: IntentType.CONVERSATIONAL,
    }[value]


def _attention_profile(intent: IntentType, contract: AnalyticalIntentContract) -> AttentionProfile:
    if intent == IntentType.MONITORING:
        return AttentionProfile.MONITORING
    if intent == IntentType.EXECUTION:
        return AttentionProfile.EXECUTION
    if intent in (IntentType.HYBRID, IntentType.COMPARATIVE) or (
        contract.needs_analytics and contract.needs_memory
    ):
        return AttentionProfile.HYBRID
    if contract.needs_analytics:
        return AttentionProfile.ANALYTICAL
    if contract.needs_memory:
        return AttentionProfile.MEMORY_FOCUSED
    return AttentionProfile.CONVERSATIONAL


def _time_scope(contract: AnalyticalIntentContract) -> str | None:
    ranges = sorted(contract.date_ranges, key=lambda r: r.date_from)
    if not ranges:
        return None
    return f"{ranges[0].date_from}/{max(r.date_to for r in ranges)}"


def _dates_valid(contract: AnalyticalIntentContract) -> bool:
    for item in contract.date_ranges:
        start = _parse_date(item.date_from)
        end = _parse_date(item.date_to)
        if start is None or end is None or end < start:
            return False
    return True


def _parse_date(raw: str) -> date | None:
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw or "") is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _normalize_entity_filters(
    filters: tuple[dict[str, str], ...],
    aliases: dict[str, str],
) -> tuple[dict[str, str], ...]:
    out: list[dict[str, str]] = []
    for item in filters:
        dimension = _resolve_key(item.get("dimension"), aliases)
        value = str(item.get("value") or "").strip()
        if dimension is None or not value:
            continue
        if dimension in _TEMPORAL_FILTER_DIMENSIONS:
            continue
        match = _normalize_filter_match(
            dimension=dimension,
            value=value,
            match=str(item.get("match") or "contains"),
        )
        out.append({"dimension": dimension, "value": value, "match": match})
    return tuple(out)


def _normalize_filter_match(*, dimension: str, value: str, match: str) -> str:
    normalized = match.strip().lower()
    if normalized not in {"contains", "exact"}:
        normalized = "contains"
    if normalized != "exact":
        return normalized
    if dimension in {"periodo", "data_pagamento"} and re.fullmatch(r"20\d{2}(?:-\d{2})?(?:-\d{2})?", value):
        return "exact"
    return "contains"


_TEMPORAL_FILTER_DIMENSIONS = frozenset({"periodo", "data_pagamento"})


def _comparison_has_sources(contract: AnalyticalIntentContract, has_analytical_memory: bool) -> bool:
    return (
        len(contract.date_ranges) >= 2
        or contract.source_periods == SourcePeriods.LAST_TWO_ANALYTICAL_TURNS
        and has_analytical_memory
    )


def _resolve_key(value: str | None, aliases: dict[str, str]) -> str | None:
    if value is None:
        return None
    return aliases.get(value.strip().lower(), value.strip())
