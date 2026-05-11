from __future__ import annotations

from dataclasses import dataclass

from orion_mcp.core.decision.actions import Action
from orion_mcp.core.state.models import State
from orion_mcp.core.strategy import Strategy


@dataclass(frozen=True)
class DecisionContext:
    llm_calls_used: int = 0
    tool_calls_used: int = 0


def decide(
    state: State,
    user_input: str,
    strategy: Strategy,
    *,
    ctx: DecisionContext | None = None,
) -> Action:
    """
    Pure deterministic routing. `strategy` only affects downstream model choice, not this function.
    """
    _ = strategy
    ctx = ctx or DecisionContext()

    if state.intent == "format_only" and state.data_cache:
        return Action.FORMAT_RESPONSE

    if state.flags.get("force_refresh"):
        return Action.CALL_TOOL

    if not state.data_cache:
        if ctx.tool_calls_used >= 1:
            return Action.GENERATE_RESPONSE
        return Action.CALL_TOOL

    if state.intent == "why_question" and state.data_cache:
        # Após tool no mesmo request, não usar segundo passo só de insights (evita >2 LLMs).
        if ctx.tool_calls_used > 0:
            return Action.GENERATE_RESPONSE
        return Action.GENERATE_INSIGHTS

    return Action.GENERATE_RESPONSE
