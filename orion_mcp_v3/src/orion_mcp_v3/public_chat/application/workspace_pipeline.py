"""Pipeline workspace — planner → resolver → extractor → RemissiveWorkspace."""

from __future__ import annotations

import time

from orion_mcp_v3.protocols.llm import LLMProvider
from orion_mcp_v3.public_chat.domain.fact_engine.models import RemissiveWorkspace
from orion_mcp_v3.public_chat.domain.fact_extractor import FactExtractor
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
from orion_mcp_v3.public_chat.infrastructure.memory_resolver import MemoryResolver
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event


async def build_remissive_workspace(
    message: str,
    *,
    contract: IntentContract,
    knowledge: ConhecimentoRecuperado,
    planner: FactPlanner,
    resolver: MemoryResolver,
    extractor: FactExtractor | None = None,
) -> RemissiveWorkspace:
    t0 = time.monotonic()
    plan = await planner.plan(message, contract=contract)
    resolve_result = await resolver.resolve(plan.requirements, knowledge)
    extract_result = (extractor or FactExtractor()).extract(
        plan.requirements,
        resolve_result.resolved,
        semantics_version="v1",
    )

    all_gaps = tuple(dict.fromkeys((*resolve_result.gaps, *extract_result.gaps)))
    confidences = [fact.confidence for fact in extract_result.facts]
    workspace_confidence = min(confidences) if confidences else 0.0

    workspace = RemissiveWorkspace(
        period=resolve_result.join_plan.period if resolve_result.join_plan else contract.period,
        facts=extract_result.facts,
        gaps=all_gaps,
        requirements=plan.requirements,
        join_plan=resolve_result.join_plan,
        workspace_confidence=workspace_confidence,
    )
    log_public_chat_event(
        etapa="workspace.build",
        fase="post",
        dados={
            "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
            "fact_count": len(workspace.facts),
            "gap_count": len(workspace.gaps),
            "workspace_confidence": workspace.workspace_confidence,
            "facts": [fact.as_mapping() for fact in workspace.facts],
            "gaps": [gap.as_mapping() for gap in workspace.gaps],
        },
    )
    return workspace


def build_fact_planner(provider: LLMProvider | None, *, max_tokens: int = 512) -> FactPlanner:
    return FactPlanner(provider, max_tokens=max_tokens)
