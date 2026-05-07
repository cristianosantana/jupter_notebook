"""Estado mínimo do composer (Fase 1.1 — sem persistência nem multiturn rico)."""

from __future__ import annotations

from dataclasses import dataclass, field

from orion_mcp_v3.contracts.context_block import ContextBlock
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy


@dataclass
class ContextState:
    """Fase lógica, política activa, tecto em tokens e blocos já materializados."""

    current_phase: str = "idle"
    active_policy: AttentionPolicy = AttentionPolicy.CONVERSATIONAL
    token_budget: int = 4096
    active_blocks: list[ContextBlock] = field(default_factory=list)
