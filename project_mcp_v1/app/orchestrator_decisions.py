"""
Motor de decisão leve por turno (pipelines pós-especialista, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.conversation_state import ConversationStateV1

if TYPE_CHECKING:
    from app.config import Settings

PostPipelineMode = Literal["always", "heuristic"]

NextAction = Literal[
    "RUN_FULL_POST_PIPELINES",
    "SKIP_POST_PIPELINES",
]


def should_run_post_pipelines(
    settings: "Settings",
    state: ConversationStateV1,
    *,
    flow_mode: str,
) -> dict[str, bool]:
    """
    Devolve flags ``critique``, ``formatador``, ``f3``.

    ``fast_skeleton`` corta sempre os três. ``legacy`` + ``always`` mantém o comportamento
    actual (delegando depois às flags ``pipeline_*``). ``heuristic`` + ``low`` salta os três.
    """
    if flow_mode == "fast_skeleton":
        return {"critique": False, "formatador": False, "f3": False}
    mode = str(getattr(settings, "orchestrator_post_pipelines_mode", "always") or "always")
    if mode != "heuristic":
        return {"critique": True, "formatador": True, "f3": True}
    if state.complexity == "low":
        return {"critique": False, "formatador": False, "f3": False}
    return {"critique": True, "formatador": True, "f3": True}


def decide_next_action(
    settings: "Settings",
    state: ConversationStateV1,
    *,
    flow_mode: str,
) -> NextAction:
    """Ramificação principal pós-especialista (legacy); ``fast_skeleton`` resolve antes na SM."""
    flags = should_run_post_pipelines(settings, state, flow_mode=flow_mode)
    if not any(flags.values()):
        return "SKIP_POST_PIPELINES"
    return "RUN_FULL_POST_PIPELINES"
