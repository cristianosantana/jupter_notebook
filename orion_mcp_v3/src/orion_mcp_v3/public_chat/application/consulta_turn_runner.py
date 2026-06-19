"""Orquestração de turno consultivo — v2 cache hit + miss."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from orion_mcp_v3.public_chat.application.context_pipeline import prepare_selected_context
from orion_mcp_v3.public_chat.application.context_window import load_context_window
from orion_mcp_v3.public_chat.application.workspace_pipeline import build_remissive_workspace
from orion_mcp_v3.public_chat.config.settings import PublicChatSettings
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, build_answer_payload
from orion_mcp_v3.public_chat.domain.knowledge_fingerprint import (
    build_knowledge_fingerprint_from_knowledge,
)
from orion_mcp_v3.public_chat.infrastructure.analytical_narrator import AnalyticalNarrator
from orion_mcp_v3.public_chat.infrastructure.context_selector import PublicContextSelector
from orion_mcp_v3.public_chat.infrastructure.intent_interpreter import PublicIntentInterpreter
from orion_mcp_v3.public_chat.infrastructure.memory_resolver import MemoryResolver
from orion_mcp_v3.public_chat.infrastructure.narrator import PublicNarrator
from orion_mcp_v3.public_chat.infrastructure.pipeline_snapshots import (
    log_cache_resolution,
    log_cache_stored,
    log_qa_turn_summary,
    snapshot_intent,
)
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import (
    log_public_chat_event,
    preview_message,
)
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
        context_selector: PublicContextSelector,
        fact_planner: FactPlanner | None = None,
        memory_resolver: MemoryResolver | None = None,
        analytical_narrator: AnalyticalNarrator | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._intent = intent_interpreter
        self._retriever = retriever
        self._narrator = narrator
        self._context_selector = context_selector
        self._fact_planner = fact_planner
        self._memory_resolver = memory_resolver
        self._analytical_narrator = analytical_narrator

    async def run_turn(
        self,
        message: str,
        *,
        parent_question_id: UUID | None = None,
    ) -> AsyncIterator[TurnStreamChunk]:
        t0 = time.monotonic()
        log_public_chat_event(
            etapa="runner.turn",
            fase="pre",
            dados={
                **preview_message(message),
                "parent_question_id": str(parent_question_id) if parent_question_id else None,
            },
        )

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

        log_public_chat_event(
            etapa="runner.intent_persisted",
            fase="post",
            dados={
                "question_id": str(question.id),
                "thread_id": str(question.thread_id),
                "topic": topic,
                "semantic_hash": semantic_hash,
                "intent": contract.intent,
                "confidence": contract.confidence,
                "ancestor_count": len(ancestors),
                "contract": snapshot_intent(contract),
                **preview_message(message),
            },
        )

        cached = await self._store.find_resolution(topic, semantic_hash)
        log_cache_resolution(
            cache_hit=cached is not None,
            topic=topic,
            semantic_hash=semantic_hash,
            cached=cached,
        )
        if cached is not None:
            async for chunk in self._run_cache_hit(
                message=message,
                question_id=question.id,
                thread_id=question.thread_id,
                parent_question_id=question.parent_question_id,
                topic=topic,
                semantic_hash=semantic_hash,
                cached=cached,
                contract=contract,
            ):
                yield chunk
            log_public_chat_event(
                etapa="runner.turn",
                fase="post",
                dados={
                    "path": "cache_hit",
                    "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                    "question_id": str(question.id),
                },
            )
            return

        async for chunk in self._run_cache_miss(
            message=message,
            question_id=question.id,
            thread_id=question.thread_id,
            parent_question_id=question.parent_question_id,
            topic=topic,
            semantic_hash=semantic_hash,
            contract=contract,
        ):
            yield chunk
        log_public_chat_event(
            etapa="runner.turn",
            fase="post",
            dados={
                "path": "cache_miss",
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "question_id": str(question.id),
            },
        )

    async def run_turn_miss_only(
        self,
        message: str,
        *,
        parent_question_id: UUID | None = None,
    ) -> AsyncIterator[str]:
        """v1 — ignora cache hit (compatibilidade phase2)."""
        log_public_chat_event(
            etapa="runner.turn_miss_only",
            fase="pre",
            dados=preview_message(message),
        )
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
            contract=contract,
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
        contract: IntentContract,
    ) -> AsyncIterator[TurnStreamChunk]:
        t0 = time.monotonic()
        log_public_chat_event(
            etapa="runner.cache_hit",
            fase="pre",
            dados={"response_id": str(cached.id), "topic": topic},
        )

        knowledge = await self._retriever.reload_from_payload(cached.answer_payload)
        new_fingerprint = build_knowledge_fingerprint_from_knowledge(knowledge)
        fingerprint_stale = new_fingerprint != cached.knowledge_fingerprint
        response_id = cached.id
        snapshot: str | None = cached.presentation_snapshot

        if fingerprint_stale:
            log_public_chat_event(
                etapa="runner.fingerprint_stale",
                fase="post",
                dados={
                    "old_fingerprint": cached.knowledge_fingerprint,
                    "new_fingerprint": new_fingerprint,
                },
            )
            answer_payload = build_answer_payload(knowledge)
            response_id = await self._store.upsert_resolution(
                topic=topic,
                semantic_hash=semantic_hash,
                answer_payload=answer_payload,
                knowledge_fingerprint=new_fingerprint,
                cache_ttl_days=self._settings.cache_ttl_days,
                presentation_snapshot=None,
            )

        use_snapshot = (
            not fingerprint_stale
            and self._settings.use_presentation_snapshot
            and bool(snapshot)
        )

        if use_snapshot:
            log_public_chat_event(
                etapa="runner.presentation_snapshot",
                fase="post",
                dados={"used": True, "snapshot_chars": len(snapshot or "")},
            )
            presentation = snapshot or ""
            if presentation:
                yield TurnStreamChunk(delta=presentation)
        else:
            presentation_parts: list[str] = []
            async for delta in self._stream_presentation(
                message,
                contract=contract,
                knowledge=knowledge,
            ):
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
        log_public_chat_event(
            etapa="runner.cache_hit",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "fingerprint_stale": fingerprint_stale,
                "used_snapshot": use_snapshot,
                "presentation_chars": len(presentation),
                "is_repeat": True,
            },
        )
        answer_payload = build_answer_payload(knowledge)
        log_qa_turn_summary(
            pergunta=message,
            resposta=presentation,
            question_id=str(question_id),
            thread_id=str(thread_id),
            response_id=str(response_id),
            cached=True,
            cache_path="cache_hit",
            topic=topic,
            semantic_hash=semantic_hash,
            intent=contract.intent,
            confidence=contract.confidence,
            is_repeat=True,
            knowledge=knowledge,
            answer_payload=answer_payload,
            cache_resolution=cached,
            fingerprint_stale=fingerprint_stale,
            used_presentation_snapshot=use_snapshot,
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
        contract: IntentContract,
    ) -> AsyncIterator[TurnStreamChunk]:
        t0 = time.monotonic()
        log_public_chat_event(
            etapa="runner.cache_miss",
            fase="pre",
            dados={"topic": topic, "semantic_hash": semantic_hash},
        )

        knowledge = await self._retriever.retrieve(message)
        presentation_parts: list[str] = []
        async for delta in self._stream_presentation(
            message,
            contract=contract,
            knowledge=knowledge,
        ):
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
        log_cache_stored(
            response_id=str(response_id),
            topic=topic,
            semantic_hash=semantic_hash,
            answer_payload=answer_payload,
            knowledge_fingerprint=knowledge_fingerprint,
            is_repeat=False,
            presentation_chars=len(presentation),
            stored_snapshot=snapshot is not None,
        )
        log_public_chat_event(
            etapa="runner.cache_miss",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "response_id": str(response_id),
                "knowledge_fingerprint": knowledge_fingerprint,
                "presentation_chars": len(presentation),
                "is_repeat": False,
            },
        )
        log_qa_turn_summary(
            pergunta=message,
            resposta=presentation,
            question_id=str(question_id),
            thread_id=str(thread_id),
            response_id=str(response_id),
            cached=False,
            cache_path="cache_miss",
            topic=topic,
            semantic_hash=semantic_hash,
            intent=contract.intent,
            confidence=contract.confidence,
            is_repeat=False,
            knowledge=knowledge,
            answer_payload=answer_payload,
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

    def _use_workspace(self) -> bool:
        return (
            self._settings.use_workspace
            and self._fact_planner is not None
            and self._memory_resolver is not None
            and self._analytical_narrator is not None
        )

    async def _stream_presentation(
        self,
        message: str,
        *,
        contract: IntentContract,
        knowledge: ConhecimentoRecuperado,
    ) -> AsyncIterator[str]:
        if self._use_workspace():
            assert self._fact_planner is not None
            assert self._memory_resolver is not None
            assert self._analytical_narrator is not None
            workspace = await build_remissive_workspace(
                message,
                contract=contract,
                knowledge=knowledge,
                planner=self._fact_planner,
                resolver=self._memory_resolver,
            )
            async for delta in self._analytical_narrator.stream(
                message,
                contract=contract,
                workspace=workspace,
            ):
                yield delta
            return

        selected = await prepare_selected_context(
            message,
            contract=contract,
            knowledge=knowledge,
            selector=self._context_selector,
        )
        async for delta in self._narrator.stream(message, contract=contract, selected=selected):
            yield delta
