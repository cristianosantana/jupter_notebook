"""Memória conversacional: repositório, blocos, composer e cache de resumos (Fase 2)."""

from orion_mcp_v3.memory.blocks import message_to_context_block, messages_to_context_blocks
from orion_mcp_v3.memory.composer import MemoryComposer
from orion_mcp_v3.memory.episodic_retriever import EpisodicRetriever
from orion_mcp_v3.memory.semantic_retriever import SemanticRetriever
from orion_mcp_v3.memory.repositories import (
    ConversationMessage,
    ConversationStateRepository,
    InMemoryConversationStateRepository,
)
from orion_mcp_v3.memory.summary_cache import (
    InMemorySummaryCache,
    NullSummaryCache,
    RedisSummaryCache,
    SummaryCachePort,
)

__all__ = [
    "ConversationMessage",
    "ConversationStateRepository",
    "EpisodicRetriever",
    "InMemoryConversationStateRepository",
    "InMemorySummaryCache",
    "MemoryComposer",
    "message_to_context_block",
    "messages_to_context_blocks",
    "NullSummaryCache",
    "RedisSummaryCache",
    "SemanticRetriever",
    "SummaryCachePort",
]

