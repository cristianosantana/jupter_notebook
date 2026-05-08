"""
MemoryComposer MVP (Fase 2.3): mensagens recentes → blocos → ``allocate`` → texto de prompt.

§8 ORDEM_IMPLEMENTAÇÃO: também devolve :class:`~ContextBlock` (sem render) via :meth:`compose_blocks`;
recuperadores episódico / semântico opcionais.
"""

from __future__ import annotations

from collections.abc import Sequence

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.memory.blocks import messages_to_context_blocks
from orion_mcp_v3.memory.episodic_retriever import EpisodicRetriever
from orion_mcp_v3.memory.repositories.conversation_state import ConversationStateRepository
from orion_mcp_v3.memory.semantic_retriever import SemanticRetriever
from orion_mcp_v3.memory.summary_cache import NullSummaryCache, SummaryCachePort
from orion_mcp_v3.runtime import AttentionPolicy
from orion_mcp_v3.runtime.budget_allocator import allocate
from orion_mcp_v3.runtime.prompt_render import render_blocks_to_prompt


class MemoryComposer:
    """
    Orquestra repositório + orçação de tokens (sem chamada ao LLM).

    Opcionalmente antepõe texto vindo do :class:`~orion_mcp_v3.memory.summary_cache.SummaryCachePort`
    como bloco ESSENCE antes dos turnos recentes.

    Com ``semantic_retriever`` + ``semantic_query``, injerta blocos MEMORY por relevância lexical;
    com ``episodic_retriever``, usa-o em vez de ``get_recent`` directo.
    """

    def __init__(
        self,
        repository: ConversationStateRepository,
        *,
        summary_cache: SummaryCachePort | None = None,
    ) -> None:
        self._repo = repository
        self._summ: SummaryCachePort = summary_cache if summary_cache is not None else NullSummaryCache()

    def compose_blocks(
        self,
        session_id: str,
        *,
        max_tokens: int,
        recent_limit: int = 60,
        policy: AttentionPolicy | None = None,
        prefix_blocks: Sequence[ContextBlock] = (),
        semantic_query: str | None = None,
        semantic_retriever: SemanticRetriever | None = None,
        episodic_retriever: EpisodicRetriever | None = None,
    ) -> list[ContextBlock]:
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
        if semantic_query and semantic_retriever is not None:
            sem = semantic_retriever.retrieve(semantic_query.strip(), session_id)
            for b in sem:
                blocks.append(
                    ContextBlock(
                        text=b.text,
                        role=b.role,
                        source=b.source,
                        block_id=b.block_id,
                        metadata={**dict(b.metadata), "retrieval": "semantic"},
                        relevance_score=max(b.relevance_score, 0.55),
                    )
                )
        if episodic_retriever is not None:
            blocks.extend(episodic_retriever.retrieve(session_id, limit=recent_limit))
        else:
            recent = self._repo.get_recent(session_id, limit=recent_limit)
            blocks.extend(messages_to_context_blocks(recent))

        seen_ids: set[str] = set()
        collapsed: list[ContextBlock] = []
        for b in blocks:
            bid = b.block_id
            if bid is not None and bid in seen_ids:
                continue
            if bid is not None:
                seen_ids.add(bid)
            collapsed.append(b)

        fitted = allocate(collapsed, max_tokens, policy=policy)
        return list(fitted)

    def compose(
        self,
        session_id: str,
        *,
        max_tokens: int,
        recent_limit: int = 60,
        policy: AttentionPolicy | None = None,
        prefix_blocks: Sequence[ContextBlock] = (),
        semantic_query: str | None = None,
        semantic_retriever: SemanticRetriever | None = None,
        episodic_retriever: EpisodicRetriever | None = None,
    ) -> str:
        fitted = self.compose_blocks(
            session_id,
            max_tokens=max_tokens,
            recent_limit=recent_limit,
            policy=policy,
            prefix_blocks=prefix_blocks,
            semantic_query=semantic_query,
            semantic_retriever=semantic_retriever,
            episodic_retriever=episodic_retriever,
        )
        return render_blocks_to_prompt(fitted)
