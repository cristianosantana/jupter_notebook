from orion_mcp.core.config.settings import Settings
from orion_mcp.core.context.context_builder import (
    _NOTE_SYS_TRUNC,
    apply_llm_context_max_chars,
)


def test_apply_llm_context_max_chars_noop_when_unset() -> None:
    s = Settings()
    sys_o, usr_o, t = apply_llm_context_max_chars("system", "u" * 5000, s)
    assert sys_o == "system"
    assert usr_o == "u" * 5000
    assert t is False


def test_apply_llm_context_max_chars_truncates_user() -> None:
    s = Settings(llm_context_max_chars=100)
    sys_o, usr_o, t = apply_llm_context_max_chars("S" * 20, "U" * 200, s)
    assert t is True
    assert sys_o == "S" * 20
    assert len(sys_o) + len(usr_o) <= 100
    assert "ORION_LLM_CONTEXT_MAX_CHARS" in usr_o


def test_apply_llm_context_max_chars_truncates_system_when_needed() -> None:
    s = Settings(llm_context_max_chars=80)
    sys_o, usr_o, t = apply_llm_context_max_chars("S" * 100, "U" * 50, s)
    assert t is True
    assert len(sys_o) + len(usr_o) <= 80


def test_apply_llm_context_max_chars_reserves_user_when_system_fills_cap() -> None:
    """Evita `rest == 0`: system + sufixo no teto máximo não podem apagar o user."""
    cap = 500
    s = Settings(llm_context_max_chars=cap)
    sys_len = cap - len(_NOTE_SYS_TRUNC)
    sys_o, usr_o, t = apply_llm_context_max_chars("x" * sys_len, "y" * 10_000, s)
    assert t is True
    assert len(usr_o) > 0
    assert len(sys_o) + len(usr_o) <= cap
