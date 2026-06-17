"""Orquestração de turno consultivo — v1 cache miss only."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from orion_mcp_v3.public_chat.application.context_window import load_context_window
from orion_mcp_v3.public_chat.config.settings import PublicChatSettings
from orion_mcp_v3.public_chat.domain.knowledge import build_answer_payload
from orion_mcp_v3.public_chat.domain.knowledge_fingerprint import (
    build_knowledge_fingerprint_from_knowledge,
)
from orion_mcp_v3.public_chat.infrastructure.intent_interpreter import PublicIntentInterpreter
from orion_mcp_v3.public_chat.infrastructure.narrator import PublicNarrator
from orion_mcp_v3.public_chat.infrastructure.remissive_retriever import RemissiveRetriever
from orion_mcp_v3.public_chat.infrastructure.response_store import ResponseStore


@dataclass(frozen=True, slots=True)
class TurnResult:
    question_id: UUID
    thread_id: UUID
    parent_question_id: UUID | None
    topic: str
    semantic_hash: str
    response_id: UUID
    presentation_delivered: str
    cached: bool = False


class ConsultaTurnRunner:
    """Runner v1 — sempre percorre o caminho cache miss."""

    def __init__(
        self,
        *,
        settings: PublicChatSettings,
        store: ResponseStore,
        intent_interpreter: PublicIntentInterpreter,
        retriever: RemissiveRetriever,
        narrator: PublicNarrator,
    ) -> None:
        self._settings = settings
        self._store = store
        self._intent = intent_interpreter
        self._retriever = retriever
        self._narrator = narrator

    async def run_turn_miss_only(
        self,
        message: str,
        *,
        parent_question_id: UUID | None = None,
    ) -> AsyncIterator[str]:
        ancestors = await load_context_window(
            self._store,
            parent_question_id,
            max_depth=self._settings.context_depth,
        )
        contract, topic, semantic_hash = await self._intent.interpret(
            message,
            ancestors=ancestors,
        )
        question = await self._store.insert_question(
            query_original=message,
            topic=topic,
            intent_contract=contract,
            semantic_hash=semantic_hash,
            parent_question_id=parent_question_id,
        )

        # v1: ignora cache hit mesmo se existir
        knowledge = await self._retriever.retrieve(message)
        presentation_parts: list[str] = []
        async for delta in self._narrator.stream(message, knowledge):
            presentation_parts.append(delta)
            yield delta
        presentation = "".join(presentation_parts)

        answer_payload = build_answer_payload(knowledge)
        knowledge_fingerprint = build_knowledge_fingerprint_from_knowledge(knowledge)
        response_id = await self._store.upsert_resolution(
            topic=topic,
            semantic_hash=semantic_hash,
            answer_payload=answer_payload,
            knowledge_fingerprint=knowledge_fingerprint,
            cache_ttl_days=self._settings.cache_ttl_days,
        )
        await self._store.link_question_response(
            question_id=question.id,
            response_id=response_id,
            is_repeat=False,
            presentation_delivered=presentation,
        )

    async def run_turn_with_metadata(
        self,
        message: str,
        *,
        parent_question_id: UUID | None = None,
    ) -> tuple[TurnResult, str]:
        ancestors = await load_context_window(
            self._store,
            parent_question_id,
            max_depth=self._settings.context_depth,
        )
        contract, topic, semantic_hash = await self._intent.interpret(
            message,
            ancestors=ancestors,
        )
        question = await self._store.insert_question(
            query_original=message,
            topic=topic,
            intent_contract=contract,
            semantic_hash=semantic_hash,
            parent_question_id=parent_question_id,
        )
        knowledge = await self._retriever.retrieve(message)
        presentation = await self._narrator.render(message, knowledge)
        answer_payload = build_answer_payload(knowledge)
        knowledge_fingerprint = build_knowledge_fingerprint_from_knowledge(knowledge)
        response_id = await self._store.upsert_resolution(
            topic=topic,
            semantic_hash=semantic_hash,
            answer_payload=answer_payload,
            knowledge_fingerprint=knowledge_fingerprint,
            cache_ttl_days=self._settings.cache_ttl_days,
        )
        await self._store.link_question_response(
            question_id=question.id,
            response_id=response_id,
            is_repeat=False,
            presentation_delivered=presentation,
        )
        result = TurnResult(
            question_id=question.id,
            thread_id=question.thread_id,
            parent_question_id=question.parent_question_id,
            topic=topic,
            semantic_hash=semantic_hash,
            response_id=response_id,
            presentation_delivered=presentation,
            cached=False,
        )
        return result, presentation
