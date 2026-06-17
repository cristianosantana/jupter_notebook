"""Narrador do Chat Público — apresenta conhecimento recuperado."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider, LLMStreamChunk
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado
from orion_mcp_v3.public_chat.prompts import get_public_chat_prompt_registry

_NO_HITS_MESSAGE = "Não encontrei informações validadas sobre isso."
_SYSTEM_PROMPT = get_public_chat_prompt_registry().get_text("public_chat_narrator.system")


class PublicNarrator:
    def __init__(self, provider: LLMProvider, *, max_tokens: int = 1024) -> None:
        self._provider = provider
        self._max_tokens = max_tokens

    async def stream(
        self,
        message: str,
        knowledge: ConhecimentoRecuperado,
    ) -> AsyncIterator[str]:
        if not knowledge.has_hits:
            yield _NO_HITS_MESSAGE
            return

        prompt = json.dumps(
            {
                "user_message": message,
                "knowledge": knowledge.as_prompt_dict(),
            },
            ensure_ascii=False,
            default=str,
        )
        messages = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ]
        async for chunk in self._provider.stream(messages, max_tokens=self._max_tokens, temperature=0):
            if chunk.delta:
                yield chunk.delta

    async def render(
        self,
        message: str,
        knowledge: ConhecimentoRecuperado,
    ) -> str:
        parts: list[str] = []
        async for delta in self.stream(message, knowledge):
            parts.append(delta)
        return "".join(parts) if parts else _NO_HITS_MESSAGE
