"""
Validação milestone: ContextBlocks → BudgetAllocator → prompt final.

Para ver o prompt no terminal: ``pytest tests/test_runtime_prompt_pipeline.py -s``
"""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime import allocate, render_blocks_to_prompt


def _print_prompt_banner(title: str, prompt: str) -> None:
    bar = "=" * 72
    print(f"\n{bar}\n{title}\n{bar}\n{prompt}\n{bar}\n")


def test_context_blocks_to_allocate_to_prompt_prints_full_pipeline() -> None:
    blocks = [
        ContextBlock(
            "És um assistente útil.",
            ContextRole.SYSTEM,
            ContextSource.SYSTEM,
            relevance_score=0.0,
        ),
        ContextBlock(
            "Qual foi o total de vendas?",
            ContextRole.USER,
            ContextSource.USER_INPUT,
            relevance_score=0.9,
        ),
        ContextBlock(
            "Preciso dos dados agregados por mês.",
            ContextRole.USER,
            ContextSource.USER_INPUT,
            relevance_score=0.5,
        ),
    ]

    fitted = allocate(blocks, max_tokens=2048)
    prompt = render_blocks_to_prompt(fitted)

    _print_prompt_banner("PROMPT FINAL (ContextBlocks → allocate → render)", prompt)

    assert "[SYSTEM]" in prompt
    assert "És um assistente" in prompt
    assert "[USER]" in prompt
    assert "vendas" in prompt


def test_tight_budget_prompt_prints_truncation() -> None:
    """Orçamento pequeno: blocos podem ser truncados; o prompt impresso reflecte isso."""
    long_user = "y" * 400
    blocks = [
        ContextBlock("SYS", ContextRole.SYSTEM, ContextSource.SYSTEM),
        ContextBlock(long_user, ContextRole.USER, ContextSource.USER_INPUT, relevance_score=1.0),
    ]

    fitted = allocate(blocks, max_tokens=15)
    prompt = render_blocks_to_prompt(fitted)

    _print_prompt_banner("PROMPT FINAL (orçamento apertado — possível truncagem)", prompt)

    assert "[SYSTEM]" in prompt
    assert fitted[1].metadata.get("truncated") is True
