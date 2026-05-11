"""
LLM Provider Contracts (Fase 5.1) — interfaces formais para geração de texto.

Três modos: ``generate`` (prompt string), ``chat`` (lista de mensagens),
``stream`` (chat com iterador assíncrono de chunks).

Metadata standard: ``usage``, ``latency``, ``finish_reason``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Mapping, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Consumo de tokens reportado pelo provider."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMResponseMeta:
    """Metadata standard que acompanha qualquer resposta do provider."""

    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    model: str = ""
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Resposta completa (não-streaming)."""

    text: str
    meta: LLMResponseMeta = field(default_factory=LLMResponseMeta)


@dataclass(frozen=True, slots=True)
class LLMStreamChunk:
    """Fragmento durante streaming."""

    delta: str
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """Mensagem individual de chat (role + content)."""

    role: str
    content: str


@runtime_checkable
class LLMProvider(Protocol):
    """Interface mínima para qualquer backend de LLM (OpenAI, Anthropic, local, mock)."""

    async def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        """Texto livre → resposta."""
        ...

    async def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> LLMResponse:
        """Chat multi-turno → resposta."""
        ...

    async def stream(self, messages: Sequence[ChatMessage], **kwargs: Any) -> AsyncIterator[LLMStreamChunk]:
        """Chat multi-turno → iterador assíncrono de chunks."""
        ...


class NullLLMProvider:
    """Provider noop para testes — devolve eco ou texto fixo."""

    def __init__(self, *, fixed_response: str = "[NullLLM] Sem provider configurado.") -> None:
        self._fixed = fixed_response

    async def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            text=self._fixed,
            meta=LLMResponseMeta(finish_reason="null_provider", model="null"),
        )

    async def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            text=self._fixed,
            meta=LLMResponseMeta(finish_reason="null_provider", model="null"),
        )

    async def stream(self, messages: Sequence[ChatMessage], **kwargs: Any) -> AsyncIterator[LLMStreamChunk]:
        yield LLMStreamChunk(delta=self._fixed, finish_reason="null_provider")


class EchoLLMProvider:
    """Provider para testes — devolve o último conteúdo do utilizador."""

    async def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            text=f"[Echo] {prompt[:500]}",
            meta=LLMResponseMeta(
                usage=LLMUsage(prompt_tokens=len(prompt) // 4, completion_tokens=len(prompt) // 4),
                finish_reason="stop",
                model="echo",
            ),
        )

    async def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> LLMResponse:
        last = messages[-1].content if messages else ""
        return LLMResponse(
            text=f"[Echo] {last[:500]}",
            meta=LLMResponseMeta(
                usage=LLMUsage(prompt_tokens=len(last) // 4, completion_tokens=len(last) // 4),
                finish_reason="stop",
                model="echo",
            ),
        )

    async def stream(self, messages: Sequence[ChatMessage], **kwargs: Any) -> AsyncIterator[LLMStreamChunk]:
        last = messages[-1].content if messages else ""
        text = f"[Echo] {last[:500]}"
        for i in range(0, len(text), 20):
            yield LLMStreamChunk(delta=text[i : i + 20])
        yield LLMStreamChunk(delta="", finish_reason="stop")
