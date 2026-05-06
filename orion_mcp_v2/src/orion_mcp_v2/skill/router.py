"""Roteamento intent → skill_id (espelha o DecisionEngine)."""

from __future__ import annotations

from orion_mcp_v2.core.decision.engine import BusinessIntent, _skill_for_intent


def skill_for_intent(intent: BusinessIntent) -> str:
    return _skill_for_intent(intent)
