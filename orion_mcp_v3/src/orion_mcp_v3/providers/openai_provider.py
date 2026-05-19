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
    Para certos modelos (ex.: ``gpt-5*``, ``o1*``), a API usa
    ``max_completion_tokens`` em vez de ``max_tokens``, e não aceita
    ``temperature`` excepto o valor por defeito — nesses casos o parâmetro
    ``temperature`` é omitido em :meth:`_merge_params`.
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

    @staticmethod
    def _completion_budget_for_constrained_model(max_tokens: int) -> int:
        """Evita respostas vazias quando modelos reasoning consomem todo o budget interno."""
        return max(int(max_tokens), 8192)

    @staticmethod
    def _is_constrained_chat_model(model: str) -> bool:
        """Modelos com ``max_completion_tokens`` e temperatura só no default da API."""
        m = model.strip().lower()
        return (
            m.startswith("gpt-5")
            or m.startswith("o1")
            or m.startswith("o3")
            or m.startswith("o4")
        )

    def _merge_params(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        model = kwargs.pop("model", self._model)
        temperature = kwargs.pop("temperature", self._temperature)
        max_tok = kwargs.pop("max_tokens", self._max_tokens)
        max_compl = kwargs.pop("max_completion_tokens", None)

        merged: dict[str, Any] = {"model": model, **kwargs}

        if not self._is_constrained_chat_model(model):
            merged["temperature"] = temperature

        if max_compl is not None:
            merged["max_completion_tokens"] = max_compl
        elif self._is_constrained_chat_model(model):
            merged["max_completion_tokens"] = self._completion_budget_for_constrained_model(max_tok)
        else:
            merged["max_tokens"] = max_tok
        return merged

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
