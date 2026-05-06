from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from openai import APIStatusError, AsyncOpenAI, BadRequestError

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.llm import model_config as _model_config
from orion_mcp.core.strategy import Strategy

resolve_chat_model_id = _model_config.resolve_chat_model_id
resolve_model = _model_config.resolve_model

_MSG_EMPTY_STREAM_LENGTH_PT = (
    "A geração atingiu o limite de tokens de saída antes de produzir texto visível "
    "(comum em modelos com raciocínio interno). Aumenta `ORION_LLM_COMPLETION_MAX_TOKENS` e tenta de novo."
)
_MSG_EMPTY_STREAM_GENERIC_PT = (
    "O modelo não devolveu texto na resposta em streaming. Verifica o modelo configurado, quotas e logs."
)
_MSG_EMPTY_STREAM_FILTER_PT = "A resposta foi omitida pelo filtro de conteúdo da API."


def _reasoning_effort_for_model(model: str) -> str | None:
    """Reduz tokens de raciocínio em modelos que suportam `reasoning_effort` na Chat Completions API."""
    m = (model or "").lower()
    if "gpt-5" in m or m.startswith(("o1", "o3", "o4")):
        return "low"
    return None


class LLMProvider(ABC):
    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream de texto (deltas). Implementações concretas devem yield apenas conteúdo."""
        if False:  # pragma: no cover
            yield ""

    async def generate(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        system_prompt: str | None = None,
    ) -> str:
        """Resposta completa (ex.: JSON one-shot para insights). Agrega `generate_stream`."""
        parts: list[str] = []
        async for piece in self.generate_stream(
            prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        ):
            parts.append(piece)
        return "".join(parts)


class MockLLMProvider(LLMProvider):
    async def generate_stream(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        _ = temperature, max_tokens
        sys = (system_prompt or "").strip()
        if sys:
            yield "[system]"
            yield sys[:120]
            yield "|"
        yield f"[mock:{model}] "
        yield prompt[:200]
        yield "…"


class OpenAILLMProvider(LLMProvider):
    def __init__(self, client: AsyncOpenAI, settings: Settings):
        self._client = client
        self._settings = settings

    async def generate_stream(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        messages: list[dict[str, str]] = []
        sys = (system_prompt or "").strip()
        if sys:
            messages.append({"role": "system", "content": sys})
        messages.append({"role": "user", "content": prompt})
        use_max_completion = False
        temp_val: float | None = temperature
        reasoning_effort = _reasoning_effort_for_model(model)
        stream: Any = None
        for _ in range(7):
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": True,
            }
            if temp_val is not None:
                kwargs["temperature"] = temp_val
            if use_max_completion:
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens
            if reasoning_effort is not None:
                kwargs["reasoning_effort"] = reasoning_effort
            try:
                stream = await self._client.chat.completions.create(**kwargs)
                break
            except (BadRequestError, APIStatusError) as e:
                if getattr(e, "status_code", None) != 400:
                    raise
                err = str(e).lower()
                if "max_completion_tokens" in err or (
                    "max_tokens" in err and "unsupported" in err
                ):
                    use_max_completion = True
                    continue
                if "temperature" in err and "unsupported" in err:
                    temp_val = None
                    continue
                if reasoning_effort is not None and (
                    "reasoning" in err or "reasoning_effort" in err
                ):
                    reasoning_effort = None
                    continue
                raise
        if stream is None:
            raise RuntimeError("openai chat completion stream failed after retries")

        last_finish: str | None = None
        refusal_parts: list[str] = []
        content_yielded = 0
        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            ch0 = choices[0]
            fr = getattr(ch0, "finish_reason", None)
            if fr:
                last_finish = fr
            delta = getattr(ch0, "delta", None)
            if delta is None:
                continue
            ref = getattr(delta, "refusal", None)
            if ref:
                refusal_parts.append(ref)
            content = getattr(delta, "content", None)
            if content:
                content_yielded += 1
                yield content

        if content_yielded == 0:
            if refusal_parts:
                yield "".join(refusal_parts)
            elif last_finish == "length":
                yield _MSG_EMPTY_STREAM_LENGTH_PT
            elif last_finish == "content_filter":
                yield _MSG_EMPTY_STREAM_FILTER_PT
            else:
                yield _MSG_EMPTY_STREAM_GENERIC_PT


def insights_bundle_user_prompt(context: str) -> str:
    """Texto `user` enviado a `generate` no ramo insights (sem mensagem system)."""
    return (
        "Responde em JSON válido com chaves insights (lista de até 5 strings curtas) "
        "e reply (texto útil para o utilizador). Contexto:\n"
        f"{context}"
    )


async def generate_insights_bundle(
    llm: LLMProvider,
    *,
    context: str,
    settings: Settings,
    strategy: Strategy,
) -> tuple[list[str], str]:
    """
    Uma única chamada LLM devolve insights + texto de resposta (JSON simples).
    """
    model = resolve_chat_model_id(settings, strategy)
    prompt = insights_bundle_user_prompt(context)
    raw = await llm.generate(
        prompt, model=model, temperature=0.2, max_tokens=settings.llm_insights_max_tokens
    )
    insights, reply = _parse_insights_bundle(raw)
    return insights, reply


def _parse_insights_bundle(raw: str) -> tuple[list[str], str]:
    import json

    raw = raw.strip()
    try:
        data = json.loads(raw)
        ins = data.get("insights") or []
        rep = str(data.get("reply") or "")
        if isinstance(ins, list):
            return [str(x) for x in ins[:5]], rep
    except Exception:
        pass
    return [], raw or "(sem resposta)"


def build_llm(settings: Settings) -> LLMProvider:
    if not settings.openai_api_key:
        return MockLLMProvider()
    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_http_timeout_seconds,
    )
    return OpenAILLMProvider(client, settings)
