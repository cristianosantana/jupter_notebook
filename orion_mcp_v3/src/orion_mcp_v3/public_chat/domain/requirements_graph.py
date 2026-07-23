"""Requirements Graph — nós (leaf requirements) + edges de composição."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from orion_mcp_v3.public_chat.domain.analytical_plan import AnalyticalGoal, AnalyticalPlan
from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.intent_contract import PublicOperationType


class CompositionEdgeKind(str, Enum):
    COMPARE_IDENTITY = "compare_identity"
    DELTA = "delta"
    RANK = "rank"
    SERIES = "series"
    SUM = "sum"
    SHARE = "share"


@dataclass(frozen=True, slots=True)
class CompositionEdge:
    kind: CompositionEdgeKind
    source_fact_keys: tuple[str, ...]
    target_key: str

    def as_mapping(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "source_fact_keys": list(self.source_fact_keys),
            "target_key": self.target_key,
        }


@dataclass(frozen=True, slots=True)
class RequirementsGraph:
    nodes: tuple[FactRequirement, ...]
    edges: tuple[CompositionEdge, ...]
    plan: AnalyticalPlan

    def as_mapping(self) -> dict[str, Any]:
        return {
            "plan": self.plan.as_mapping(),
            "nodes": [node.as_mapping() for node in self.nodes],
            "edges": [edge.as_mapping() for edge in self.edges],
        }


def build_requirements_graph(
    requirements: tuple[FactRequirement, ...],
    plan: AnalyticalPlan,
) -> RequirementsGraph:
    edges: list[CompositionEdge] = []
    if plan.goal == AnalyticalGoal.LEADER_COMPARISON and len(requirements) >= 2:
        keys = tuple(req.fact_key for req in requirements)
        matched = next((req.matched_key for req in requirements if req.matched_key), "index")
        periods = [req.period or "" for req in sorted(requirements, key=lambda r: r.period or "")]
        target = f"dynamic:{matched}@leader_change:{periods[0]}:{periods[-1]}"
        edges.append(
            CompositionEdge(
                kind=CompositionEdgeKind.COMPARE_IDENTITY,
                source_fact_keys=keys,
                target_key=target,
            )
        )
    elif plan.goal == AnalyticalGoal.PERIOD_DELTA and len(requirements) >= 2:
        keys = tuple(req.fact_key for req in requirements)
        matched = next((req.matched_key for req in requirements if req.matched_key), "index")
        periods = sorted(req.period or "" for req in requirements)
        target = f"dynamic:{matched}@growth:{periods[0]}:{periods[-1]}"
        edges.append(
            CompositionEdge(
                kind=CompositionEdgeKind.DELTA,
                source_fact_keys=keys,
                target_key=target,
            )
        )
    elif plan.goal == AnalyticalGoal.COMPARISON and len(requirements) >= 2:
        # Forma estrutural: PeriodDelta pode ser materializado no composer
        periods = sorted({req.period for req in requirements if req.period})
        if len(periods) >= 2:
            keys = tuple(req.fact_key for req in requirements)
            matched = next((req.matched_key for req in requirements if req.matched_key), "index")
            edges.append(
                CompositionEdge(
                    kind=CompositionEdgeKind.DELTA,
                    source_fact_keys=keys,
                    target_key=f"dynamic:{matched}@growth:{periods[0]}:{periods[-1]}",
                )
            )
    elif plan.goal == AnalyticalGoal.TIME_SERIES and requirements:
        keys = tuple(req.fact_key for req in requirements)
        matched = next((req.matched_key for req in requirements if req.matched_key), "index")
        edges.append(
            CompositionEdge(
                kind=CompositionEdgeKind.SERIES,
                source_fact_keys=keys,
                target_key=f"dynamic:{matched}@time_series",
            )
        )
    elif plan.goal == AnalyticalGoal.CUMULATIVE and requirements:
        keys = tuple(req.fact_key for req in requirements)
        matched = next((req.matched_key for req in requirements if req.matched_key), "index")
        edges.append(
            CompositionEdge(
                kind=CompositionEdgeKind.SUM,
                source_fact_keys=keys,
                target_key=f"dynamic:{matched}@cumulative",
            )
        )
    elif plan.goal == AnalyticalGoal.SHARE and requirements:
        keys = tuple(req.fact_key for req in requirements)
        matched = next((req.matched_key for req in requirements if req.matched_key), "index")
        edges.append(
            CompositionEdge(
                kind=CompositionEdgeKind.SHARE,
                source_fact_keys=keys,
                target_key=f"dynamic:{matched}@share",
            )
        )
    elif plan.goal == AnalyticalGoal.RANKING:
        for req in requirements:
            edges.append(
                CompositionEdge(
                    kind=CompositionEdgeKind.RANK,
                    source_fact_keys=(req.fact_key,),
                    target_key=req.fact_key,
                )
            )
    return RequirementsGraph(nodes=requirements, edges=tuple(edges), plan=plan)


def is_period_delta_operation(operation: str | None) -> bool:
    op = (operation or "").strip().lower()
    return op in {
        PublicOperationType.PERIOD_GROWTH.value,
        PublicOperationType.PERIOD_DECLINE.value,
        "period_growth",
        "period_decline",
    }


def is_leader_change_operation(operation: str | None) -> bool:
    return (operation or "").strip().lower() == PublicOperationType.LEADER_CHANGE.value
