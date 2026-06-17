"""Provider OpenAI isolado do Chat Público."""

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


class OpenAIPublicLLMProvider:
    """Wrapper mínimo sobre ``openai.AsyncOpenAI`` para intent + narrador."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 2048,
        base_url: str | None = None,
        temperature: float = 0.3,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key é obrigatório para OpenAIPublicLLMProvider")
        try:
            import openai  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "O pacote 'openai' é necessário. Instale com: pip install openai"
            ) from exc

        self._client = openai.AsyncOpenAI(
            api_key=api_key.strip(),
            base_url=base_url or None,
        )
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    def _params(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {
            "model": kwargs.pop("model", self._model),
            "temperature": kwargs.pop("temperature", self._temperature),
            "max_tokens": kwargs.pop("max_tokens", self._max_tokens),
            **kwargs,
        }

    @staticmethod
    def _meta(raw: Any, elapsed_ms: float) -> LLMResponseMeta:
        usage_raw = getattr(raw, "usage", None)
        usage = LLMUsage()
        if usage_raw is not None:
            usage = LLMUsage(
                prompt_tokens=getattr(usage_raw, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage_raw, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage_raw, "total_tokens", 0) or 0,
            )
        choice = raw.choices[0] if raw.choices else None
        finish = getattr(choice, "finish_reason", None) if choice is not None else "stop"
        return LLMResponseMeta(
            usage=usage,
            latency_ms=elapsed_ms,
            finish_reason=finish or "stop",
            model=getattr(raw, "model", "") or "",
        )

    async def generate(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return await self.chat([ChatMessage(role="user", content=prompt)], **kwargs)

    async def chat(self, messages: Sequence[ChatMessage], **kwargs: Any) -> LLMResponse:
        t0 = time.monotonic()
        payload = [{"role": m.role, "content": m.content} for m in messages]
        raw = await self._client.chat.completions.create(
            messages=payload,
            **self._params(dict(kwargs)),
        )
        text = raw.choices[0].message.content or ""
        return LLMResponse(text=text, meta=self._meta(raw, (time.monotonic() - t0) * 1000.0))

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        **kwargs: Any,
    ) -> AsyncIterator[LLMStreamChunk]:
        payload = [{"role": m.role, "content": m.content} for m in messages]
        stream = await self._client.chat.completions.create(
            messages=payload,
            stream=True,
            **self._params(dict(kwargs)),
        )
        async for event in stream:
            if not event.choices:
                continue
            choice = event.choices[0]
            delta = choice.delta.content or ""
            finish = choice.finish_reason
            if delta or finish:
                yield LLMStreamChunk(delta=delta, finish_reason=finish)
