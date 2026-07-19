"""Orquestrador único de requirements analíticos pós-retrieval."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from typing import Any

from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider
from orion_mcp_v3.public_chat.domain.composition_planner import CompositionPlanner, NoOpCompositionPlanner
from orion_mcp_v3.public_chat.domain.fact_engine.gap import FactGap, GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.requirement_kind import RequirementKind
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.intent_heuristics import sanitize_ranking_entity_filters
from orion_mcp_v3.public_chat.domain.key_metrics_introspection import (
    HeuristicStatus,
    KeyMetricsIndexEntry,
    MatchMethod,
    available_key_metrics_payload,
    build_dynamic_requirement,
    build_key_metrics_index_from_hits,
    dimensions_from_contract,
    expand_same_key_period_from_index,
    find_key_metrics_source,
    period_from_context_key,
    same_key_only_period_ambiguity,
    should_include_period_in_fact_key,
)
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
from orion_mcp_v3.public_chat.domain.period_selection import (
    comparison_operand_dimensions,
    entities_for_dimension,
    non_period_entity_filters,
    periods_from_contract,
    scope_entity_tuples,
)
from orion_mcp_v3.public_chat.domain.period_utils import period_in_context_key
from orion_mcp_v3.public_chat.domain.special_requirements import NoOpSpecialCatalog, SpecialRequirementsCatalog
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event
from orion_mcp_v3.public_chat.prompts import get_public_chat_prompt_registry


@dataclass(frozen=True, slots=True)
class FactPlanResult:
    requirements: tuple[FactRequirement, ...]
    composite: bool
    used_llm_fallback: bool
    used_llm_disambiguation: bool
    confidence: float
    gaps: tuple[FactGap, ...] = ()


async def plan_analytical_requirements(
    message: str,
    *,
    contract: IntentContract,
    knowledge: ConhecimentoRecuperado,
    llm: LLMProvider | None = None,
    special_catalog: SpecialRequirementsCatalog | None = None,
    composition_planner: CompositionPlanner | None = None,
    max_tokens: int = 512,
) -> FactPlanResult:
    t0 = time.monotonic()
    special = special_catalog or NoOpSpecialCatalog()
    composition = composition_planner or NoOpCompositionPlanner()
    contract = sanitize_ranking_entity_filters(contract)

    index = build_key_metrics_index_from_hits(knowledge.hits)
    if not index:
        result = FactPlanResult(
            requirements=(),
            composite=False,
            used_llm_fallback=False,
            used_llm_disambiguation=False,
            confidence=contract.confidence,
            gaps=(
                FactGap(
                    fact_key="dynamic:*",
                    reason=GapReason.NOT_FOUND,
                    detail="no key_metrics in retrieved hit",
                ),
            ),
        )
        _log_plan(result, t0)
        return result

    lookup_reqs, lookup_gaps, used_llm = await _resolve_lookup_requirements(
        message,
        contract=contract,
        index=index,
        llm=llm,
        max_tokens=max_tokens,
    )

    derived_reqs = special.build(
        message,
        contract=contract,
        knowledge=knowledge,
        lookup_requirements=lookup_reqs,
    )
    compose_reqs = composition.build(
        message,
        contract=contract,
        knowledge=knowledge,
        lookup_requirements=lookup_reqs,
    )

    requirements = _merge_requirements(lookup_reqs, derived_reqs, compose_reqs)
    composite = len(requirements) >= 2 or any(
        req.requirement_kind == RequirementKind.COMPOSITION for req in requirements
    )

    result = FactPlanResult(
        requirements=requirements,
        composite=composite,
        used_llm_fallback=False,
        used_llm_disambiguation=used_llm,
        confidence=contract.confidence,
        gaps=tuple(lookup_gaps),
    )
    _log_plan(result, t0, index=index)
    return result


async def _resolve_lookup_requirements(
    message: str,
    *,
    contract: IntentContract,
    index: tuple[KeyMetricsIndexEntry, ...],
    llm: LLMProvider | None,
    max_tokens: int,
) -> tuple[tuple[FactRequirement, ...], list[FactGap], bool]:
    dims = dimensions_from_contract(contract, message)
    if not dims:
        dims = ("forma_pagamento",) if "pagamento" in message.lower() else dims

    requirements: list[FactRequirement] = []
    gaps: list[FactGap] = []
    used_llm = False
    comparison_periods = periods_from_contract(contract)
    if len(comparison_periods) > 1:
        return await _resolve_period_comparison_requirements(
            message,
            contract=contract,
            periods=comparison_periods,
            dims=dims,
            index=index,
            llm=llm,
            max_tokens=max_tokens,
        )

    operands = comparison_operand_dimensions(contract)
    target_dims = operands if operands else dims

    for dimension in target_dims:
        scope = scope_entity_tuples(
            contract,
            operands,
            exclude_dimensions=(dimension,),
        )
        entities = entities_for_dimension(contract, dimension, message=message) or (None,)
        search_index = index
        if contract.period:
            period_index = _index_for_period(index, contract.period)
            if period_index:
                search_index = period_index

        for entity in entities:
            match = find_key_metrics_source(
                search_index,
                dimension=dimension,
                metric_kind=contract.metric,
                entity=entity,
                message=message,
            )
            entries, gap, llm_used = await _entries_from_match(
                message,
                contract=contract,
                index=index,
                dimension=dimension,
                entity=entity,
                match=match,
                llm=llm,
                max_tokens=max_tokens,
            )
            if llm_used:
                used_llm = True
            if gap is not None:
                gaps.append(gap)
                continue
            for entry in entries:
                period = period_from_context_key(entry.context_key) or contract.period
                requirements.append(
                    build_dynamic_requirement(
                        entry,
                        contract=contract,
                        match_method=MatchMethod.LLM if llm_used else match.match_method,
                        message=message,
                        entity=entity,
                        period=period,
                        scope_entities=scope,
                        exclude_scope_dimensions=(dimension,),
                        include_period_in_key=should_include_period_in_fact_key(
                            contract,
                            index,
                            index_key=entry.key,
                        ),
                    )
                )

    return tuple(requirements), gaps, used_llm


async def _resolve_period_comparison_requirements(
    message: str,
    *,
    contract: IntentContract,
    periods: tuple[str, ...],
    dims: tuple[str, ...],
    index: tuple[KeyMetricsIndexEntry, ...],
    llm: LLMProvider | None,
    max_tokens: int,
) -> tuple[tuple[FactRequirement, ...], list[FactGap], bool]:
    requirements: list[FactRequirement] = []
    gaps: list[FactGap] = []
    used_llm = False
    period_dims = dims or ("periodo",)
    operands = comparison_operand_dimensions(contract)
    target_dims = operands if operands else period_dims

    for period in periods:
        period_index = _index_for_period(index, period)
        candidate_index = period_index or index
        period_contract = replace(
            contract,
            period=period,
            entity_filters=non_period_entity_filters(contract),
        )
        for dimension in target_dims:
            scope = scope_entity_tuples(
                contract,
                operands,
                exclude_dimensions=(dimension,),
            )
            entities = entities_for_dimension(period_contract, dimension, message=message) or (None,)
            for entity in entities:
                match = find_key_metrics_source(
                    candidate_index,
                    dimension=dimension,
                    metric_kind=period_contract.metric,
                    entity=entity,
                    message=message,
                )
                entries, gap, llm_used = await _entries_from_match(
                    message,
                    contract=period_contract,
                    index=candidate_index,
                    dimension=dimension,
                    entity=entity,
                    match=match,
                    llm=llm,
                    max_tokens=max_tokens,
                    period=period,
                )
                if llm_used:
                    used_llm = True
                if gap is not None:
                    gaps.append(gap)
                    continue
                for entry in entries:
                    requirement = build_dynamic_requirement(
                        entry,
                        contract=period_contract,
                        match_method=MatchMethod.LLM if llm_used else match.match_method,
                        message=message,
                        entity=entity,
                        period=period,
                        scope_entities=scope,
                        exclude_scope_dimensions=(dimension,),
                        include_period_in_key=len(periods) > 1,
                    )
                    if not period_index:
                        requirement = _catalog_resolved_requirement(
                            requirement,
                            detail=f"no_index_entry_for_period:{period}",
                        )
                    requirements.append(requirement)

    return tuple(requirements), gaps, used_llm


def _index_for_period(
    index: tuple[KeyMetricsIndexEntry, ...],
    period: str,
) -> tuple[KeyMetricsIndexEntry, ...]:
    return tuple(
        entry
        for entry in index
        if entry.context_key is not None and period_in_context_key(entry.context_key, period)
    )


async def _entries_from_match(
    message: str,
    *,
    contract: IntentContract,
    index: tuple[KeyMetricsIndexEntry, ...],
    dimension: str,
    entity: str | None,
    match,
    llm: LLMProvider | None,
    max_tokens: int,
    period: str | None = None,
) -> tuple[tuple[KeyMetricsIndexEntry, ...], FactGap | None, bool]:
    entity_suffix = f"@{entity}" if entity else ""
    period_suffix = f"@{period}" if period else ""
    gap_key = f"dynamic:{dimension}{entity_suffix}{period_suffix}"

    if match.status == HeuristicStatus.RESOLVED and match.entry is not None:
        return (match.entry,), None, False

    if match.status == HeuristicStatus.AMBIGUOUS:
        if same_key_only_period_ambiguity(match.candidates):
            index_key = match.candidates[0].key
            expanded = expand_same_key_period_from_index(index, index_key=index_key)
            if expanded:
                return expanded, None, False
        resolved = await _llm_disambiguate_index(
            message,
            contract=contract,
            index=index,
            candidates=match.candidates,
            llm=llm,
            max_tokens=max_tokens,
        )
        if resolved is not None:
            return (resolved,), None, True
        return (), FactGap(
            fact_key=gap_key,
            reason=GapReason.KEY_METRICS_INDEX_AMBIGUOUS,
            detail=f"candidates={[entry.key for entry in match.candidates]}",
        ), False

    return (), FactGap(
        fact_key=gap_key,
        reason=GapReason.NOT_FOUND,
        detail=f"dimension={dimension}",
    ), False


def _catalog_resolved_requirement(
    requirement: FactRequirement,
    *,
    detail: str,
) -> FactRequirement:
    return replace(
        requirement,
        source_origin_id=None,
        source_context_key=None,
        source_resolution_mode="catalog_fallback",
        source_resolution_detail=detail,
    )


async def _llm_disambiguate_index(
    message: str,
    *,
    contract: IntentContract,
    index: tuple[KeyMetricsIndexEntry, ...],
    candidates: tuple[KeyMetricsIndexEntry, ...],
    llm: LLMProvider | None,
    max_tokens: int,
) -> KeyMetricsIndexEntry | None:
    if llm is None or not candidates:
        return None
    allowlist = {entry.key for entry in candidates} or {entry.key for entry in index}
    try:
        system = get_public_chat_prompt_registry().get_text("public_chat_fact_planner_index.system")
    except KeyError:
        system = (
            "Escolha o índice key_metrics mais adequado. "
            'Responda JSON: {"sources":[{"key":"..."}],"answerable":true}'
        )
    payload = {
        "message": message,
        "intent_contract": contract.as_mapping(),
        "available_key_metrics": available_key_metrics_payload(candidates or index),
    }
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
    ]
    try:
        response = await llm.complete(messages, max_tokens=max_tokens, temperature=0)
    except Exception:
        return None
    return _parse_llm_index_choice(response.content, allowlist, index)


def _parse_llm_index_choice(
    content: str,
    allowlist: set[str],
    index: tuple[KeyMetricsIndexEntry, ...],
) -> KeyMetricsIndexEntry | None:
    text = (content or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    sources = parsed.get("sources")
    if not isinstance(sources, list):
        return None
    for item in sources:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if isinstance(key, str) and key in allowlist:
            for entry in index:
                if entry.key == key:
                    return entry
    return None


def _merge_requirements(
    *groups: tuple[FactRequirement, ...],
) -> tuple[FactRequirement, ...]:
    merged: list[FactRequirement] = []
    seen: set[str] = set()
    for group in groups:
        for req in group:
            if req.fact_key in seen:
                continue
            seen.add(req.fact_key)
            merged.append(req)
    return tuple(merged)


def _log_plan(
    result: FactPlanResult,
    t0: float,
    *,
    index: tuple[KeyMetricsIndexEntry, ...] | None = None,
) -> None:
    dados: dict[str, Any] = {
        "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
        "composite": result.composite,
        "used_llm_fallback": result.used_llm_fallback,
        "used_llm_disambiguation": result.used_llm_disambiguation,
        "confidence": result.confidence,
        "requirement_kinds": [req.requirement_kind.value for req in result.requirements],
        "requirements": [req.as_mapping() for req in result.requirements],
        "fact_keys": [req.fact_key for req in result.requirements],
        "matched_keys": [req.matched_key for req in result.requirements],
        "match_methods": [req.match_method for req in result.requirements],
        "heuristic_statuses": [req.heuristic_status for req in result.requirements],
        "gaps": [gap.as_mapping() for gap in result.gaps],
    }
    if index is not None:
        dados["key_metrics_index"] = {
            "entry_count": len(index),
            "entries": [
                {
                    "key": entry.key,
                    "dimension": entry.dimension,
                    "metric_kind": entry.metric_kind,
                    "origin_id": entry.origin_id,
                    "context_key": entry.context_key,
                }
                for entry in index
            ],
        }
    log_public_chat_event(
        etapa="fact.plan",
        fase="post",
        dados=dados,
    )
