"""Catálogo residual de requirements especiais (derived)."""

from __future__ import annotations

from typing import Protocol

from orion_mcp_v3.public_chat.domain.fact_engine.models import FactRequirement
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado


class SpecialRequirementsCatalog(Protocol):
    def build(
        self,
        message: str,
        *,
        contract: IntentContract,
        knowledge: ConhecimentoRecuperado,
        lookup_requirements: tuple[FactRequirement, ...],
    ) -> tuple[FactRequirement, ...]: ...


class NoOpSpecialCatalog:
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
