"""
Trace estruturado (JSON Lines) para depuração do agente: LLM, MCP cliente/servidor, sampling.

Pastas ``YYYYMMDD/hora`` e o campo ``ts`` usam **hora local** (``TZ`` / fuso do sistema).

Ficheiros por pedido HTTP:

- ``{run_id}_app.jsonl`` — processo da API (orquestrador, ``OpenAIProvider``, cliente MCP, sampling).
- ``{run_id}_server.jsonl`` — processo MCP (servidor), mesmo ``run_id`` via meta.

Cada linha inclui ``run_id``. Com sessão PostgreSQL activa, todas as linhas da app incluem
``session_id`` (UUID em string ou ``null``).

Truncagem de strings grandes: controlada por ``agent_trace_max_field_chars`` / env
``AGENT_TRACE_MAX_FIELD_CHARS``. Valor **0 ou negativo** desactiva truncagem (análise completa;
atenção a disco e dados sensíveis).

Fases LLM no loop principal: definir com ``llm_phase_context("orchestrator:maestro")`` (etc.) antes
de ``model.chat``; ``OpenAIProvider`` inclui ``llm_phase`` e ``openai_call_index`` nos eventos
``llm.request`` / ``llm.response``. Chamadas laterais (memory, digest, observer, F3) devem usar a mesma convenção.

No fim de cada ``orchestrator.run`` com trace activo, grava-se ``openai.chat_completions.summary``
(com contagens por ``llm_phase``, duração total em ms e ``calls_initiated`` vs ``calls_completed``).
"""

from __future__ import annotations

import json
import asyncio
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app.config import get_settings

_trace_logger_ctx: ContextVar[AgentTraceLogger | None] = ContextVar(
    "agent_trace_logger", default=None
)

trace_llm_phase_ctx: ContextVar[str | None] = ContextVar(
    "trace_llm_phase", default=None
)


@dataclass
class OpenAiChatCompletionsStats:
    """
    Conta chamadas a ``chat.completions`` no processo da API durante um ``orchestrator.run``.

    Gravado no fim do run como evento ``openai.chat_completions.summary`` quando o trace está activo.
    """

    calls_initiated: int = 0
    calls_completed: int = 0
    calls_by_llm_phase: dict[str, int] = field(default_factory=dict)
    total_duration_ms: float = 0.0

    def begin_request(self) -> int:
        self.calls_initiated += 1
        return self.calls_initiated

    def complete_response(self, phase: str | None, elapsed_s: float) -> None:
        self.calls_completed += 1
        p = phase or "unknown"
        self.calls_by_llm_phase[p] = self.calls_by_llm_phase.get(p, 0) + 1
        self.total_duration_ms += elapsed_s * 1000.0

    def to_summary_fields(self) -> dict[str, Any]:
        return {
            "calls_completed": self.calls_completed,
            "calls_initiated": self.calls_initiated,
            "calls_by_llm_phase": dict(sorted(self.calls_by_llm_phase.items())),
            "total_duration_ms": round(self.total_duration_ms, 3),
        }


_openai_chat_stats_ctx: ContextVar[OpenAiChatCompletionsStats | None] = ContextVar(
    "openai_chat_completions_stats", default=None
)


def activate_openai_chat_stats_for_run() -> None:
    """Invocado no início de um run com trace; cada ``OpenAIProvider.chat`` completo incrementa contadores."""
    _openai_chat_stats_ctx.set(OpenAiChatCompletionsStats())


def get_openai_chat_stats() -> OpenAiChatCompletionsStats | None:
    return _openai_chat_stats_ctx.get()


def take_openai_chat_stats() -> OpenAiChatCompletionsStats | None:
    """Lê e limpa o acumulador (fim do run, antes de libertar o trace logger)."""
    s = _openai_chat_stats_ctx.get()
    _openai_chat_stats_ctx.set(None)
    return s


def get_trace_logger() -> AgentTraceLogger | None:
    return _trace_logger_ctx.get()


def set_trace_logger(logger: AgentTraceLogger | None) -> Any:
    return _trace_logger_ctx.set(logger)


def reset_trace_logger(token: Any) -> None:
    _trace_logger_ctx.reset(token)


def get_trace_llm_phase() -> str | None:
    return trace_llm_phase_ctx.get()


@contextmanager
def llm_phase_context(phase: str) -> Iterator[None]:
    """Define a fase LLM actual para os eventos ``llm.*`` do ``OpenAIProvider``."""
    tok = trace_llm_phase_ctx.set(phase)
    try:
        yield
    finally:
        trace_llm_phase_ctx.reset(tok)


class AgentTraceLogger:
    """
    Grava uma linha JSON por evento. API única: ``record(event, **campos)``.
    """

    _lock = threading.Lock()

    def __init__(
        self,
        *,
        run_id: str,
        app_log_path: Path,
        max_value_chars: int = 200_000,
        session_id: str | None = None,
    ) -> None:
        self.run_id = run_id
        self._session_id = session_id
        self._app_log_path = app_log_path
        self._max_value_chars = max_value_chars
        app_log_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def start_run(
        cls,
        trace_dir: Path,
        *,
        max_value_chars: int = 200_000,
        session_id: str | None = None,
    ) -> AgentTraceLogger:
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).astimezone()
        day = now.strftime("%Y%m%d")
        hour = str(now.hour)
        app_log_path = trace_dir / day / hour / f"{run_id}_app.jsonl"
        return cls(
            run_id=run_id,
            app_log_path=app_log_path,
            max_value_chars=max_value_chars,
            session_id=session_id,
        )

    def record(self, event: str, **fields: Any) -> None:
        """Grava um evento; todos os kwargs entram no JSON (truncagem conforme ``max_value_chars``)."""
        row: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).astimezone().isoformat(),
            "run_id": self.run_id,
            "session_id": self._session_id,
            "event": event,
        }
        for k, v in fields.items():
            row[k] = self._sanitize_value(v)
        line = json.dumps(row, ensure_ascii=False, default=_json_default)
        if get_settings().agent_trace_flush_async:

            def _write() -> None:
                with self._lock:
                    with self._app_log_path.open("a", encoding="utf-8") as f:
                        f.write(line + "\n")

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                loop.create_task(asyncio.to_thread(_write))
                return
        with self._lock:
            with self._app_log_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _sanitize_value(self, v: Any) -> Any:
        if v is None or isinstance(v, (bool, int, float)):
            return v
        if isinstance(v, str):
            return self._truncate_str(v)
        if isinstance(v, dict):
            out: dict[str, Any] = {}
            for k, val in v.items():
                out[str(k)] = self._sanitize_value(val)
            return out
        if isinstance(v, (list, tuple)):
            return [self._sanitize_value(x) for x in v]
        if hasattr(v, "model_dump"):
            try:
                return self._sanitize_value(v.model_dump(mode="json"))
            except Exception:
                return self._truncate_str(repr(v))
        return self._truncate_str(str(v))

    def _truncate_str(self, s: str) -> str:
        if self._max_value_chars <= 0:
            return s
        if len(s) <= self._max_value_chars:
            return s
        return (
            s[: self._max_value_chars]
            + f"\n… [truncado, {len(s)} chars → {self._max_value_chars}]"
        )


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump(mode="json")
        except Exception:
            return repr(obj)
    return repr(obj)
