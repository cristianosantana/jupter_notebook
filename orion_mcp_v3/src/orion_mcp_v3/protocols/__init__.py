"""Protocols: interfaces tipadas (`typing.Protocol`) para extensibilidade."""

from orion_mcp_v3.protocols.llm import (
    ChatMessage,
    EchoLLMProvider,
    LLMProvider,
    LLMResponse,
    LLMResponseMeta,
    LLMStreamChunk,
    LLMUsage,
    NullLLMProvider,
)
from orion_mcp_v3.protocols.summarizer import SummarizerProtocol

__all__ = [
    "ChatMessage",
    "EchoLLMProvider",
    "LLMProvider",
    "LLMResponse",
    "LLMResponseMeta",
    "LLMStreamChunk",
    "LLMUsage",
    "NullLLMProvider",
    "SummarizerProtocol",
]
