"""Planner de composition cross-theme."""

from __future__ import annotations

from typing import Protocol

from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.fact_engine.requirement_kind import RequirementKind
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado


class CompositionPlanner(Protocol):
    def build(
        self,
        message: str,
        *,
        contract: IntentContract,
        knowledge: ConhecimentoRecuperado,
        lookup_requirements: tuple[FactRequirement, ...],
    ) -> tuple[FactRequirement, ...]: ...


class NoOpCompositionPlanner:
    def build(
        self,
        message: str,
        *,
        contract: IntentContract,
        knowledge: ConhecimentoRecuperado,
        lookup_requirements: tuple[FactRequirement, ...],
    ) -> tuple[FactRequirement, ...]:
        _ = (message, contract, knowledge, lookup_requirements)
        return ()


def is_same_hit_composite(lookup_requirements: tuple[FactRequirement, ...]) -> bool:
    return len(lookup_requirements) >= 2 and all(
        req.requirement_kind == RequirementKind.LOOKUP for req in lookup_requirements
    )
