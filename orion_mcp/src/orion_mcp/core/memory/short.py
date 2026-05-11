from __future__ import annotations

from orion_mcp.core.state.models import State


def update_short_memory(state: State, last_response: str) -> State:
    """Heurística determinística (sem LLM)."""
    s = state.model_copy(deep=True)
    text = (last_response or "").strip().replace("\n", " ")
    if len(text) > 400:
        text = text[:400] + "…"
    s.short_memory = text
    return s
