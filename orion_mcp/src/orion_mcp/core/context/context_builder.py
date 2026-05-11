from __future__ import annotations

from dataclasses import dataclass

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.state.intent_heuristic import format_task_profile_for_context
from orion_mcp.core.state.models import State


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _clip(text: str, budget: int) -> tuple[str, bool]:
    if _estimate_tokens(text) <= budget:
        return text, False
    max_chars = max(40, budget * 4 - 40)
    return text[:max_chars] + "…", True


def effective_llm_prompt_token_cap(settings: Settings) -> int:
    """Teto efectivo para prompts enviados ao LLM (Secção 3)."""
    return settings.effective_prompt_token_budget


def _data_cache_section_token_budget(settings: Settings) -> int:
    """
    Orçamento estimado (tokens) para «Dados resumidos».
    Evita o teto fixo baixo (~1200) que cortava grelhas grandes antes do `cap_llm_prompt`.
    """
    eff = effective_llm_prompt_token_cap(settings)
    desired = max(1200, eff - 450)
    return min(settings.context_section_budget_tokens, desired)


@dataclass(frozen=True)
class ContextBuildResult:
    """Texto de contexto + sinalização de truncagem para `payload['perf']` / `state.flags['perf']`."""

    text: str
    context_truncated: bool


def cap_llm_prompt(text: str, settings: Settings) -> tuple[str, bool]:
    """Garante que o prompt final (incl. sufixos do orquestrador) não excede o teto Secção 3."""
    cap = effective_llm_prompt_token_cap(settings)
    return _clip(text, cap)


_NOTE_USER_TRUNC = "\n… [truncado: ORION_LLM_CONTEXT_MAX_CHARS (user/contexto)]"
_NOTE_SYS_TRUNC = "… [truncado: ORION_LLM_CONTEXT_MAX_CHARS (system)]"


def apply_llm_context_max_chars(
    system_prompt: str,
    user_text: str,
    settings: Settings,
) -> tuple[str, str, bool]:
    """
    Por pedido HTTP: garante len(system)+len(user) <= `llm_context_max_chars` quando definido.
    Prioridade: cortar o texto `user`; só se o `system` sozinho exceder o teto é que se trunca o system.
    """
    cap = settings.llm_context_max_chars
    if cap is None:
        return system_prompt, user_text, False
    sys = system_prompt or ""
    usr = user_text or ""
    if len(sys) + len(usr) <= cap:
        return sys, usr, False
    space_for_user = cap - len(sys) - len(_NOTE_USER_TRUNC)
    if space_for_user > 0:
        return sys, usr[:space_for_user] + _NOTE_USER_TRUNC, True
    # System ocupa todo o teto: truncar system e deixar user mínimo ou vazio.
    space_for_sys = cap - len(_NOTE_SYS_TRUNC)
    if space_for_sys < 1:
        return _NOTE_SYS_TRUNC[:cap], "", True
    sys_out = sys[:space_for_sys] + _NOTE_SYS_TRUNC
    rest = cap - len(sys_out)
    if rest > 0 and usr:
        return sys_out, usr[:rest], True
    # System + sufixo preencheram o teto (`rest == 0`): sem isto o `user` ficava vazio.
    if usr and rest <= 0:
        note_len = len(_NOTE_SYS_TRUNC)
        min_user_floor = max(1, min(256, cap // 4))
        target_sys_max = cap - min_user_floor - note_len
        if target_sys_max >= 1:
            sys_out2 = sys[:target_sys_max] + _NOTE_SYS_TRUNC
            rest2 = cap - len(sys_out2)
            if rest2 > 0:
                return sys_out2, usr[:rest2], True
    return sys_out, "", True


def build_context(
    state: State, user_input: str, settings: Settings, *, long_memory: str = ""
) -> ContextBuildResult:
    """
    Monta contexto por secções com teto global (sem histórico de mensagens, sem JSON bruto de tools).
    """
    effective = effective_llm_prompt_token_cap(settings)
    total_budget = min(settings.context_section_budget_tokens, effective)

    profile_body = format_task_profile_for_context(state)
    sections: list[tuple[str, str, int]] = [
        ("Intenção", state.intent or "(vazio)", 120),
        ("Métrica", state.current_metric or "(não definida)", 120),
        ("Perfil da tarefa (heurística)", profile_body, 300),
        ("Pergunta atual", (user_input or "").strip() or "(vazio)", 400),
        ("Dados resumidos", _summaries_block(state), _data_cache_section_token_budget(settings)),
        ("Insights", "\n".join(f"- {i}" for i in state.insights) or "(nenhum)", 400),
        ("Memória curta", state.short_memory or "(vazio)", 400),
        ("Memória longa relevante", long_memory or "(vazio)", 600),
    ]
    # Secções 0–3 (pergunta + perfil antes dos dados) nunca são omitidas por `break`;
    # o orçamento restante aplica-se sobretudo a «Dados resumidos» e memórias.
    essentials_count = 4
    parts: list[str] = []
    used = 0
    truncated = False
    for idx, (title, body, sec_budget) in enumerate(sections):
        if idx >= essentials_count and used >= total_budget:
            break
        remaining = total_budget - used
        if idx < essentials_count:
            body_cap = min(
                sec_budget,
                max(32, remaining) if remaining > 0 else min(sec_budget, 32),
            )
        else:
            if remaining <= 0:
                break
            body_cap = min(sec_budget, remaining)
        clipped, t = _clip(body, body_cap)
        truncated = truncated or t
        block = f"### {title}\n{clipped}\n"
        parts.append(block)
        used += _estimate_tokens(block)
    text = "\n".join(parts).strip()
    if _estimate_tokens(text) > effective:
        text, t = _clip(text, effective)
        truncated = truncated or t
    return ContextBuildResult(text=text, context_truncated=truncated)


def _summaries_block(state: State) -> str:
    lines: list[str] = []
    for k, entry in state.data_cache.items():
        short_key = k[:16] + "…" if len(k) > 24 else k
        lines.append(f"- {short_key}: {entry.summary}")
    return "\n".join(lines) if lines else "(sem cache de dados)"
