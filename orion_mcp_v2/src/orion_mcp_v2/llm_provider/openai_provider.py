from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from orion_mcp_v2.llm_provider.llm_io_dump import write_llm_io_dump

if TYPE_CHECKING:
    from orion_mcp_v2.config.settings import Settings

_logger = logging.getLogger(__name__)


def _assistant_text_from_chat_response(resp: Any) -> str:
    """Usa `content`; se vazio, tenta `refusal` (modelos recentes podem só preencher um dos dois)."""
    choices = getattr(resp, "choices", None) or []
    if not choices:
        _logger.warning("openai_response_no_choices model=%s", getattr(resp, "model", None))
        return ""
    choice = choices[0]
    msg = getattr(choice, "message", None)
    if msg is None:
        fr = getattr(choice, "finish_reason", None)
        _logger.warning("openai_choice_no_message finish_reason=%s", fr)
        return ""
    text = (getattr(msg, "content", None) or "").strip()
    if text:
        return text
    refusal = getattr(msg, "refusal", None)
    if refusal:
        fs = str(refusal).strip()
        if fs:
            return fs
    fr = getattr(choice, "finish_reason", None)
    _logger.warning(
        "openai_empty_assistant_message finish_reason=%s model=%s",
        fr,
        getattr(resp, "model", None),
    )
    return ""


def _completion_limit_kwargs(model: str, limit: int) -> dict[str, int]:
    """APIs novas (ex.: gpt-5*, o*) rejeitam `max_tokens`; usam `max_completion_tokens`."""
    m = (model or "").strip().lower()
    if "/" in m:
        m = m.rsplit("/", 1)[-1]
    if (
        m.startswith("gpt-5")
        or m.startswith("o1")
        or m.startswith("o3")
        or m.startswith("o4")
    ):
        return {"max_completion_tokens": limit}
    return {"max_tokens": limit}


class OpenAIChatService:
    def __init__(self, settings: "Settings"):
        self._settings = settings
        key = (settings.openai_api_key or "").strip()
        self._client = AsyncOpenAI(api_key=key or "dummy", timeout=settings.openai_timeout_seconds) if key else None

    async def complete(
        self,
        *,
        system_prompt: str,
        user_text: str,
        model: str,
        max_tokens: int,
    ) -> str:
        kw = _completion_limit_kwargs(model, max_tokens)
        if self._client is None:
            reply = (
                "[orion_v2_mock_llm] "
                + (system_prompt[:120] + "…")
                + " | "
                + (user_text[:200] + "…")
            )
            write_llm_io_dump(
                self._settings,
                model=model,
                max_tokens=max_tokens,
                completion_kw=kw,
                system_prompt=system_prompt,
                user_text=user_text,
                raw_response=None,
                extracted_reply=reply,
                mode="mock_no_api_key",
            )
            return reply
        resp = await self._client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            **kw,
        )
        text = _assistant_text_from_chat_response(resp)
        write_llm_io_dump(
            self._settings,
            model=model,
            max_tokens=max_tokens,
            completion_kw=kw,
            system_prompt=system_prompt,
            user_text=user_text,
            raw_response=resp,
            extracted_reply=text,
            mode="chat_completions",
        )
        return text

    async def complete_stream(
        self,
        *,
        system_prompt: str,
        user_text: str,
        model: str,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Streaming token deltas (compatível com SSE). Mock: fatias do mesmo texto que `complete`."""
        if self._client is None:
            text = await self.complete(
                system_prompt=system_prompt,
                user_text=user_text,
                model=model,
                max_tokens=max_tokens,
            )
            step = max(8, len(text) // 16 or 1)
            for i in range(0, len(text), step):
                yield text[i : i + step]
            return

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]
        kw = _completion_limit_kwargs(model, max_tokens)
        stream: Any = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            **kw,
            stream=True,
        )
        chunks: list[str] = []
        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0], "delta", None)
            if delta is None:
                continue
            content = getattr(delta, "content", None)
            if content:
                chunks.append(content)
                yield content
        assembled = "".join(chunks)
        write_llm_io_dump(
            self._settings,
            model=model,
            max_tokens=max_tokens,
            completion_kw=kw,
            system_prompt=system_prompt,
            user_text=user_text,
            raw_response=None,
            extracted_reply=assembled,
            mode="chat_completions_stream",
            stream_chunks=chunks,
        )
