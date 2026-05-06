"""Tetos unificados de prompt (tokens) e resumo de tool (caracteres)."""

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.context.context_builder import effective_llm_prompt_token_cap


def test_effective_prompt_uses_min_legacy_when_budget_unset() -> None:
    s = Settings(
        context_max_tokens=500,
        llm_max_prompt_tokens=900,
        llm_prompt_token_budget=None,
    )
    assert s.effective_prompt_token_budget == 500
    assert effective_llm_prompt_token_cap(s) == 500


def test_effective_prompt_canonical_budget_overrides_legacy() -> None:
    s = Settings(
        context_max_tokens=100,
        llm_max_prompt_tokens=300,
        llm_prompt_token_budget=4000,
    )
    assert s.effective_prompt_token_budget == 4000
    assert effective_llm_prompt_token_cap(s) == 4000


def test_tool_summary_chars_derived_when_unset() -> None:
    s = Settings(
        llm_prompt_token_budget=1000,
        tool_llm_summary_max_chars=None,
    )
    # 1000 * 4 * 0.6 = 2400
    assert s.tool_llm_summary_max_chars == 2400
    assert s.resolved_tool_llm_summary_max_chars() == 2400


def test_tool_summary_explicit_chars() -> None:
    s = Settings(tool_llm_summary_max_chars=15000)
    assert s.tool_llm_summary_max_chars == 15000


def test_llm_tool_context_chars_alias() -> None:
    s = Settings.model_validate({"llm_tool_context_chars": 8888})
    assert s.tool_llm_summary_max_chars == 8888


def test_effective_tool_summary_max_chars_full_rows_uses_context_cap() -> None:
    s = Settings.model_validate(
        {
            "tool_llm_catalog_full_rows": True,
            "llm_context_max_chars": 200_000,
            "tool_llm_summary_max_chars": 5000,
        }
    )
    eff = s.effective_tool_llm_summary_max_chars()
    assert eff >= int(200_000 * 0.78)
    assert eff <= 2_000_000


def test_effective_tool_summary_max_chars_without_full_rows_matches_resolved() -> None:
    s = Settings.model_validate(
        {
            "tool_llm_catalog_full_rows": False,
            "llm_context_max_chars": 500_000,
            "tool_llm_summary_max_chars": 8000,
        }
    )
    assert s.effective_tool_llm_summary_max_chars() == s.resolved_tool_llm_summary_max_chars()
