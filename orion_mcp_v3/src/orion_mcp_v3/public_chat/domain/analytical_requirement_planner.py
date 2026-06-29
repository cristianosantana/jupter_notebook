"""Orquestrador único de requirements analíticos pós-retrieval."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider
from orion_mcp_v3.public_chat.domain.composition_planner import CompositionPlanner, NoOpCompositionPlanner
from orion_mcp_v3.public_chat.domain.fact_engine.gap import FactGap, GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.requirement_kind import RequirementKind
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.key_metrics_introspection import (
    HeuristicStatus,
    KeyMetricsIndexEntry,
    MatchMethod,
    available_key_metrics_payload,
    build_dynamic_requirement,
    build_key_metrics_index,
    dimensions_from_contract,
    find_key_metrics_source,
)
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
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

    primary_hit = knowledge.hits[0] if knowledge.hits else None
    if primary_hit is None or not primary_hit.key_metrics:
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

    index = build_key_metrics_index(primary_hit.key_metrics)
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

    entity = next((filt.value for filt in contract.entity_filters if filt.value), None)
    for dimension in dims:
        match = find_key_metrics_source(
            index,
            dimension=dimension,
            metric_kind=contract.metric,
            entity=entity,
            message=message,
        )
        if match.status == HeuristicStatus.RESOLVED and match.entry is not None:
            requirements.append(
                build_dynamic_requirement(
                    match.entry,
                    contract=contract,
                    match_method=match.match_method,
                )
            )
            continue

        if match.status == HeuristicStatus.AMBIGUOUS:
            resolved = await _llm_disambiguate_index(
                message,
                contract=contract,
                index=index,
                candidates=match.candidates,
                llm=llm,
                max_tokens=max_tokens,
            )
            if resolved is not None:
                used_llm = True
                requirements.append(
                    build_dynamic_requirement(
                        resolved,
                        contract=contract,
                        match_method=MatchMethod.LLM,
                        heuristic_status=HeuristicStatus.RESOLVED,
                    )
                )
                continue
            gaps.append(
                FactGap(
                    fact_key=f"dynamic:{dimension}",
                    reason=GapReason.KEY_METRICS_INDEX_AMBIGUOUS,
                    detail=f"candidates={[entry.key for entry in match.candidates]}",
                )
            )
            continue

        gaps.append(
            FactGap(
                fact_key=f"dynamic:{dimension}",
                reason=GapReason.NOT_FOUND,
                detail=f"dimension={dimension}",
            )
        )

    return tuple(requirements), gaps, used_llm


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
                }
                for entry in index
            ],
        }
    log_public_chat_event(
        etapa="fact.plan",
        fase="post",
        dados=dados,
    )
