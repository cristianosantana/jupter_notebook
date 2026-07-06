"""Interpretador LLM de intenção pública."""

from __future__ import annotations

import json
import time
from typing import Sequence
from uuid import UUID

from orion_mcp_v3.public_chat.prompts import get_public_chat_prompt_registry
from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.intent_heuristics import extract_heuristic_signals
from orion_mcp_v3.public_chat.domain.intent_parser import parse_json_object, parse_public_intent_payload
from orion_mcp_v3.public_chat.domain.models import AncestorTurn
from orion_mcp_v3.public_chat.domain.semantic_hash import build_semantic_hash
from orion_mcp_v3.public_chat.domain.topic_resolver import resolve_topic
from orion_mcp_v3.public_chat.infrastructure.pipeline_snapshots import snapshot_intent
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event, preview_message
from orion_mcp_v3.public_chat.infrastructure.response_store import ResponseStore

_SYSTEM_PROMPT = get_public_chat_prompt_registry().get_text("public_chat_intent.system")


class PublicIntentInterpreter:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        max_tokens: int = 512,
        min_confidence: float = 0.5,
        store: ResponseStore | None = None,
        use_intent_cache: bool = False,
    ) -> None:
        self._provider = provider
        self._max_tokens = max_tokens
        self._min_confidence = min_confidence
        self._store = store
        self._use_intent_cache = use_intent_cache

    async def interpret(
        self,
        message: str,
        *,
        ancestors: Sequence[AncestorTurn] = (),
        parent_question_id: UUID | None = None,
    ) -> tuple[IntentContract, str, str]:
        """Retorna contrato validado, topic e semantic_hash."""
        t0 = time.monotonic()
        log_public_chat_event(
            etapa="intent.interpret",
            fase="pre",
            dados={**preview_message(message), "ancestor_count": len(ancestors)},
        )

        if self._use_intent_cache and self._store is not None:
            cached = await self._store.find_cached_intent(
                message,
                parent_question_id=parent_question_id,
            )
            if cached is not None:
                log_public_chat_event(
                    etapa="intent.cache_hit",
                    fase="post",
                    dados={
                        "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                        "intent": cached.intent_contract.intent,
                        "topic": cached.topic,
                        "semantic_hash": cached.semantic_hash,
                        "confidence": cached.intent_contract.confidence,
                        "contract": snapshot_intent(cached.intent_contract),
                    },
                )
                return cached.intent_contract, cached.topic, cached.semantic_hash

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
        except Exception as exc:
            log_public_chat_event(
                etapa="intent.interpret",
                fase="error",
                dados={"reason": type(exc).__name__, "detail": str(exc), "fallback": "geral"},
            )
            contract = IntentContract.geral()
            topic = resolve_topic(contract)
            semantic_hash = build_semantic_hash(contract)
            log_public_chat_event(
                etapa="intent.interpret",
                fase="post",
                dados={
                    "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                    "intent": contract.intent,
                    "topic": topic,
                    "semantic_hash": semantic_hash,
                    "confidence": contract.confidence,
                    "fallback": True,
                    "contract": snapshot_intent(contract),
                },
            )
            return contract, topic, semantic_hash

        payload = parse_json_object(response.text)
        contract = parse_public_intent_payload(
            payload,
            min_confidence=self._min_confidence,
            message=message,
        )
        topic = resolve_topic(contract)
        semantic_hash = build_semantic_hash(contract)
        log_public_chat_event(
            etapa="intent.interpret",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "intent": contract.intent,
                "topic": topic,
                "semantic_hash": semantic_hash,
                "confidence": contract.confidence,
                "fallback": False,
                "cache_hit": False,
                "contract": snapshot_intent(contract),
            },
        )
        return contract, topic, semantic_hash


def _build_prompt(message: str, *, ancestors: Sequence[AncestorTurn]) -> str:
    payload = {
        "user_message": message,
        "ancestor_chain": [turn.as_prompt_dict() for turn in ancestors],
        "heuristic_signals": extract_heuristic_signals(message),
        "required_json_shape": {
            "intent": "string",
            "metric": "string|null",
            "period": "YYYY-MM|null",
            "domain": "string|null",
            "operation": "ranking_asc|ranking_desc|list|summary|comparison|null",
            "dimension": "string|null",
            "sort_direction": "asc|desc|null",
            "entity_filters": [
                {"dimension": "string", "value": "string", "match": "contains|exact"}
            ],
            "confidence": "number 0..1",
        },
    }
    return json.dumps(payload, ensure_ascii=False, default=str)
