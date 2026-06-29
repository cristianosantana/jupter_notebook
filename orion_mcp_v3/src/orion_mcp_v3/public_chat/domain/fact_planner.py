"""Fact Planner — delega ao RequirementPlanner analítico."""

from __future__ import annotations

from orion_mcp_v3.protocols.llm import LLMProvider
from orion_mcp_v3.public_chat.domain.analytical_requirement_planner import FactPlanResult, plan_analytical_requirements
from orion_mcp_v3.public_chat.domain.composition_planner import CompositionPlanner, NoOpCompositionPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
from orion_mcp_v3.public_chat.domain.special_requirements import NoOpSpecialCatalog, SpecialRequirementsCatalog


class FactPlanner:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        *,
        catalog=None,
        max_tokens: int = 512,
        special_catalog: SpecialRequirementsCatalog | None = None,
        composition_planner: CompositionPlanner | None = None,
    ) -> None:
        self._provider = provider
        self._max_tokens = max_tokens
        self._special_catalog = special_catalog or NoOpSpecialCatalog()
        self._composition_planner = composition_planner or NoOpCompositionPlanner()
        _ = catalog

    @property
    def provider(self) -> LLMProvider | None:
        return self._provider

    async def plan(
        self,
        message: str,
        *,
        contract: IntentContract,
        knowledge: ConhecimentoRecuperado | None = None,
    ) -> FactPlanResult:
        if knowledge is None:
            return FactPlanResult(
                requirements=(),
                composite=False,
                used_llm_fallback=False,
                used_llm_disambiguation=False,
                confidence=contract.confidence,
            )
        return await plan_analytical_requirements(
            message,
            contract=contract,
            knowledge=knowledge,
            llm=self._provider,
            special_catalog=self._special_catalog,
            composition_planner=self._composition_planner,
            max_tokens=self._max_tokens,
        )
