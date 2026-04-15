"""
Tecto global de chamadas ``model.chat`` por pedido HTTP (orquestrador).

Usado por ``OpenAIProvider.chat``; o contador é reposto no início/fim de ``ModularOrchestrator.run``.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_cap: ContextVar[int] = ContextVar("orch_llm_cap", default=0)
_used: ContextVar[int] = ContextVar("orch_llm_used", default=0)
_cap_hit: ContextVar[bool] = ContextVar("orch_llm_cap_hit", default=False)


def llm_budget_begin_run(cap: int) -> None:
    c = max(0, int(cap or 0))
    _cap.set(c)
    _used.set(0)
    _cap_hit.set(False)


def llm_budget_end_run() -> None:
    _cap.set(0)
    _used.set(0)
    _cap_hit.set(False)


def llm_budget_try_consume() -> bool:
    """
    Antes de cada chamada à API de chat: devolve False se o tecto já foi atingido
    (não incrementa). Caso contrário incrementa o contador e devolve True.
    """
    cap = _cap.get()
    if cap <= 0:
        return True
    u = _used.get()
    if u >= cap:
        _cap_hit.set(True)
        return False
    _used.set(u + 1)
    return True


def was_llm_cap_hit() -> bool:
    return bool(_cap_hit.get())


def degraded_llm_assistant_message() -> dict[str, Any]:
    """Resposta sintética quando não há orçamento para outra chamada ao modelo."""
    return {
        "role": "assistant",
        "content": (
            "Limite de chamadas ao modelo para este pedido foi atingido "
            "(``ORCHESTRATOR_MAX_LLM_CALLS_PER_REQUEST``). "
            "Aumenta o valor na configuração ou simplifica a pergunta."
        ),
    }
