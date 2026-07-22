"""Pipeline workspace — plan → graph → resolve → cells → compose → RemissiveWorkspace."""

from __future__ import annotations

import time

from orion_mcp_v3.protocols.llm import LLMProvider
from orion_mcp_v3.public_chat.domain.analytical_plan import build_analytical_plan
from orion_mcp_v3.public_chat.domain.analytical_requirement_planner import plan_analytical_requirements
from orion_mcp_v3.public_chat.domain.composition_planner import NoOpCompositionPlanner
from orion_mcp_v3.public_chat.domain.fact_engine.models import RemissiveWorkspace
from orion_mcp_v3.public_chat.domain.fact_extractor import FactExtractor, PARTIAL_RANKING_CONFIDENCE
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.intent_heuristics import sanitize_ranking_entity_filters
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
from orion_mcp_v3.public_chat.domain.knowledge_composer import compose_knowledge
from orion_mcp_v3.public_chat.domain.knowledge_scoper import scope_knowledge_to_periods
from orion_mcp_v3.public_chat.domain.period_selection import periods_from_contract
from orion_mcp_v3.public_chat.domain.requirements_graph import build_requirements_graph
from orion_mcp_v3.public_chat.domain.special_requirements import NoOpSpecialCatalog
from orion_mcp_v3.public_chat.infrastructure.memory_resolver import MemoryResolver
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event

_RANKING_OPERATIONS = frozenset(
    {
        PublicOperationType.RANKING_ASC.value,
        PublicOperationType.RANKING_DESC.value,
        PublicOperationType.LEADER_CHANGE.value,
        PublicOperationType.PERIOD_GROWTH.value,
        PublicOperationType.PERIOD_DECLINE.value,
        PublicOperationType.TIME_SERIES.value,
        PublicOperationType.CUMULATIVE.value,
        "ranking_asc",
        "ranking_desc",
        "leader_change",
        "period_growth",
        "period_decline",
        "time_series",
        "cumulative",
        "min",
        "max",
    }
)


async def build_remissive_workspace(
    message: str,
    *,
    contract: IntentContract,
    knowledge: ConhecimentoRecuperado,
    planner: FactPlanner | None = None,
    resolver: MemoryResolver,
    extractor: FactExtractor | None = None,
    llm: LLMProvider | None = None,
) -> RemissiveWorkspace:
    t0 = time.monotonic()
    provider = llm
    if provider is None and planner is not None:
        provider = planner.provider
    contract = sanitize_ranking_entity_filters(contract)
    analytical_plan = build_analytical_plan(contract)
    contract_periods = periods_from_contract(contract)
    scoped_knowledge, scope_degraded = scope_knowledge_to_periods(
        knowledge,
        periods=contract_periods,
    )

    plan = await plan_analytical_requirements(
        message,
        contract=contract,
        knowledge=scoped_knowledge,
        llm=provider,
        special_catalog=NoOpSpecialCatalog(),
        composition_planner=NoOpCompositionPlanner(),
    )
    req_graph = build_requirements_graph(plan.requirements, analytical_plan)
    resolve_result = await resolver.resolve(plan.requirements, scoped_knowledge)
    extract_result = (extractor or FactExtractor()).extract(
        plan.requirements,
        resolve_result.resolved,
        semantics_version="v2",
    )
    composition = compose_knowledge(
        graph=req_graph,
        leaf_facts=extract_result.facts,
        resolved=resolve_result.resolved,
        semantics_version="v2",
    )

    all_gaps = tuple(
        dict.fromkeys((*plan.gaps, *resolve_result.gaps, *extract_result.gaps, *composition.gaps))
    )
    facts = composition.facts if composition.facts else extract_result.facts
    confidences = [fact.confidence for fact in facts]
    workspace_confidence = min(confidences) if confidences else 0.0
    ranking_base_rows = composition.ranking_base_rows or extract_result.ranking_base_rows
    source_truncated = composition.source_truncated or extract_result.source_truncated
    ranking_partial = _ranking_base_insufficient(
        contract,
        ranking_base_rows=ranking_base_rows,
        source_truncated=source_truncated,
        fact_count=len(facts),
    )
    if ranking_partial:
        workspace_confidence = min(workspace_confidence, PARTIAL_RANKING_CONFIDENCE)

    workspace = RemissiveWorkspace(
        period=resolve_result.join_plan.period if resolve_result.join_plan else contract.period,
        facts=facts,
        gaps=all_gaps,
        requirements=plan.requirements,
        join_plan=resolve_result.join_plan,
        workspace_confidence=workspace_confidence,
        analytical_plan=analytical_plan,
        computed=composition.computed,
        evidence=tuple(cell.as_mapping() for cell in composition.cells),
        narrative_instructions=composition.narrative_instructions,
        requirements_graph=req_graph.as_mapping(),
    )
    log_public_chat_event(
        etapa="workspace.build",
        fase="post",
        dados={
            "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
            "fact_count": len(workspace.facts),
            "gap_count": len(workspace.gaps),
            "workspace_confidence": workspace.workspace_confidence,
            "ranking_partial": ranking_partial,
            "ranking_base_rows": ranking_base_rows,
            "source_truncated": source_truncated,
            "used_llm_disambiguation": plan.used_llm_disambiguation,
            "scope_degraded": scope_degraded,
            "scope_periods": list(contract_periods),
            "hit_count_before_scope": len(knowledge.hits),
            "hit_count_after_scope": len(scoped_knowledge.hits),
            "analytical_goal": analytical_plan.goal.value,
            "computed_kinds": [item.get("kind") for item in workspace.computed if isinstance(item, dict)],
            "facts": [fact.as_mapping() for fact in workspace.facts],
            "gaps": [gap.as_mapping() for gap in workspace.gaps],
        },
    )
    return workspace


def _ranking_base_insufficient(
    contract: IntentContract,
    *,
    ranking_base_rows: int | None,
    source_truncated: bool,
    fact_count: int,
) -> bool:
    operation = (contract.operation or "").strip().lower()
    if operation not in _RANKING_OPERATIONS:
        return False
    if source_truncated:
        return True
    if ranking_base_rows is not None and ranking_base_rows <= 1:
        return True
    if fact_count == 1 and ranking_base_rows is None:
        return True
    return False


def build_fact_planner(provider: LLMProvider | None, *, max_tokens: int = 512) -> FactPlanner:
    return FactPlanner(provider, max_tokens=max_tokens)
