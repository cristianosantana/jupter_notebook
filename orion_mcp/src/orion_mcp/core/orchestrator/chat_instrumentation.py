"""
Instrumentação de turno (decisão, tool, data_cache, truncagens) para depuração.

- Com `ORION_ORCHESTRATOR_CHAT_TRACE=true`:
  - linhas JSON em log INFO (`orion_mcp.orchestration`) em eventos de turno;
  - ficheiros `trace_context_*_<session>.txt` em `ORION_LLM_DEBUG_LOG_DIR` com **system** + **user**
    (contexto exacto enviado ou que seria enviado ao LLM).
- Com `ORION_LLM_HALT_BEFORE_CHAT=true`: o mesmo snapshot entra em `extra` no ficheiro
  JSON gravado em `logs/` (sem depender do trace).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.state.models import State

_LOG = logging.getLogger("orion_mcp.orchestration")

_SEM_CACHE_MARKER = "(sem cache de dados)"


def snapshot_state_for_instrumentation(
    state: State,
    *,
    decision_action: str,
    tool_calls: int,
    llm_calls: int,
    user_input: str,
    elapsed_ms_since_turn_start: int,
) -> dict[str, Any]:
    """Estado relevante para perceber se a tool preencheu `data_cache` antes do LLM."""
    tp = state.entities.get("task_profile")
    tp_keys = list(tp.keys()) if isinstance(tp, dict) else []
    previews: list[dict[str, Any]] = []
    for k, entry in list(state.data_cache.items())[:40]:
        sm = entry.summary or ""
        previews.append(
            {
                "cache_key_suffix": k[-48:],
                "summary_len": len(sm),
                "summary_head": sm[:280].replace("\n", "⏎"),
            }
        )
    perf = state.flags.get("perf")
    perf_clean = dict(perf) if isinstance(perf, dict) else None
    return {
        "decision_action": decision_action,
        "intent": state.intent,
        "elapsed_ms_since_turn_start": elapsed_ms_since_turn_start,
        "metrics_tool_calls": tool_calls,
        "metrics_llm_calls": llm_calls,
        "data_cache_entry_count": len(state.data_cache),
        "data_cache_summaries": previews,
        "current_metric": state.current_metric,
        "flags_force_refresh": bool(state.flags.get("force_refresh")),
        "flags_domain_query_id": (str(state.flags.get("domain_query_id") or "").strip() or None),
        "flags_perf": perf_clean,
        "task_profile_keys": tp_keys,
        "user_input_head": (user_input or "")[:200],
    }


def snapshot_context_pipeline(
    *,
    phase: str,
    transport: str,
    context_truncated_from_builder: bool,
    cap_llm_truncated: bool,
    raw_context_char_len: int,
    final_user_prompt_char_len: int,
    raw_has_sem_cache_marker: bool,
    final_has_sem_cache_marker: bool,
) -> dict[str, Any]:
    """O que aconteceu ao texto entre `build_context` e o pedido ao modelo."""
    return {
        "phase": phase,
        "transport": transport,
        "context_truncated_from_builder": context_truncated_from_builder,
        "cap_llm_truncated": cap_llm_truncated,
        "raw_context_char_len": raw_context_char_len,
        "final_user_prompt_char_len": final_user_prompt_char_len,
        "raw_has_sem_cache_marker": raw_has_sem_cache_marker,
        "final_has_sem_cache_marker": final_has_sem_cache_marker,
    }


def sem_cache_marker_in(text: str) -> bool:
    return _SEM_CACHE_MARKER in (text or "")


def build_llm_halt_debug_extra(
    *,
    state: State,
    session_id: str,
    user_input: str,
    decision_action: str,
    metrics: dict[str, Any],
    budget_llm_calls: int,
    transport: str,
    halt_kind: str,
    ctx_res_text: str,
    ctx_text_final: str,
    context_truncated_from_builder: bool,
    cap_llm_truncated: bool,
    elapsed_ms_since_turn_start: int,
) -> dict[str, Any]:
    """Conteúdo do campo `extra` nos JSON de parada LLM."""
    return {
        "session_id": session_id,
        "halt_kind": halt_kind,
        "state_at_llm_gate": snapshot_state_for_instrumentation(
            state,
            decision_action=decision_action,
            tool_calls=int(metrics.get("tool_calls") or 0),
            llm_calls=budget_llm_calls,
            user_input=user_input,
            elapsed_ms_since_turn_start=elapsed_ms_since_turn_start,
        ),
        "context_pipeline": snapshot_context_pipeline(
            phase="halt_before_llm",
            transport=transport,
            context_truncated_from_builder=context_truncated_from_builder,
            cap_llm_truncated=cap_llm_truncated,
            raw_context_char_len=len(ctx_res_text),
            final_user_prompt_char_len=len(ctx_text_final),
            raw_has_sem_cache_marker=sem_cache_marker_in(ctx_res_text),
            final_has_sem_cache_marker=sem_cache_marker_in(ctx_text_final),
        ),
    }


def log_orchestration_event(
    settings: Settings,
    event: str,
    session_id: str,
    payload: dict[str, Any],
) -> None:
    if not settings.orchestrator_chat_trace:
        return
    line = json.dumps(
        {"event": event, "session_id": session_id, **payload},
        ensure_ascii=False,
    )
    _LOG.info("%s", line)


def write_trace_llm_context_file(
    settings: Settings,
    *,
    session_id: str,
    transport: str,
    kind: str,
    system_prompt: str | None,
    user_content: str,
) -> str | None:
    """
    Grava `system` + `user` (contexto completo) em texto sob `llm_debug_log_dir`.
    Só actua com `orchestrator_chat_trace=true`. Devolve caminho absoluto ou None.
    """
    if not settings.orchestrator_chat_trace:
        return None
    base = Path(settings.llm_debug_log_dir).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
    safe_sid = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)[:48]
    safe_kind = "".join(c if c.isalnum() or c in "-_" else "_" for c in kind)[:32]
    safe_tr = "".join(c if c.isalnum() or c in "-_" else "_" for c in transport)[:16]
    path = base / f"trace_context_{safe_kind}_{safe_tr}_{ts}_{safe_sid}.txt"
    sys_block = (system_prompt or "").strip() or "(none)"
    body = "\n".join(
        [
            f"session_id={session_id}",
            f"transport={transport}",
            f"kind={kind}",
            "",
            "=== system ===",
            sys_block,
            "",
            "=== user (contexto enviado ao LLM) ===",
            user_content,
        ]
    )
    path.write_text(body, encoding="utf-8")
    abspath = str(path.resolve())
    _LOG.info(
        "%s",
        json.dumps(
            {"event": "trace_context_file", "session_id": session_id, "path": abspath},
            ensure_ascii=False,
        ),
    )
    return abspath
