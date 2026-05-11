"""
Provider OpenAI (Fase 5.1) — implementação concreta de :class:`~LLMProvider`.

Usa ``openai.AsyncOpenAI`` quando disponível; se ``openai`` não estiver instalado,
a inicialização lança ``ImportError`` descritivo.
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Sequence

from orion_mcp_v3.protocols.llm import (
    ChatMessage,
    LLMResponse,
    LLMResponseMeta,
    LLMStreamChunk,
    LLMUsage,
)


class OpenAIProvider:
    """
    Wrapper sobre ``openai.AsyncOpenAI`` compatível com :class:`~LLMProvider`.

    Parâmetros opcionais (``temperature``, ``max_tokens``, ``model``) servem como
    defaults; podem ser sobrepostos em cada chamada via ``**kwargs``.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-5-mini",
        temperature: float = 0.3,
        max_tokens: int = 2048,
        base_url: str | None = None,
    ) -> None:
        try:
            import openai  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "O pacote 'openai' é necessário para OpenAIProvider. "
                "Instale com: pip install openai"
            ) from exc

        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.AsyncOpenAI(**kwargs)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def _merge_params(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": kwargs.pop("model", self._model),
            "temperature": kwargs.pop("temperature", self._temperature),
            "max_tokens": kwargs.pop("max_tokens", self._max_tokens),
            **kwargs,
        }

    @staticmethod
    def _extract_meta(raw: Any, elapsed_ms: float) -> LLMResponseMeta:
        usage_raw = getattr(raw, "usage", None)
        if usage_raw is not None:
            usage = LLMUsage(
                prompt_tokens=getattr(usage_raw, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage_raw, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage_raw, "total_tokens", 0) or 0,
            )
        else:
            usage = LLMUsage()
        choice = raw.choices[0] if raw.choices else None
        finish = getattr(choice, "finish_reason", "stop") if choice else "stop"
        model = getattr(raw, "model", "") or ""
        return LLMResponseMeta(
            usage=usage,
            latency_ms=elapsed_ms,
            finish_reason=finish or "stop",
            model=model,
        )

    async def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        params = self._merge_params(kwargs)
        messages = [{"role": "user", "content": prompt}]
        t0 = time.monotonic()
        raw = await self._client.chat.completions.create(messages=messages, **params)
        elapsed = (time.monotonic() - t0) * 1000.0
        text = raw.choices[0].message.content if raw.choices else ""
        return LLMResponse(text=text or "", meta=self._extract_meta(raw, elapsed))

    async def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> LLMResponse:
        params = self._merge_params(kwargs)
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        t0 = time.monotonic()
        raw = await self._client.chat.completions.create(messages=msgs, **params)
        elapsed = (time.monotonic() - t0) * 1000.0
        text = raw.choices[0].message.content if raw.choices else ""
        return LLMResponse(text=text or "", meta=self._extract_meta(raw, elapsed))

    async def stream(self, messages: Sequence[ChatMessage], **kwargs: Any) -> AsyncIterator[LLMStreamChunk]:
        params = self._merge_params(kwargs)
        params["stream"] = True
        msgs = [{"role": m.role, "content": m.content} for m in messages]
        raw_stream = await self._client.chat.completions.create(messages=msgs, **params)
        async for chunk in raw_stream:
            delta = ""
            finish = None
            if chunk.choices:
                c = chunk.choices[0]
                delta = getattr(c.delta, "content", "") or ""
                finish = getattr(c, "finish_reason", None)
            yield LLMStreamChunk(delta=delta, finish_reason=finish)
