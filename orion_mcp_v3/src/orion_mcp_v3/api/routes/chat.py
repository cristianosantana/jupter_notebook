"""
Rota ``POST /api/v1/chat`` (Fase 6.1).

Fluxo: request → session → orchestrator → narrator → response.
Suporta SSE streaming quando ``request.stream=True``.
"""

from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from orion_mcp_v3.api.models import (
    ChatRequest,
    ChatResponse,
    ChatResponseMeta,
    ErrorResponse,
    UsageInfo,
)
from orion_mcp_v3.memory.episodic_retriever import EpisodicRetriever
from orion_mcp_v3.memory.semantic_retriever import SemanticRetriever
from orion_mcp_v3.protocols.llm import LLMProvider, NullLLMProvider
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.cognitive_orchestrator import CognitiveOrchestrator
from orion_mcp_v3.runtime.context_state import CognitivePhase
from orion_mcp_v3.runtime.intent_resolver import IntentResolver, map_attention_profile_to_policy
from orion_mcp_v3.runtime.narrator import CognitiveNarrator
from orion_mcp_v3.runtime.session_manager import SessionManager


def _resolve_policy(name: str) -> AttentionPolicy:
    try:
        return AttentionPolicy(name.strip().lower())
    except ValueError:
        return AttentionPolicy.BALANCED


def create_chat_router(
    *,
    session_manager: SessionManager | None = None,
    llm_provider: LLMProvider | None = None,
    narrator: CognitiveNarrator | None = None,
) -> APIRouter:
    """Factory que retorna o router de chat com dependências injectadas."""
    router = APIRouter(prefix="/api/v1", tags=["chat"])
    sm = session_manager or SessionManager()
    provider = llm_provider or NullLLMProvider()
    narr = narrator or CognitiveNarrator(provider)
    orchestrator = CognitiveOrchestrator()
    resolver = IntentResolver()

    @router.post(
        "/chat",
        response_model=ChatResponse,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    async def chat(req: ChatRequest) -> ChatResponse | StreamingResponse:
        t0 = time.monotonic()
        session = sm.get_or_create(req.conversation_id)
        policy = _resolve_policy(req.policy)

        sm.record_user_message(session, req.message)
        sm.update_phase(session, CognitivePhase.RETRIEVING)

        cognitive_plan = resolver.resolve(req.message)
        resolved_policy = map_attention_profile_to_policy(cognitive_plan.attention_profile)

        epi = EpisodicRetriever(sm.repository)
        memory_blocks = epi.retrieve(
            session.conversation_id,
            limit=sm.memory_window,
            query=req.message,
            intent_type=cognitive_plan.intent_type.value,
            entities=cognitive_plan.entities,
        )

        sm.update_phase(session, CognitivePhase.FUSING)

        orch_result = orchestrator.finalize_prompt(
            req.message,
            policy=resolved_policy,
            cognitive_plan=cognitive_plan,
            memory_blocks=memory_blocks,
            max_tokens=req.max_tokens,
        )

        sm.update_phase(session, CognitivePhase.NARRATING)

        if req.stream:
            return _sse_response(narr, orch_result, session, sm, t0, cognitive_plan)

        narration = await narr.narrate(orch_result)
        elapsed = (time.monotonic() - t0) * 1000.0

        sm.record_assistant_message(session, narration.narration)
        sm.update_phase(session, CognitivePhase.IDLE)

        usage = narration.llm_response.meta.usage
        meta = ChatResponseMeta(
            conversation_id=session.conversation_id,
            model=narration.llm_response.meta.model,
            finish_reason=narration.llm_response.meta.finish_reason,
            latency_ms=elapsed,
            usage=UsageInfo(
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
            ),
            safeguards=list(narration.safeguards_applied),
            cognitive_intent=cognitive_plan.intent_type.value,
            coverage_note=narration.coverage_note,
        )
        return ChatResponse(reply=narration.narration, meta=meta)

    def _sse_response(narr, orch_result, session, sm, t0, cognitive_plan):
        async def event_generator():
            full_text: list[str] = []
            try:
                async for chunk in narr.narrate_stream(orch_result):
                    full_text.append(chunk.delta)
                    payload = json.dumps({"delta": chunk.delta, "finish_reason": chunk.finish_reason})
                    yield f"data: {payload}\n\n"
            finally:
                text = "".join(full_text)
                sm.record_assistant_message(session, text)
                sm.update_phase(session, CognitivePhase.IDLE)
                elapsed = (time.monotonic() - t0) * 1000.0
                done = json.dumps({
                    "done": True,
                    "conversation_id": session.conversation_id,
                    "latency_ms": round(elapsed, 2),
                    "cognitive_intent": cognitive_plan.intent_type.value,
                })
                yield f"data: {done}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
