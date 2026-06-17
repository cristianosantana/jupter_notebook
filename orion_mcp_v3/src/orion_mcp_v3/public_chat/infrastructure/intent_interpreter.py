"""Interpretador LLM de intenção pública."""

from __future__ import annotations

import json
import logging
from typing import Sequence

from orion_mcp_v3.public_chat.prompts import get_public_chat_prompt_registry
from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.intent_parser import parse_json_object, parse_public_intent_payload
from orion_mcp_v3.public_chat.domain.models import AncestorTurn
from orion_mcp_v3.public_chat.domain.semantic_hash import build_semantic_hash
from orion_mcp_v3.public_chat.domain.topic_resolver import resolve_topic

_LOG = logging.getLogger(__name__)
_SYSTEM_PROMPT = get_public_chat_prompt_registry().get_text("public_chat_intent.system")


class PublicIntentInterpreter:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_tokens: int = 512,
        min_confidence: float = 0.5,
    ) -> None:
        self._provider = provider
        self._max_tokens = max_tokens
        self._min_confidence = min_confidence

    async def interpret(
        self,
        message: str,
        *,
        ancestors: Sequence[AncestorTurn] = (),
    ) -> tuple[IntentContract, str, str]:
        """Retorna contrato validado, topic e semantic_hash."""
        prompt = _build_prompt(message, ancestors=ancestors)
        try:
            response = await self._provider.chat(
                [
                    ChatMessage(role="system", content=_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=prompt),
                ],
                max_tokens=self._max_tokens,
                temperature=0,
            )
        except Exception:
            _LOG.exception("public intent interpreter provider failed")
            contract = IntentContract.geral()
            topic = resolve_topic(contract)
            return contract, topic, build_semantic_hash(contract)

        payload = parse_json_object(response.text)
        contract = parse_public_intent_payload(payload, min_confidence=self._min_confidence)
        topic = resolve_topic(contract)
        semantic_hash = build_semantic_hash(contract)
        return contract, topic, semantic_hash


def _build_prompt(message: str, *, ancestors: Sequence[AncestorTurn]) -> str:
    payload = {
        "user_message": message,
        "ancestor_chain": [turn.as_prompt_dict() for turn in ancestors],
        "required_json_shape": {
            "intent": "string",
            "metric": "string|null",
            "period": "YYYY-MM|null",
            "domain": "string|null",
            "entity_filters": [
                {"dimension": "string", "value": "string", "match": "contains|exact"}
            ],
            "confidence": "number 0..1",
        },
    }
    return json.dumps(payload, ensure_ascii=False, default=str)
