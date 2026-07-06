"""Narrador analítico — resposta a partir do RemissiveWorkspace."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator

from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider
from orion_mcp_v3.public_chat.domain.fact_engine.models import RemissiveWorkspace
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event, preview_message
from orion_mcp_v3.public_chat.prompts import get_public_chat_prompt_registry

NO_FACTS_FALLBACK_MESSAGE = "Não encontrei fatos validados suficientes para responder."


def is_no_facts_fallback(presentation: str) -> bool:
    return presentation.strip() == NO_FACTS_FALLBACK_MESSAGE
_SYSTEM_PROMPT = get_public_chat_prompt_registry().get_text("public_chat_analytical_narrator.system")


class AnalyticalNarrator:
    def __init__(self, provider: LLMProvider, *, max_tokens: int = 1024) -> None:
        self._provider = provider
        self._max_tokens = max_tokens

    async def stream(
        self,
        message: str,
        *,
        contract: IntentContract,
        workspace: RemissiveWorkspace,
    ) -> AsyncIterator[str]:
        t0 = time.monotonic()
        facts_payload = workspace.as_prompt_dict()
        log_public_chat_event(
            etapa="narrator.analytical.stream",
            fase="pre",
            dados={
                **preview_message(message),
                "fact_count": len(workspace.facts),
                "gap_count": len(workspace.gaps),
                "workspace_confidence": workspace.workspace_confidence,
            },
        )
        if not workspace.has_facts:
            log_public_chat_event(
                etapa="narrator.analytical.stream",
                fase="post",
                dados={
                    "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                    "no_facts_fallback": True,
                    "presentation_chars": len(NO_FACTS_FALLBACK_MESSAGE),
                },
            )
            yield NO_FACTS_FALLBACK_MESSAGE
            return

        prompt = json.dumps(
            {
                "user_message": message,
                "intent_contract": contract.as_mapping(),
                "workspace": facts_payload,
                "allowed_derivations": ["participacao = oficina / total"],
            },
            ensure_ascii=False,
            default=str,
        )
        messages = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT),
            ChatMessage(role="user", content=prompt),
        ]
        parts: list[str] = []
        async for chunk in self._provider.stream(messages, max_tokens=self._max_tokens, temperature=0):
            if chunk.delta:
                parts.append(chunk.delta)
                yield chunk.delta
        log_public_chat_event(
            etapa="narrator.analytical.stream",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "presentation_chars": len("".join(parts)),
                "fact_count": len(workspace.facts),
            },
        )

    async def render(
        self,
        message: str,
        *,
        contract: IntentContract,
        workspace: RemissiveWorkspace,
    ) -> str:
        parts: list[str] = []
        async for delta in self.stream(message, contract=contract, workspace=workspace):
            parts.append(delta)
        return "".join(parts) if parts else NO_FACTS_FALLBACK_MESSAGE
