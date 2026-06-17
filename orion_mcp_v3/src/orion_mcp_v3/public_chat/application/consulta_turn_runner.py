"""Orquestração de turno consultivo — v2 cache hit + miss."""

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
from orion_mcp_v3.public_chat.infrastructure.response_store import CachedResolution, ResponseStore


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


@dataclass(frozen=True, slots=True)
class TurnStreamChunk:
    delta: str = ""
    result: TurnResult | None = None


class ConsultaTurnRunner:
    """Runner v2 — cache hit (reload + re-narrar) e miss (retrieve + narrar)."""

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

    async def run_turn(
        self,
        message: str,
        *,
        parent_question_id: UUID | None = None,
    ) -> AsyncIterator[TurnStreamChunk]:
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

        cached = await self._store.find_resolution(topic, semantic_hash)
        if cached is not None:
            async for chunk in self._run_cache_hit(
                message=message,
                question_id=question.id,
                thread_id=question.thread_id,
                parent_question_id=question.parent_question_id,
                topic=topic,
                semantic_hash=semantic_hash,
                cached=cached,
            ):
                yield chunk
            return

        async for chunk in self._run_cache_miss(
            message=message,
            question_id=question.id,
            thread_id=question.thread_id,
            parent_question_id=question.parent_question_id,
            topic=topic,
            semantic_hash=semantic_hash,
        ):
            yield chunk

    async def run_turn_miss_only(
        self,
        message: str,
        *,
        parent_question_id: UUID | None = None,
    ) -> AsyncIterator[str]:
        """v1 — ignora cache hit (compatibilidade phase2)."""
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

        async for chunk in self._run_cache_miss(
            message=message,
            question_id=question.id,
            thread_id=question.thread_id,
            parent_question_id=question.parent_question_id,
            topic=topic,
            semantic_hash=semantic_hash,
        ):
            if chunk.delta:
                yield chunk.delta

    async def run_turn_with_metadata(
        self,
        message: str,
        *,
        parent_question_id: UUID | None = None,
    ) -> tuple[TurnResult, str]:
        result: TurnResult | None = None
        parts: list[str] = []
        async for chunk in self.run_turn(message, parent_question_id=parent_question_id):
            if chunk.delta:
                parts.append(chunk.delta)
            if chunk.result is not None:
                result = chunk.result
        if result is None:
            raise RuntimeError("run_turn finished without TurnResult")
        return result, "".join(parts)

    async def _run_cache_hit(
        self,
        *,
        message: str,
        question_id: UUID,
        thread_id: UUID,
        parent_question_id: UUID | None,
        topic: str,
        semantic_hash: str,
        cached: CachedResolution,
    ) -> AsyncIterator[TurnStreamChunk]:
        knowledge = await self._retriever.reload_from_payload(cached.answer_payload)
        new_fingerprint = build_knowledge_fingerprint_from_knowledge(knowledge)
        fingerprint_stale = new_fingerprint != cached.knowledge_fingerprint
        response_id = cached.id
        snapshot: str | None = cached.presentation_snapshot

        if fingerprint_stale:
            answer_payload = build_answer_payload(knowledge)
            response_id = await self._store.upsert_resolution(
                topic=topic,
                semantic_hash=semantic_hash,
                answer_payload=answer_payload,
                knowledge_fingerprint=new_fingerprint,
                cache_ttl_days=self._settings.cache_ttl_days,
                presentation_snapshot=None,
            )
            snapshot = None

        use_snapshot = (
            not fingerprint_stale
            and self._settings.use_presentation_snapshot
            and bool(snapshot)
        )

        if use_snapshot:
            presentation = snapshot or ""
            if presentation:
                yield TurnStreamChunk(delta=presentation)
        else:
            presentation_parts: list[str] = []
            async for delta in self._narrator.stream(message, knowledge):
                presentation_parts.append(delta)
                yield TurnStreamChunk(delta=delta)
            presentation = "".join(presentation_parts)
            if self._settings.use_presentation_snapshot and presentation:
                await self._store.upsert_resolution(
                    topic=topic,
                    semantic_hash=semantic_hash,
                    answer_payload=cached.answer_payload,
                    knowledge_fingerprint=new_fingerprint,
                    cache_ttl_days=self._settings.cache_ttl_days,
                    presentation_snapshot=presentation,
                )

        await self._store.link_question_response(
            question_id=question_id,
            response_id=response_id,
            is_repeat=True,
            presentation_delivered=presentation,
        )
        yield TurnStreamChunk(
            result=TurnResult(
                question_id=question_id,
                thread_id=thread_id,
                parent_question_id=parent_question_id,
                topic=topic,
                semantic_hash=semantic_hash,
                response_id=response_id,
                presentation_delivered=presentation,
                cached=True,
            )
        )

    async def _run_cache_miss(
        self,
        *,
        message: str,
        question_id: UUID,
        thread_id: UUID,
        parent_question_id: UUID | None,
        topic: str,
        semantic_hash: str,
    ) -> AsyncIterator[TurnStreamChunk]:
        knowledge = await self._retriever.retrieve(message)
        presentation_parts: list[str] = []
        async for delta in self._narrator.stream(message, knowledge):
            presentation_parts.append(delta)
            yield TurnStreamChunk(delta=delta)
        presentation = "".join(presentation_parts)

        answer_payload = build_answer_payload(knowledge)
        knowledge_fingerprint = build_knowledge_fingerprint_from_knowledge(knowledge)
        snapshot = presentation if self._settings.use_presentation_snapshot else None
        response_id = await self._store.upsert_resolution(
            topic=topic,
            semantic_hash=semantic_hash,
            answer_payload=answer_payload,
            knowledge_fingerprint=knowledge_fingerprint,
            cache_ttl_days=self._settings.cache_ttl_days,
            presentation_snapshot=snapshot,
        )
        await self._store.link_question_response(
            question_id=question_id,
            response_id=response_id,
            is_repeat=False,
            presentation_delivered=presentation,
        )
        yield TurnStreamChunk(
            result=TurnResult(
                question_id=question_id,
                thread_id=thread_id,
                parent_question_id=parent_question_id,
                topic=topic,
                semantic_hash=semantic_hash,
                response_id=response_id,
                presentation_delivered=presentation,
                cached=False,
            )
        )
