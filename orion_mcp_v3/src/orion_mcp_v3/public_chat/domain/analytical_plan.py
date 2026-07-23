"""AnalyticalPlan — intenção estruturada (não lista de facts)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.period_selection import periods_from_contract


class AnalyticalGoal(str, Enum):
    RANKING = "ranking"
    LEADER_COMPARISON = "leader_comparison"
    PERIOD_DELTA = "period_delta"
    TIME_SERIES = "time_series"
    CUMULATIVE = "cumulative"
    SHARE = "share"
    LOOKUP = "lookup"
    COMPARISON = "comparison"
    LIST = "list"
    SUMMARY = "summary"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AnalyticalPlan:
    goal: AnalyticalGoal
    operation: str | None
    dimension: str | None
    metric: str | None
    periods: tuple[str, ...]
    sort_direction: str | None
    confidence: float

    def as_mapping(self) -> dict[str, Any]:
        return {
            "goal": self.goal.value,
            "operation": self.operation,
            "dimension": self.dimension,
            "metric": self.metric,
            "periods": list(self.periods),
            "sort_direction": self.sort_direction,
            "confidence": round(self.confidence, 4),
        }


def build_analytical_plan(contract: IntentContract) -> AnalyticalPlan:
    operation = (contract.operation or "").strip().lower() or None
    periods = periods_from_contract(contract)
    if not periods and contract.period:
        periods = (contract.period,)
    goal = _goal_from_operation(operation)
    return AnalyticalPlan(
        goal=goal,
        operation=operation,
        dimension=contract.dimension,
        metric=contract.metric,
        periods=periods,
        sort_direction=contract.sort_direction,
        confidence=contract.confidence,
    )


def _goal_from_operation(operation: str | None) -> AnalyticalGoal:
    if operation == PublicOperationType.LEADER_CHANGE.value:
        return AnalyticalGoal.LEADER_COMPARISON
    if operation in (
        PublicOperationType.PERIOD_GROWTH.value,
        PublicOperationType.PERIOD_DECLINE.value,
    ):
        return AnalyticalGoal.PERIOD_DELTA
    if operation == PublicOperationType.TIME_SERIES.value:
        return AnalyticalGoal.TIME_SERIES
    if operation == PublicOperationType.CUMULATIVE.value:
        return AnalyticalGoal.CUMULATIVE
    if operation == PublicOperationType.SHARE.value:
        return AnalyticalGoal.SHARE
    if operation in (
        PublicOperationType.RANKING_ASC.value,
        PublicOperationType.RANKING_DESC.value,
        "min",
        "max",
    ):
        return AnalyticalGoal.RANKING
    if operation == PublicOperationType.COMPARISON.value:
        return AnalyticalGoal.COMPARISON
    if operation == PublicOperationType.LIST.value:
        return AnalyticalGoal.LIST
    if operation == PublicOperationType.SUMMARY.value:
        return AnalyticalGoal.SUMMARY
    if operation is None:
        return AnalyticalGoal.UNKNOWN
    return AnalyticalGoal.LOOKUP
