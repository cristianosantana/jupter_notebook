"""
Perfil de tarefa determinístico (sem LLM) alinhado a docs/heurística_de_tomada_de_decisão.md:
ação ótima (simplicidade, pragmatismo, iteração), postura de risco e limites operacionais.
"""

from __future__ import annotations

import json
from typing import Any

from orion_mcp.core.state.models import State

_ANALYTICS_KW = (
    "quantos",
    "quanto",
    "total",
    "top",
    "lista",
    "listagem",
    "resumo",
    "média",
    "media",
    "soma",
    "ranking",
    "gráfico",
    "grafico",
    "tabela",
    "dados",
    "métrica",
    "metrica",
)


def _lower(s: str) -> str:
    return (s or "").strip().lower()


def _has_analytics_keywords(text: str) -> bool:
    t = _lower(text)
    return any(k in t for k in _ANALYTICS_KW)


def _data_status(state: State) -> str:
    if not state.data_cache:
        return "no_data"
    perf = state.flags.get("perf")
    if isinstance(perf, dict) and perf.get("mcp_unavailable"):
        return "degraded"
    for entry in state.data_cache.values():
        s = entry.summary or ""
        if "mcp_degraded" in s or "MCP indisponível" in s or "[MCP indisponível" in s:
            return "degraded"
    return "has_cache"


def _risk_posture(state: State, user_input: str) -> str:
    if state.intent == "why_question":
        return "conservador"
    st = _data_status(state)
    if st == "degraded":
        return "conservador"
    if st == "no_data" and (
        bool(state.flags.get("domain_query_id"))
        or _has_analytics_keywords(user_input)
    ):
        return "conservador"
    return "normal"


def _style_hint(state: State) -> str:
    if state.intent == "format_only":
        return "Formatar a saída conforme o pedido do utilizador (tabela/html/lista)."
    if state.intent == "why_question":
        return "Explicar causas possíveis com cautela, só com base nos dados resumidos."
    if state.intent == "refresh_data":
        return "Dados foram pedidos para atualização; síntese clara do que mudou ou do estado actual."
    return "Resposta directa e útil; priorizar clareza."


def _compute_task_profile(state: State, user_input: str) -> dict[str, Any]:
    data_status = _data_status(state)
    risk = _risk_posture(state, user_input)
    t = _lower(user_input)
    pragmatic = _has_analytics_keywords(user_input) or "resumo" in t or "em poucas palavras" in t
    catalog = bool(str(state.flags.get("domain_query_id") or "").strip())

    iteration_hint = (
        "O turno pode ainda ir buscar dados via tool; não inventar números antes de existirem em "
        "'Dados resumidos'."
        if data_status == "no_data" and (catalog or _has_analytics_keywords(user_input))
        else "Basear a resposta nos blocos de contexto abaixo; assinalar lacunas se os dados forem insuficientes."
    )

    summary_for_llm = (
        f"postura_risco={risk}; dados={data_status}; "
        f"consulta_catalogada={'sim' if catalog else 'não'}; "
        f"pragmatismo_brevidade={'sim' if pragmatic else 'não'}. "
        f"{iteration_hint}"
    )

    return {
        "risk_posture": risk,
        "data_status": data_status,
        "analytics_catalog_query": catalog,
        "pragmatic_brevity_hint": pragmatic,
        "style_hint": _style_hint(state),
        "summary_for_llm": summary_for_llm,
    }


def apply_task_heuristic_profile(state: State, user_input: str) -> State:
    """Preenche `state.entities['task_profile']` (cópia imutável do estado)."""
    s = state.model_copy(deep=True)
    profile = _compute_task_profile(s, user_input)
    entities = dict(s.entities)
    entities["task_profile"] = profile
    s.entities = entities
    return s


def format_task_profile_for_context(state: State) -> str:
    """Texto estável para a secção 'Perfil da tarefa (heurística)' no ContextBuilder."""
    raw = state.entities.get("task_profile")
    if not isinstance(raw, dict):
        return "(não aplicável)"
    try:
        lines = [
            f"- resumo: {raw.get('summary_for_llm', '')}",
            f"- estilo: {raw.get('style_hint', '')}",
            f"- postura_risco: {raw.get('risk_posture', '')}",
            f"- dados: {raw.get('data_status', '')}",
            f"- consulta_catalogada: {raw.get('analytics_catalog_query', False)}",
        ]
        return "\n".join(lines)
    except Exception:
        return json.dumps(raw, ensure_ascii=False)[:800]
