from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import asyncpg

from orion_mcp.core.budget import BudgetExceeded, RequestBudget
from orion_mcp.core.config.settings import Settings
from openai import APITimeoutError

from orion_mcp.core.context.context_builder import (
    apply_llm_context_max_chars,
    build_context,
    cap_llm_prompt,
)
from orion_mcp.core.decision.actions import Action
from orion_mcp.core.decision.decision_engine import DecisionContext, decide
from orion_mcp.core.formatter.formatter import FormatRequest, format_response
from orion_mcp.core.llm.embeddings import embed_text
from orion_mcp.core.llm.model_config import resolve_chat_model_id
from orion_mcp.core.llm.provider import (
    LLMProvider,
    build_llm,
    generate_insights_bundle,
    insights_bundle_user_prompt,
)
from orion_mcp.core.llm.request_dump import build_chat_completion_messages, write_llm_debug_json
from orion_mcp.core.memory.index_queue import maybe_enqueue_memory_index_after_chat
from orion_mcp.core.memory.long import retrieve_memory
from orion_mcp.core.memory.short import update_short_memory
from orion_mcp.core.orchestrator.action_executor import ActionExecutor
from orion_mcp.core.orchestrator.chat_instrumentation import (
    build_llm_halt_debug_extra,
    log_orchestration_event,
    snapshot_state_for_instrumentation,
    write_trace_llm_context_file,
)
from orion_mcp.core.orchestrator.context_suffixes import apply_chat_user_context_suffixes
from orion_mcp.core.orchestrator.state_manager import StateManager
from orion_mcp.core.state.turn_hints import ChatTurnHints
from orion_mcp.core.state.intent_heuristic import apply_task_heuristic_profile
from orion_mcp.core.state.models import State
from orion_mcp.core.state.transitions import update_state
from orion_mcp.core.strategy import Strategy

_logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    payload: dict[str, Any]
    metrics: dict[str, Any]


@dataclass
class _ChatTurnPrepared:
    session_id: str
    user_input: str
    strategy: Strategy
    state: State
    action: Action
    long_memo: str
    budget: RequestBudget
    metrics: dict[str, Any]
    t0: float


def _infer_format(user_input: str) -> Literal["html", "tabela", "lista"]:
    t = (user_input or "").strip().lower()
    if "html" in t:
        return "html"
    if "tabela" in t or t == "tabela":
        return "tabela"
    return "lista"


def _sse_event(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _merge_perf_into_state(state: State, **flags: bool) -> State:
    s = state.model_copy(deep=True)
    cur = s.flags.get("perf")
    base: dict[str, bool] = {}
    if isinstance(cur, dict):
        base.update({str(k): bool(v) for k, v in cur.items() if v})
    for k, v in flags.items():
        if v:
            base[str(k)] = True
    s.flags = {**s.flags, "perf": base}
    return s


def _attach_perf(payload: dict[str, Any], state: State) -> dict[str, Any]:
    perf = state.flags.get("perf")
    if isinstance(perf, dict):
        clean = {str(k): True for k, v in perf.items() if v}
        if clean:
            return {**payload, "perf": clean}
    return payload


def _chat_system_message(settings: Settings) -> str | None:
    t = (settings.llm_system_prompt or "").strip()
    return t or None


def _debug_halt_reply_body(log_path: str) -> str:
    return (
        "<p>Parada de depuração LLM (<code>ORION_LLM_HALT_BEFORE_CHAT=true</code>): "
        "o modelo não foi chamado. O pedido foi gravado em:<br/>"
        f"<code>{log_path}</code></p>"
    )


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        state_manager: StateManager,
        tools: ActionExecutor,
        llm: LLMProvider,
        pool: asyncpg.Pool | None,
    ):
        self._settings = settings
        self._state = state_manager
        self._tools = tools
        self._llm = llm
        self._pool = pool

    @classmethod
    def build(
        cls,
        settings: Settings,
        repo: Any,
        tool_registry: Any,
        pool: asyncpg.Pool | None,
    ) -> Orchestrator:
        return cls(
            settings,
            StateManager(repo),
            ActionExecutor(tool_registry),
            build_llm(settings),
            pool,
        )

    async def _prepare_turn(
        self,
        session_id: str,
        user_input: str,
        strategy: Strategy,
        hints: ChatTurnHints | None = None,
    ) -> _ChatTurnPrepared:
        t0 = time.perf_counter()
        budget = RequestBudget(self._settings)
        metrics: dict[str, Any] = {"llm_calls": 0, "tool_calls": 0, "tokens_used": None}

        state = await self._state.load_state(session_id)
        state = update_state(state, user_input, hints)
        state = apply_task_heuristic_profile(state, user_input)

        ctx = DecisionContext(
            llm_calls_used=budget.llm_calls,
            tool_calls_used=budget.tool_calls,
        )
        action = decide(state, user_input, strategy, ctx=ctx)

        if action == Action.CALL_TOOL:
            state = await self._tools.run_call_tool(state)
            budget.record_tool()
            metrics["tool_calls"] = budget.tool_calls
            ctx = DecisionContext(
                llm_calls_used=budget.llm_calls,
                tool_calls_used=budget.tool_calls,
            )
            action = decide(state, user_input, strategy, ctx=ctx)

        long_memo = ""
        if self._pool and self._settings.enable_long_memory:
            q_emb = await embed_text(self._settings, user_input)
            meta: dict[str, Any] = {}
            if state.current_metric:
                meta["metric"] = state.current_metric
            quoted = (state.entities or {}).get("quoted") if state.entities else None
            if isinstance(quoted, list) and quoted:
                meta["entity"] = str(quoted[0])
            chunks = await retrieve_memory(
                self._pool,
                session_id=session_id,
                query_embedding=q_emb,
                settings=self._settings,
                metadata_filters=meta,
                k=3,
            )
            long_memo = "\n".join(chunks)
            state = state.model_copy(deep=True)
            state.long_memory_refs = [c[:80] for c in chunks]

        elapsed_prepare_ms = int((time.perf_counter() - t0) * 1000)
        if self._settings.llm_halt_before_chat:
            log_orchestration_event(
                self._settings,
                "after_prepare_turn",
                session_id,
                snapshot_state_for_instrumentation(
                    state,
                    decision_action=action.value,
                    tool_calls=int(metrics["tool_calls"]),
                    llm_calls=int(metrics["llm_calls"]),
                    user_input=user_input,
                    elapsed_ms_since_turn_start=elapsed_prepare_ms,
                ),
            )

        return _ChatTurnPrepared(
            session_id=session_id,
            user_input=user_input,
            strategy=strategy,
            state=state,
            action=action,
            long_memo=long_memo,
            budget=budget,
            metrics=metrics,
            t0=t0,
        )

    async def handle_chat(
        self,
        *,
        session_id: str,
        user_input: str,
        strategy: Strategy = Strategy.fast,
        hints: ChatTurnHints | None = None,
    ) -> ChatResult:
        p = await self._prepare_turn(session_id, user_input, strategy, hints)
        state, action, long_memo, budget, metrics, t0 = (
            p.state,
            p.action,
            p.long_memo,
            p.budget,
            p.metrics,
            p.t0,
        )
        session_id = p.session_id
        user_input = p.user_input
        strategy = p.strategy

        if action == Action.FORMAT_RESPONSE:
            fmt = _infer_format(user_input)
            body_text = "\n".join(e.summary for e in state.data_cache.values()) or "(vazio)"
            out = format_response(FormatRequest(content=body_text, format=fmt))
            state = update_short_memory(state, body_text)
            await self._state.save_state(session_id, state)
            metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            metrics["llm_calls"] = budget.llm_calls
            return ChatResult(
                payload=_attach_perf({"kind": "formatted", **out}, state),
                metrics=metrics,
            )

        if action == Action.GENERATE_INSIGHTS:
            ctx_res = build_context(state, user_input, self._settings, long_memory=long_memo)
            state = _merge_perf_into_state(state, context_truncated=ctx_res.context_truncated)
            insights_prompt = insights_bundle_user_prompt(ctx_res.text)
            model_ins = resolve_chat_model_id(self._settings, strategy)
            write_trace_llm_context_file(
                self._settings,
                session_id=session_id,
                transport="chat",
                kind="insights_bundle",
                system_prompt=None,
                user_content=insights_prompt,
            )
            if self._settings.llm_halt_before_chat:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                halt_extra = build_llm_halt_debug_extra(
                    state=state,
                    session_id=session_id,
                    user_input=user_input,
                    decision_action=action.value,
                    metrics=metrics,
                    budget_llm_calls=budget.llm_calls,
                    transport="chat",
                    halt_kind="insights_bundle",
                    ctx_res_text=ctx_res.text,
                    ctx_text_final=insights_prompt,
                    context_truncated_from_builder=ctx_res.context_truncated,
                    cap_llm_truncated=False,
                    elapsed_ms_since_turn_start=elapsed_ms,
                )
                log_orchestration_event(
                    self._settings, "halt_before_llm", session_id, halt_extra
                )
                log_path = write_llm_debug_json(
                    self._settings.llm_debug_log_dir,
                    kind="insights_bundle",
                    transport="chat",
                    session_id=session_id,
                    halted=True,
                    openai_request={
                        "model": model_ins,
                        "temperature": 0.2,
                        "max_tokens": self._settings.llm_insights_max_tokens,
                        "stream": False,
                        "messages": [{"role": "user", "content": insights_prompt}],
                    },
                    extra=halt_extra,
                )
                state = _merge_perf_into_state(state, llm_debug_halt=True)
                reply_body = _debug_halt_reply_body(log_path)
                state = state.model_copy(deep=True)
                state.insights = []
                state = update_short_memory(state, reply_body)
                fmt = _infer_format(user_input)
                out = format_response(FormatRequest(content=reply_body, format=fmt))
                await self._state.save_state(session_id, state)
                metrics["llm_calls"] = budget.llm_calls
                metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                return ChatResult(
                    payload=_attach_perf(
                        {
                            "kind": "chat",
                            **out,
                            "insights": [],
                            "llm_debug_log_file": log_path,
                        },
                        state,
                    ),
                    metrics=metrics,
                )

            try:
                budget.record_llm()
            except BudgetExceeded:
                action = Action.GENERATE_RESPONSE
            else:
                try:
                    insights, reply = await generate_insights_bundle(
                        self._llm,
                        context=ctx_res.text,
                        settings=self._settings,
                        strategy=strategy,
                    )
                except APITimeoutError:
                    state = _merge_perf_into_state(state, llm_timeout=True)
                    insights, reply = [], "O serviço do modelo excedeu o tempo limite. Tenta de novo."
                state = state.model_copy(deep=True)
                state.insights = insights
                state = update_short_memory(state, reply)
                fmt = _infer_format(user_input)
                out = format_response(FormatRequest(content=reply, format=fmt))
                await self._state.save_state(session_id, state)
                metrics["llm_calls"] = budget.llm_calls
                metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                maybe_enqueue_memory_index_after_chat(
                    settings=self._settings,
                    pool=self._pool,
                    session_id=session_id,
                    state=state,
                    user_input=user_input,
                    assistant_text=reply,
                )
                return ChatResult(
                    payload=_attach_perf({"kind": "chat", **out, "insights": insights}, state),
                    metrics=metrics,
                )

        # Action.GENERATE_RESPONSE
        ctx_res = build_context(state, user_input, self._settings, long_memory=long_memo)
        ctx_text = apply_chat_user_context_suffixes(
            ctx_res.text, state, settings=self._settings
        )
        ctx_text, cap_trunc = cap_llm_prompt(ctx_text, self._settings)
        system_prompt = _chat_system_message(self._settings)
        system_prompt, ctx_text, char_trunc = apply_llm_context_max_chars(
            system_prompt, ctx_text, self._settings
        )
        state = _merge_perf_into_state(
            state,
            context_truncated=ctx_res.context_truncated or cap_trunc or char_trunc,
        )

        model = resolve_chat_model_id(self._settings, strategy)
        temperature = 0.2
        max_tokens = self._settings.llm_completion_max_tokens
        write_trace_llm_context_file(
            self._settings,
            session_id=session_id,
            transport="chat",
            kind="chat_completion",
            system_prompt=system_prompt,
            user_content=ctx_text,
        )

        if self._settings.llm_halt_before_chat:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            halt_extra = build_llm_halt_debug_extra(
                state=state,
                session_id=session_id,
                user_input=user_input,
                decision_action=action.value,
                metrics=metrics,
                budget_llm_calls=budget.llm_calls,
                transport="chat",
                halt_kind="chat_completion",
                ctx_res_text=ctx_res.text,
                ctx_text_final=ctx_text,
                context_truncated_from_builder=ctx_res.context_truncated,
                cap_llm_truncated=cap_trunc or char_trunc,
                elapsed_ms_since_turn_start=elapsed_ms,
            )
            log_orchestration_event(
                self._settings, "halt_before_llm", session_id, halt_extra
            )
            log_path = write_llm_debug_json(
                self._settings.llm_debug_log_dir,
                kind="chat_completion",
                transport="chat",
                session_id=session_id,
                halted=True,
                openai_request={
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                    "messages": build_chat_completion_messages(
                        system_prompt=system_prompt,
                        user_text=ctx_text,
                    ),
                },
                extra=halt_extra,
            )
            state = _merge_perf_into_state(state, llm_debug_halt=True)
            reply_body = _debug_halt_reply_body(log_path)
            state = update_short_memory(state, reply_body)
            fmt = _infer_format(user_input)
            out = format_response(FormatRequest(content=reply_body, format=fmt))
            await self._state.save_state(session_id, state)
            metrics["llm_calls"] = budget.llm_calls
            metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            return ChatResult(
                payload=_attach_perf(
                    {"kind": "chat", **out, "llm_debug_log_file": log_path},
                    state,
                ),
                metrics=metrics,
            )

        try:
            budget.record_llm()
        except BudgetExceeded:
            partial = "Limite de chamadas LLM atingido para este pedido."
            state = _merge_perf_into_state(state, llm_budget_exhausted=True)
            state = update_short_memory(state, partial)
            await self._state.save_state(session_id, state)
            metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            metrics["llm_calls"] = budget.llm_calls
            return ChatResult(
                payload=_attach_perf(
                    {"kind": "chat", "format": "lista", "body": f"<p>{partial}</p>"},
                    state,
                ),
                metrics=metrics,
            )

        reply_parts: list[str] = []
        try:
            async for delta in self._llm.generate_stream(
                ctx_text,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
            ):
                reply_parts.append(delta)
        except APITimeoutError:
            state = _merge_perf_into_state(state, llm_timeout=True)
            reply_parts = [
                "O serviço do modelo excedeu o tempo limite. Tenta de novo.",
            ]
        reply = "".join(reply_parts)
        metrics["llm_calls"] = budget.llm_calls
        state = update_short_memory(state, reply)
        fmt = _infer_format(user_input)
        out = format_response(FormatRequest(content=reply, format=fmt))
        await self._state.save_state(session_id, state)
        metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        maybe_enqueue_memory_index_after_chat(
            settings=self._settings,
            pool=self._pool,
            session_id=session_id,
            state=state,
            user_input=user_input,
            assistant_text=reply,
        )
        return ChatResult(payload=_attach_perf({"kind": "chat", **out}, state), metrics=metrics)

    async def handle_chat_stream(
        self,
        *,
        session_id: str,
        user_input: str,
        strategy: Strategy = Strategy.fast,
        hints: ChatTurnHints | None = None,
    ) -> AsyncIterator[str]:
        """
        SSE: eventos JSON por linha `data: ...`.
        - `{"type":"token","delta":"..."}` por delta do LLM (só em GENERATE_RESPONSE).
        - `{"type":"done","session_id","payload","metrics"}` no fim do turno.
        """
        p = await self._prepare_turn(session_id, user_input, strategy, hints)
        state, action, long_memo, budget, metrics, t0 = (
            p.state,
            p.action,
            p.long_memo,
            p.budget,
            p.metrics,
            p.t0,
        )
        session_id = p.session_id
        user_input = p.user_input
        strategy = p.strategy

        if action == Action.FORMAT_RESPONSE:
            fmt = _infer_format(user_input)
            body_text = "\n".join(e.summary for e in state.data_cache.values()) or "(vazio)"
            out = format_response(FormatRequest(content=body_text, format=fmt))
            state = update_short_memory(state, body_text)
            await self._state.save_state(session_id, state)
            metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            metrics["llm_calls"] = budget.llm_calls
            yield _sse_event(
                {
                    "type": "done",
                    "session_id": session_id,
                    "payload": _attach_perf({"kind": "formatted", **out}, state),
                    "metrics": metrics,
                }
            )
            return

        if action == Action.GENERATE_INSIGHTS:
            ctx_res = build_context(state, user_input, self._settings, long_memory=long_memo)
            state = _merge_perf_into_state(state, context_truncated=ctx_res.context_truncated)
            insights_prompt = insights_bundle_user_prompt(ctx_res.text)
            model_ins = resolve_chat_model_id(self._settings, strategy)
            write_trace_llm_context_file(
                self._settings,
                session_id=session_id,
                transport="chat_stream",
                kind="insights_bundle",
                system_prompt=None,
                user_content=insights_prompt,
            )
            if self._settings.llm_halt_before_chat:
                elapsed_ms = int((time.perf_counter() - t0) * 1000)
                halt_extra = build_llm_halt_debug_extra(
                    state=state,
                    session_id=session_id,
                    user_input=user_input,
                    decision_action=action.value,
                    metrics=metrics,
                    budget_llm_calls=budget.llm_calls,
                    transport="chat_stream",
                    halt_kind="insights_bundle",
                    ctx_res_text=ctx_res.text,
                    ctx_text_final=insights_prompt,
                    context_truncated_from_builder=ctx_res.context_truncated,
                    cap_llm_truncated=False,
                    elapsed_ms_since_turn_start=elapsed_ms,
                )
                log_orchestration_event(
                    self._settings, "halt_before_llm", session_id, halt_extra
                )
                log_path = write_llm_debug_json(
                    self._settings.llm_debug_log_dir,
                    kind="insights_bundle",
                    transport="chat_stream",
                    session_id=session_id,
                    halted=True,
                    openai_request={
                        "model": model_ins,
                        "temperature": 0.2,
                        "max_tokens": self._settings.llm_insights_max_tokens,
                        "stream": False,
                        "messages": [{"role": "user", "content": insights_prompt}],
                    },
                    extra=halt_extra,
                )
                state = _merge_perf_into_state(state, llm_debug_halt=True)
                reply_body = _debug_halt_reply_body(log_path)
                state = state.model_copy(deep=True)
                state.insights = []
                state = update_short_memory(state, reply_body)
                fmt = _infer_format(user_input)
                out = format_response(FormatRequest(content=reply_body, format=fmt))
                await self._state.save_state(session_id, state)
                metrics["llm_calls"] = budget.llm_calls
                metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                yield _sse_event(
                    {
                        "type": "done",
                        "session_id": session_id,
                        "payload": _attach_perf(
                            {
                                "kind": "chat",
                                **out,
                                "insights": [],
                                "llm_debug_log_file": log_path,
                            },
                            state,
                        ),
                        "metrics": metrics,
                    }
                )
                return

            try:
                budget.record_llm()
            except BudgetExceeded:
                action = Action.GENERATE_RESPONSE
            else:
                try:
                    insights, reply = await generate_insights_bundle(
                        self._llm,
                        context=ctx_res.text,
                        settings=self._settings,
                        strategy=strategy,
                    )
                except APITimeoutError:
                    state = _merge_perf_into_state(state, llm_timeout=True)
                    insights, reply = [], "O serviço do modelo excedeu o tempo limite. Tenta de novo."
                state = state.model_copy(deep=True)
                state.insights = insights
                state = update_short_memory(state, reply)
                fmt = _infer_format(user_input)
                out = format_response(FormatRequest(content=reply, format=fmt))
                await self._state.save_state(session_id, state)
                metrics["llm_calls"] = budget.llm_calls
                metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                maybe_enqueue_memory_index_after_chat(
                    settings=self._settings,
                    pool=self._pool,
                    session_id=session_id,
                    state=state,
                    user_input=user_input,
                    assistant_text=reply,
                )
                yield _sse_event(
                    {
                        "type": "done",
                        "session_id": session_id,
                        "payload": _attach_perf({"kind": "chat", **out, "insights": insights}, state),
                        "metrics": metrics,
                    }
                )
                return

        # Action.GENERATE_RESPONSE
        ctx_res = build_context(state, user_input, self._settings, long_memory=long_memo)
        ctx_text = apply_chat_user_context_suffixes(
            ctx_res.text, state, settings=self._settings
        )
        ctx_text, cap_trunc = cap_llm_prompt(ctx_text, self._settings)
        system_prompt = _chat_system_message(self._settings)
        system_prompt, ctx_text, char_trunc = apply_llm_context_max_chars(
            system_prompt, ctx_text, self._settings
        )
        state = _merge_perf_into_state(
            state,
            context_truncated=ctx_res.context_truncated or cap_trunc or char_trunc,
        )

        model = resolve_chat_model_id(self._settings, strategy)
        temperature = 0.2
        max_tokens = self._settings.llm_completion_max_tokens
        write_trace_llm_context_file(
            self._settings,
            session_id=session_id,
            transport="chat_stream",
            kind="chat_completion",
            system_prompt=system_prompt,
            user_content=ctx_text,
        )

        if self._settings.llm_halt_before_chat:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            halt_extra = build_llm_halt_debug_extra(
                state=state,
                session_id=session_id,
                user_input=user_input,
                decision_action=action.value,
                metrics=metrics,
                budget_llm_calls=budget.llm_calls,
                transport="chat_stream",
                halt_kind="chat_completion",
                ctx_res_text=ctx_res.text,
                ctx_text_final=ctx_text,
                context_truncated_from_builder=ctx_res.context_truncated,
                cap_llm_truncated=cap_trunc or char_trunc,
                elapsed_ms_since_turn_start=elapsed_ms,
            )
            log_orchestration_event(
                self._settings, "halt_before_llm", session_id, halt_extra
            )
            log_path = write_llm_debug_json(
                self._settings.llm_debug_log_dir,
                kind="chat_completion",
                transport="chat_stream",
                session_id=session_id,
                halted=True,
                openai_request={
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": True,
                    "messages": build_chat_completion_messages(
                        system_prompt=system_prompt,
                        user_text=ctx_text,
                    ),
                },
                extra=halt_extra,
            )
            state = _merge_perf_into_state(state, llm_debug_halt=True)
            reply_body = _debug_halt_reply_body(log_path)
            state = update_short_memory(state, reply_body)
            fmt = _infer_format(user_input)
            out = format_response(FormatRequest(content=reply_body, format=fmt))
            await self._state.save_state(session_id, state)
            metrics["llm_calls"] = budget.llm_calls
            metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            yield _sse_event(
                {
                    "type": "done",
                    "session_id": session_id,
                    "payload": _attach_perf(
                        {"kind": "chat", **out, "llm_debug_log_file": log_path},
                        state,
                    ),
                    "metrics": metrics,
                }
            )
            return

        try:
            budget.record_llm()
        except BudgetExceeded:
            partial = "Limite de chamadas LLM atingido para este pedido."
            state = _merge_perf_into_state(state, llm_budget_exhausted=True)
            state = update_short_memory(state, partial)
            await self._state.save_state(session_id, state)
            metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            metrics["llm_calls"] = budget.llm_calls
            yield _sse_event(
                {
                    "type": "done",
                    "session_id": session_id,
                    "payload": _attach_perf(
                        {"kind": "chat", "format": "lista", "body": f"<p>{partial}</p>"},
                        state,
                    ),
                    "metrics": metrics,
                }
            )
            return

        reply_parts: list[str] = []
        try:
            async for delta in self._llm.generate_stream(
                ctx_text,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                system_prompt=system_prompt,
            ):
                reply_parts.append(delta)
                yield _sse_event({"type": "token", "delta": delta})
        except APITimeoutError:
            state = _merge_perf_into_state(state, llm_timeout=True)
            reply_parts = ["O serviço do modelo excedeu o tempo limite. Tenta de novo."]
        reply = "".join(reply_parts)
        metrics["llm_calls"] = budget.llm_calls
        state = update_short_memory(state, reply)
        fmt = _infer_format(user_input)
        out = format_response(FormatRequest(content=reply, format=fmt))
        await self._state.save_state(session_id, state)
        metrics["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        maybe_enqueue_memory_index_after_chat(
            settings=self._settings,
            pool=self._pool,
            session_id=session_id,
            state=state,
            user_input=user_input,
            assistant_text=reply,
        )
        yield _sse_event(
            {
                "type": "done",
                "session_id": session_id,
                "payload": _attach_perf({"kind": "chat", **out}, state),
                "metrics": metrics,
            }
        )
