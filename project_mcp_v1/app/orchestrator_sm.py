"""
Máquina de estados do turno (fases explícitas + tecto de passos).

O motor principal do pedido segue fases determinísticas; o LLM opera só
dentro dos handlers existentes (Maestro, especialista, pipelines).
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any
from uuid import UUID

from app.config import get_settings
from app.conversation_state import (
    load_conversation_state,
    save_conversation_state_to_metadata,
    update_state_from_input,
)
from app.orchestrator_analysis import analise
from app.orchestrator_decisions import decide_next_action, should_run_post_pipelines
from app.orchestrator_flow import ORCHESTRATOR_FLOW_FAST_SKELETON, resolve_orchestrator_flow_mode

_logger = logging.getLogger(__name__)

# Tecto de transições de fase por pedido HTTP (defesa contra regressões).
MAX_PHASE_TRANSITIONS_PER_TURN = 32


class TurnPhase(str, Enum):
    INIT = "init"
    PREPARE_AGENT = "prepare_agent"
    ENTITY_GLOSSARY = "entity_glossary"
    APPEND_USER = "append_user"
    MAESTRO_ROUTE = "maestro_route"
    SEMANTIC_INJECT = "semantic_inject"
    SPECIALIST_LOOP = "specialist_loop"
    CRITIQUE_REFINE = "critique_refine"
    FORMATADOR_UI = "formatador_ui"
    F3_PIPELINE = "f3_pipeline"
    DONE = "done"


def log_phase(phase: TurnPhase, **extra: Any) -> None:
    if extra:
        _logger.info("orch.sm from=%s extra=%s", phase.value, extra)
    else:
        _logger.info("orch.sm phase=%s", phase.value)


class TurnPhaseGuard:
    """Contador de fases para observabilidade e limite."""

    def __init__(self) -> None:
        self._n = 0
        self._last: TurnPhase | None = None

    def transition(self, to_phase: TurnPhase, **extra: Any) -> None:
        self._n += 1
        if self._n > MAX_PHASE_TRANSITIONS_PER_TURN:
            raise RuntimeError(
                f"orch.sm: excedido MAX_PHASE_TRANSITIONS_PER_TURN={MAX_PHASE_TRANSITIONS_PER_TURN}"
            )
        prev = self._last.value if self._last else None
        self._last = to_phase
        _logger.info(
            "orch.sm transition from=%s to=%s step=%s",
            prev,
            to_phase.value,
            self._n,
        )
        log_phase(to_phase, **extra)
        analise(
            "sm_transição",
            de=prev,
            para=to_phase.value,
            passo_sm=self._n,
            **{str(k): v for k, v in extra.items()},
        )


def _timing(orch: Any, name: str, t0: float) -> None:
    ms = (time.perf_counter() - t0) * 1000.0
    mark = getattr(orch, "_timing_mark", None)
    if callable(mark):
        mark(name, ms)
    analise("sm_subpasso_duração_ms", subpasso=name, ms=round(ms, 3))


async def run_fast_skeleton_turn(
    orch: Any,
    *,
    user_input: str,
    auto_route: bool,
    target_agent: Any,
    session_id: UUID | None,
    tools_used: list[dict[str, Any]],
    flow_mode: str,
) -> dict[str, Any]:
    """
    Variante ``fast_skeleton``: especialista em plano JSON + dispatch + síntese;
    sem critique, formatador, F3; maestro early return sem F3.
    """
    guard = TurnPhaseGuard()
    guard.transition(TurnPhase.INIT, agent=orch.current_agent, flow=flow_mode)

    guard.transition(TurnPhase.APPEND_USER)
    orch._append_message(
        {
            "role": "user",
            "content": user_input,
            "_orch_anchor": True,
        }
    )

    tools_payload = orch._tools_payload_for_specialist()
    step = 0

    if auto_route and orch.current_agent == "maestro":
        guard.transition(TurnPhase.MAESTRO_ROUTE)
        t_m = time.perf_counter()
        early, step = await orch._run_maestro_routing_phase(
            user_input, tools_used, step, session_id=session_id
        )
        _timing(orch, "maestro_route", t_m)
        if early is not None:
            if orch._trace_run_id:  # type: ignore[attr-defined]
                early["trace_run_id"] = orch._trace_run_id  # type: ignore[attr-defined]
            guard.transition(TurnPhase.DONE, branch="maestro_early_no_f3")
            return early

    guard.transition(TurnPhase.SEMANTIC_INJECT)
    t_s = time.perf_counter()
    await orch._inject_semantic_context_for_specialist(user_input)
    _timing(orch, "semantic_inject", t_s)

    guard.transition(TurnPhase.SPECIALIST_LOOP)
    t_sp = time.perf_counter()
    out, step = await orch._run_specialist_fast_skeleton(tools_payload, tools_used, step)
    _timing(orch, "specialist_fast_skeleton", t_sp)

    if orch._trace_run_id:  # type: ignore[attr-defined]
        out["trace_run_id"] = orch._trace_run_id  # type: ignore[attr-defined]

    st_dbg = get_settings()
    if st_dbg.semantic_context_debug_in_chat_response and orch._semantic_instrument_for_response:  # type: ignore[attr-defined]
        out["semantic_context_debug"] = dict(orch._semantic_instrument_for_response)  # type: ignore[attr-defined]

    analise(
        "sm_run_fast_skeleton_fim",
        fluxo=flow_mode,
        agente_final=out.get("agent"),
        tools_n=len(out.get("tools_used") or []),
    )
    guard.transition(TurnPhase.DONE)
    return out


async def run_linear_turn(
    orch: Any,
    *,
    user_input: str,
    auto_route: bool,
    target_agent: Any,
    session_id: UUID | None,
    tools_used: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Executa o pipeline do turno em fases explícitas (uma passagem linear).

    O loop interno LLM↔tools do especialista permanece em
    ``_run_specialist_loop``; as ferramentas MCP são obrigatoriamente deduplicadas
    via ``orchestrator_state`` / ``_call_mcp_tool_bounded``.
    """
    st = get_settings()
    flow_mode = resolve_orchestrator_flow_mode(st)
    meta = getattr(orch, "_session_metadata", None)
    conv_state = load_conversation_state(meta if isinstance(meta, dict) else None)
    update_state_from_input(conv_state, user_input)
    conv_state.last_turn_flow_mode = flow_mode
    save_conversation_state_to_metadata(meta if isinstance(meta, dict) else None, conv_state)

    analise(
        "sm_run_linear_turn_início",
        fluxo=flow_mode,
        agente=getattr(orch, "current_agent", None),
        complexidade=conv_state.complexity,
        target_agent=str(target_agent),
        session_id=str(session_id) if session_id else None,
        auto_route=auto_route,
        entrada_preview=(user_input or "")[:280],
    )

    if flow_mode == ORCHESTRATOR_FLOW_FAST_SKELETON:
        analise("sm_ramificação", destino="run_fast_skeleton_turn", fluxo=flow_mode)
        return await run_fast_skeleton_turn(
            orch,
            user_input=user_input,
            auto_route=auto_route,
            target_agent=target_agent,
            session_id=session_id,
            tools_used=tools_used,
            flow_mode=flow_mode,
        )

    guard = TurnPhaseGuard()
    guard.transition(TurnPhase.INIT, agent=orch.current_agent, flow=flow_mode)

    guard.transition(TurnPhase.APPEND_USER)
    orch._append_message(
        {
            "role": "user",
            "content": user_input,
            "_orch_anchor": True,
        }
    )

    tools_payload = orch._tools_payload_for_specialist()
    step = 0

    if auto_route and orch.current_agent == "maestro":
        guard.transition(TurnPhase.MAESTRO_ROUTE)
        t_m = time.perf_counter()
        early, step = await orch._run_maestro_routing_phase(
            user_input, tools_used, step, session_id=session_id
        )
        _timing(orch, "maestro_route", t_m)
        if early is not None:
            guard.transition(TurnPhase.F3_PIPELINE, branch="maestro_early")
            t_f3 = time.perf_counter()
            early = await orch._run_f3_pipeline(early, user_input)
            _timing(orch, "f3_pipeline_maestro_early", t_f3)
            if orch._trace_run_id:  # type: ignore[attr-defined]
                early["trace_run_id"] = orch._trace_run_id  # type: ignore[attr-defined]
            guard.transition(TurnPhase.DONE)
            return early

    guard.transition(TurnPhase.SEMANTIC_INJECT)
    t_sem = time.perf_counter()
    await orch._inject_semantic_context_for_specialist(user_input)
    _timing(orch, "semantic_inject", t_sem)

    guard.transition(TurnPhase.SPECIALIST_LOOP)
    t_sp = time.perf_counter()
    out, step = await orch._run_specialist_loop(tools_payload, tools_used, step)
    _timing(orch, "specialist_loop", t_sp)

    post_flags = should_run_post_pipelines(st, conv_state, flow_mode=flow_mode)
    decision = decide_next_action(st, conv_state, flow_mode=flow_mode)
    _logger.info("orch.sm decision=%s post_flags=%s", decision, post_flags)
    analise(
        "sm_pós_especialista_decisão",
        decisão=decision,
        post_flags=post_flags,
        agente=orch.current_agent,
        fluxo=flow_mode,
    )

    if orch.current_agent != "maestro":
        if post_flags["critique"]:
            guard.transition(TurnPhase.CRITIQUE_REFINE)
            t_cr = time.perf_counter()
            out, step = await orch._run_critique_refine_loop(out, user_input, tools_used, step)
            _timing(orch, "critique_refine", t_cr)
        if post_flags["formatador"]:
            guard.transition(TurnPhase.FORMATADOR_UI)
            t_fmt = time.perf_counter()
            out = await orch._run_formatador_ui(out, user_input)
            _timing(orch, "formatador_ui", t_fmt)

    if post_flags["f3"]:
        guard.transition(TurnPhase.F3_PIPELINE)
        t_f3 = time.perf_counter()
        out = await orch._run_f3_pipeline(out, user_input)
        _timing(orch, "f3_pipeline", t_f3)

    if orch._trace_run_id:  # type: ignore[attr-defined]
        out["trace_run_id"] = orch._trace_run_id  # type: ignore[attr-defined]

    st_dbg = get_settings()
    if st_dbg.semantic_context_debug_in_chat_response and orch._semantic_instrument_for_response:  # type: ignore[attr-defined]
        out["semantic_context_debug"] = dict(orch._semantic_instrument_for_response)  # type: ignore[attr-defined]

    analise(
        "sm_run_linear_turn_fim_legacy",
        fluxo=flow_mode,
        agente_final=out.get("agent"),
        tools_n=len(out.get("tools_used") or []),
    )
    guard.transition(TurnPhase.DONE)
    return out
