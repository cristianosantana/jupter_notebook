"""
Modo de fluxo do orquestrador (A/B: legacy vs fast_skeleton).

- ``ORCHESTRATOR_FLOW_OVERRIDE``: forçar modo sem alterar ``.env`` (útil em testes).
- ``None`` → usa ``Settings.orchestrator_flow_mode`` (``ORCHESTRATOR_FLOW_MODE``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.config import Settings

FlowModeLiteral = Literal["legacy", "fast_skeleton"]

ORCHESTRATOR_FLOW_LEGACY: FlowModeLiteral = "legacy"
ORCHESTRATOR_FLOW_FAST_SKELETON: FlowModeLiteral = "fast_skeleton"

ORCHESTRATOR_FLOW_OVERRIDE: FlowModeLiteral | None = None


def resolve_orchestrator_flow_mode(settings: "Settings") -> FlowModeLiteral:
    if ORCHESTRATOR_FLOW_OVERRIDE in (
        ORCHESTRATOR_FLOW_LEGACY,
        ORCHESTRATOR_FLOW_FAST_SKELETON,
    ):
        return ORCHESTRATOR_FLOW_OVERRIDE
    v = str(getattr(settings, "orchestrator_flow_mode", "") or "").strip().lower()
    if v == ORCHESTRATOR_FLOW_FAST_SKELETON:
        return ORCHESTRATOR_FLOW_FAST_SKELETON
    return ORCHESTRATOR_FLOW_LEGACY
