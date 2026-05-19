"""Memória cognitiva: repositório, retrieval pipeline, composer, retrievers."""

from orion_mcp_v3.memory.blocks import message_to_context_block, messages_to_context_blocks
from orion_mcp_v3.memory.composer import MemoryComposer, MemoryLayer
from orion_mcp_v3.memory.episodic_retriever import EpisodicRetriever, EpisodicScore
from orion_mcp_v3.memory.repositories import (
    ConversationMessage,
    ConversationStateRepository,
    InMemoryConversationStateRepository,
)
from orion_mcp_v3.memory.retrieval_pipeline import LayeredMemoryResult, MemoryRetrievalPipeline
from orion_mcp_v3.memory.semantic_retriever import SemanticHit, SemanticRetriever
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
    "EpisodicScore",
    "InMemoryConversationStateRepository",
    "InMemorySummaryCache",
    "LayeredMemoryResult",
    "MemoryComposer",
    "MemoryLayer",
    "MemoryRetrievalPipeline",
    "message_to_context_block",
    "messages_to_context_blocks",
    "NullSummaryCache",
    "RedisSummaryCache",
    "SemanticHit",
    "SemanticRetriever",
    "SummaryCachePort",
]
