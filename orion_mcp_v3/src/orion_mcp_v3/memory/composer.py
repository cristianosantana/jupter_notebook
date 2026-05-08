"""
MemoryComposer MVP (Fase 2.3): mensagens recentes → blocos → ``allocate`` → texto de prompt.
"""

from __future__ import annotations

from collections.abc import Sequence

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.memory.blocks import messages_to_context_blocks
from orion_mcp_v3.memory.repositories.conversation_state import ConversationStateRepository
from orion_mcp_v3.memory.summary_cache import NullSummaryCache, SummaryCachePort
from orion_mcp_v3.runtime import AttentionPolicy
from orion_mcp_v3.runtime.budget_allocator import allocate
from orion_mcp_v3.runtime.prompt_render import render_blocks_to_prompt


class MemoryComposer:
    """
    Orquestra repositório + orçação de tokens (sem chamada ao LLM).

    Opcionalmente antepõe texto vindo do :class:`~orion_mcp_v3.memory.summary_cache.SummaryCachePort`
    como bloco ESSENCE antes dos turnos recentes.
    """

    def __init__(
        self,
        repository: ConversationStateRepository,
        *,
        summary_cache: SummaryCachePort | None = None,
    ) -> None:
        self._repo = repository
        self._summ: SummaryCachePort = summary_cache if summary_cache is not None else NullSummaryCache()

    def compose(
        self,
        session_id: str,
        *,
        max_tokens: int,
        recent_limit: int = 60,
        policy: AttentionPolicy | None = None,
        prefix_blocks: Sequence[ContextBlock] = (),
    ) -> str:
        blocks: list[ContextBlock] = list(prefix_blocks)
        cached = self._summ.get_summary(session_id)
        if cached and cached.strip():
            blocks.append(
                ContextBlock(
                    text=cached.strip(),
                    role=ContextRole.NEUTRAL,
                    source=ContextSource.ESSENCE,
                    block_id="summary:cache",
                    metadata={"origin": "summary_cache"},
                    relevance_score=0.35,
                )
            )
        recent = self._repo.get_recent(session_id, limit=recent_limit)
        blocks.extend(messages_to_context_blocks(recent))
        fitted = allocate(blocks, max_tokens, policy=policy)
        return render_blocks_to_prompt(fitted)
