from __future__ import annotations

from orion_mcp_v2.config.settings import Settings


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _clip(text: str, budget: int) -> tuple[str, bool]:
    if _estimate_tokens(text) <= budget:
        return text, False
    max_chars = max(40, budget * 4 - 40)
    return text[:max_chars] + "…", True


def effective_llm_prompt_token_cap(settings: Settings) -> int:
    return settings.effective_prompt_token_budget


def cap_llm_prompt(text: str, settings: Settings) -> tuple[str, bool]:
    cap = effective_llm_prompt_token_cap(settings)
    return _clip(text, cap)


_NOTE_USER_TRUNC = "\n… [truncado: ORION_V2_LLM_CONTEXT_MAX_CHARS (user/contexto)]"
_NOTE_SYS_TRUNC = "… [truncado: ORION_V2_LLM_CONTEXT_MAX_CHARS (system)]"


def apply_llm_context_max_chars(
    system_prompt: str,
    user_text: str,
    settings: Settings,
) -> tuple[str, str, bool]:
    """
    Garante len(system)+len(user) <= llm_context_max_chars quando definido.
    Prioridade: cortar user; só se system sozinho exceder o teto trunca system.
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
    space_for_sys = cap - len(_NOTE_SYS_TRUNC)
    if space_for_sys < 1:
        return _NOTE_SYS_TRUNC[:cap], "", True
    sys_out = sys[:space_for_sys] + _NOTE_SYS_TRUNC
    rest = cap - len(sys_out)
    if rest > 0 and usr:
        return sys_out, usr[:rest], True
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


def skill_render_char_budgets(settings: Settings) -> dict[str, int]:
    """Limites por secção do skill template (caracteres), derivados do orçamento global."""
    eff_chars = max(1024, settings.effective_prompt_token_budget * 4)
    return {
        "data_summary": min(12_000, eff_chars // 2),
        "sample": min(8000, eff_chars // 4),
        "insights": min(4000, eff_chars // 8),
    }
