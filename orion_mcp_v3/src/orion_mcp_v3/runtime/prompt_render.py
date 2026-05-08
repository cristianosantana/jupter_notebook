"""Junta :class:`ContextBlock` orçados num único texto de prompt (Fase 1)."""

from __future__ import annotations

from collections.abc import Sequence

from orion_mcp_v3.contracts.context_block import ContextBlock


def render_blocks_to_prompt(blocks: Sequence[ContextBlock]) -> str:
    """
    Formato: ``[ROLE]`` por bloco, texto em baixo, separado por linhas em branco.
    Usado após :func:`~orion_mcp_v3.runtime.budget_allocator.allocate`.
    """
    parts: list[str] = []
    for b in blocks:
        header = b.role.value
        parts.append(f"[{header.upper()}]\n{b.text.strip()}")
    return "\n\n".join(parts).strip()
