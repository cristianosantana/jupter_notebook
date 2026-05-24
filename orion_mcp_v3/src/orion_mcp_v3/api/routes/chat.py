"""
Rota ``POST /api/v1/chat`` (Fase 6.1).

Fluxo: request → session → orchestrator → narrator → response.
Suporta SSE streaming quando ``request.stream=True``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from orion_mcp_v3.api.models import (
    ChatOptionsResponse,
    ChatRequest,
    ChatResponse,
    ChatResponseMeta,
    ErrorResponse,
    SessionListItem,
    SessionListResponse,
    UsageInfo,
)
from orion_mcp_v3.broker.executor import AnalyticsExecutor
from orion_mcp_v3.broker.sql_compiler import SqlAllowlist
from orion_mcp_v3.memory.episodic_retriever import EpisodicRetriever
from orion_mcp_v3.memory.chat_turn_embedding_store import ChatTurnEmbeddingStore
from orion_mcp_v3.memory.retrieval_pipeline import MemoryRetrievalPipeline
from orion_mcp_v3.memory.semantic_retriever import SemanticRetriever
from orion_mcp_v3.memory.vector_retriever import VectorRetriever
from orion_mcp_v3.protocols.llm import LLMProvider, NullLLMProvider
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.cognitive_orchestrator import CognitiveOrchestrator
from orion_mcp_v3.runtime.context_state import CognitivePhase
from orion_mcp_v3.config.settings import get_settings
from orion_mcp_v3.runtime.analytics_pipeline_trace import (
    log_pipeline_event,
    snapshot_analytics_result,
    snapshot_cognitive_plan,
    snapshot_evidence_block,
    snapshot_orchestration,
    snapshot_semantic_plan,
)
from orion_mcp_v3.runtime.analytical_context_policy import AnalyticalContextIsolationPolicy
from orion_mcp_v3.runtime.analytical_signature import signature_from_evidence, signature_from_plan
from orion_mcp_v3.runtime.intent_resolver import IntentResolver, map_attention_profile_to_policy
from orion_mcp_v3.runtime.narrator import CognitiveNarrator
from orion_mcp_v3.runtime.session_manager import SessionManager

_LOG = logging.getLogger("orion.api.chat")


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
    analytics_executor: AnalyticsExecutor | None = None,
    analytics_allowlist: SqlAllowlist | None = None,
    analytics_state: dict | None = None,
) -> APIRouter:
    """Factory que retorna o router de chat com dependências injectadas."""
    router = APIRouter(prefix="/api/v1", tags=["chat"])
    sm = session_manager or SessionManager()
    provider = llm_provider or NullLLMProvider()
    narr = narrator or CognitiveNarrator(provider)
    orchestrator = CognitiveOrchestrator()
    resolver = IntentResolver()
    context_policy = AnalyticalContextIsolationPolicy()
    _fixed_executor = analytics_executor
    _fixed_allowlist = analytics_allowlist
    # Não usar ``analytics_state or {}``: um dict vazio é falsy e seria substituído
    # por um novo {}, quebrando o partilhamento com o lifespan (executor nunca visto).
    _state: dict = analytics_state if analytics_state is not None else {}

    @router.get("/sessions", response_model=SessionListResponse)
    async def sessions_list() -> SessionListResponse:
        rows = await sm.list_session_summaries()
        return SessionListResponse(sessions=[SessionListItem(**r) for r in rows])

    @router.get("/chat/options", response_model=ChatOptionsResponse)
    async def chat_options() -> ChatOptionsResponse:
        """Políticas (:class:`~AttentionPolicy`) e limites alinhados a :class:`~ChatRequest`."""
        settings = get_settings()
        tmin, tmax = 64, 32000
        raw_presets = (2048, 4096, 8192, 16384, 20000, 32000)
        presets = sorted({p for p in raw_presets if tmin <= p <= tmax})
        def_mx = min(max(int(settings.max_tokens), tmin), tmax)
        policies = [p.value for p in AttentionPolicy]
        dp = (settings.default_policy or "analytical").strip().lower()
        if dp not in policies:
            dp = AttentionPolicy.BALANCED.value
        return ChatOptionsResponse(
            policies=policies,
            max_tokens_min=tmin,
            max_tokens_max=tmax,
            max_tokens_presets=presets,
            default_max_tokens=def_mx,
            default_policy=dp,
        )

    @router.post(
        "/chat",
        response_model=ChatResponse,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    async def chat(req: ChatRequest) -> ChatResponse | StreamingResponse:
        t0 = time.monotonic()
        conv_id = req.conversation_id
        if conv_id is not None and isinstance(conv_id, str) and not conv_id.strip():
            conv_id = None
        session = sm.get_or_create(conv_id)
        policy = _resolve_policy(req.policy)

        await sm.record_user_message(session, req.message)
        sm.update_phase(session, CognitivePhase.RETRIEVING)

        trace_pipe = get_settings().analytics_pipeline_trace
        cid = session.conversation_id
        if trace_pipe:
            log_pipeline_event(
                etapa="intent_resolve",
                fase="pre",
                conversation_id=cid,
                dados={
                    "message_chars": len(req.message or ""),
                    "message_preview": (req.message or "")[:240],
                    "policy_request": req.policy,
                    "max_tokens": req.max_tokens,
                },
            )

        cognitive_plan = resolver.resolve(req.message, policy_request=req.policy)
        resolved_policy = map_attention_profile_to_policy(cognitive_plan.attention_profile)
        context_decision = context_policy.decide(cognitive_plan)

        if trace_pipe:
            log_pipeline_event(
                etapa="intent_resolve",
                fase="post",
                conversation_id=cid,
                dados={"cognitive_plan": snapshot_cognitive_plan(cognitive_plan), "resolved_policy": resolved_policy.value},
            )

        if trace_pipe:
            log_pipeline_event(
                etapa="memory_retrieve",
                fase="pre",
                conversation_id=cid,
                dados={"memory_window": sm.memory_window, "intent_type": cognitive_plan.intent_type.value},
            )

        settings = get_settings()
        memory_pipeline = MemoryRetrievalPipeline(sm.repository)
        epi = EpisodicRetriever(sm.repository)
        sem = SemanticRetriever(sm.repository)
        vec_ret: VectorRetriever | None = None
        embed_store = _state.get("chat_turn_embedding_store")
        if (
            settings.embedding_should_retrieve
            and embed_store is not None
            and isinstance(embed_store, ChatTurnEmbeddingStore)
            and context_decision.allow_vector_memory
        ):
            vec_ret = VectorRetriever(embed_store)
        memory_blocks = await memory_pipeline.collect_blocks(
            session.conversation_id,
            recent_limit=sm.memory_window,
            semantic_query=req.message,
            semantic_retriever=sem,
            vector_retriever=vec_ret,
            vector_top_k=settings.embedding_top_k,
            episodic_retriever=epi,
            intent_type=cognitive_plan.intent_type.value,
            entities=cognitive_plan.entities,
        )

        if trace_pipe:
            vector_n = sum(1 for b in memory_blocks if b.metadata.get("retrieval") == "vector")
            lexical_n = sum(1 for b in memory_blocks if b.metadata.get("retrieval") == "semantic_lexical")
            log_pipeline_event(
                etapa="memory_retrieve",
                fase="post",
                conversation_id=cid,
                dados={
                    "memory_block_count": len(memory_blocks),
                    "memory_layer_vector": vector_n,
                    "memory_layer_lexical": lexical_n,
                    "embedding_mode": settings.effective_embedding_mode,
                },
            )

        evidence = None
        exec_ = _fixed_executor or _state.get("executor")
        al = _fixed_allowlist or _state.get("allowlist")
        if trace_pipe:
            log_pipeline_event(
                etapa="analytics_guard",
                fase="pre",
                conversation_id=cid,
                dados={
                    "needs_analytics": cognitive_plan.needs_analytics,
                    "executor_present": exec_ is not None,
                    "executor_type": type(exec_).__name__ if exec_ is not None else None,
                    "allowlist_present": al is not None,
                },
            )

        if cognitive_plan.needs_analytics and exec_ is not None and al is not None:
            _LOG.info("analytics pipeline triggered (executor=%s)", type(exec_).__name__)
            if trace_pipe:
                log_pipeline_event(
                    etapa="analytics_guard",
                    fase="post",
                    conversation_id=cid,
                    dados={"executado": True},
                )
            evidence = await _run_analytics(
                exec_, al, cognitive_plan, req.message, trace_enabled=trace_pipe, conversation_id=cid,
            )
        elif trace_pipe:
            parts: list[str] = []
            if not cognitive_plan.needs_analytics:
                parts.append("needs_analytics=false")
            if exec_ is None:
                parts.append("executor_ausente")
            if al is None:
                parts.append("allowlist_ausente")
            log_pipeline_event(
                etapa="analytics_guard",
                fase="post",
                conversation_id=cid,
                dados={"executado": False, "motivo": ",".join(parts)},
            )

        current_signature = (
            signature_from_evidence(evidence, fallback=cognitive_plan)
            if evidence is not None
            else signature_from_plan(cognitive_plan)
        )
        isolation = context_policy.filter_with_trace(
            memory_blocks,
            cognitive_plan,
            signature=current_signature,
        )
        memory_blocks = list(isolation.kept_blocks)
        if trace_pipe:
            log_pipeline_event(
                etapa="context_isolation",
                fase="post",
                conversation_id=cid,
                dados={
                    **isolation.as_trace(context_decision),
                    "signature": current_signature.as_dict(),
                },
            )

        sm.update_phase(session, CognitivePhase.FUSING)

        if trace_pipe:
            log_pipeline_event(
                etapa="cognitive_orchestrate",
                fase="pre",
                conversation_id=cid,
                dados={
                    "evidence_before_pack": snapshot_evidence_block(evidence),
                    "memory_block_count": len(memory_blocks),
                },
            )

        orch_result = orchestrator.finalize_prompt(
            req.message,
            policy=resolved_policy,
            cognitive_plan=cognitive_plan,
            evidence=evidence,
            memory_blocks=memory_blocks,
            max_tokens=req.max_tokens,
        )

        if trace_pipe:
            log_pipeline_event(
                etapa="cognitive_orchestrate",
                fase="post",
                conversation_id=cid,
                dados=snapshot_orchestration(orch_result),
            )

        sm.update_phase(session, CognitivePhase.NARRATING)

        if req.stream:
            return _sse_response(narr, orch_result, session, sm, t0, cognitive_plan, trace_pipe=trace_pipe)

        if trace_pipe:
            log_pipeline_event(
                etapa="narrate",
                fase="pre",
                conversation_id=cid,
                dados={"orch_prompt_chars": len(orch_result.prompt_text or "")},
            )

        narration = await narr.narrate(orch_result)

        if trace_pipe:
            log_pipeline_event(
                etapa="narrate",
                fase="post",
                conversation_id=cid,
                dados={
                    "reply_chars": len(narration.narration or ""),
                    "safeguards": list(narration.safeguards_applied),
                    "coverage_note_chars": len(narration.coverage_note or ""),
                },
            )
        elapsed = (time.monotonic() - t0) * 1000.0

        await sm.record_assistant_message(session, narration.narration)
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

    def _sse_response(narr, orch_result, session, sm, t0, cognitive_plan, *, trace_pipe: bool = False):
        cid = session.conversation_id

        async def event_generator():
            full_text: list[str] = []
            try:
                if trace_pipe:
                    log_pipeline_event(
                        etapa="narrate_stream",
                        fase="pre",
                        conversation_id=cid,
                        dados={"orch_prompt_chars": len(orch_result.prompt_text or "")},
                    )
                async for chunk in narr.narrate_stream(orch_result):
                    full_text.append(chunk.delta)
                    payload = json.dumps({"delta": chunk.delta, "finish_reason": chunk.finish_reason})
                    yield f"data: {payload}\n\n"
            finally:
                text = "".join(full_text)
                await sm.record_assistant_message(session, text)
                sm.update_phase(session, CognitivePhase.IDLE)
                if trace_pipe:
                    log_pipeline_event(
                        etapa="narrate_stream",
                        fase="post",
                        conversation_id=cid,
                        dados={"reply_chars": len(text), "stream": True},
                    )
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

    async def _run_analytics(
        exec_: AnalyticsExecutor,
        al: SqlAllowlist,
        cognitive_plan: Any,
        message: str,
        *,
        trace_enabled: bool = False,
        conversation_id: str | None = None,
    ) -> Any:
        from orion_mcp_v3.broker import (
            ANALYTICS_TEMPLATES,
            AnalyticsResult,
            EvidenceAggregator,
            QueryExpander,
        )
        from orion_mcp_v3.broker.answer_projector import build_projected_answer
        from orion_mcp_v3.broker.evidence_series_resolve import resolve_evidence_series_specs
        from orion_mcp_v3.contracts.evidence_block import EvidenceBlock

        if trace_enabled:
            log_pipeline_event(
                etapa="analytics_expand",
                fase="pre",
                conversation_id=conversation_id,
                dados={"cognitive_plan": snapshot_cognitive_plan(cognitive_plan), "query_chars": len(message or "")},
            )

        expander = QueryExpander(registry=ANALYTICS_TEMPLATES)
        plans = expander.expand(cognitive_plan, al, query_text=message)
        if trace_enabled:
            log_pipeline_event(
                etapa="analytics_expand",
                fase="post",
                conversation_id=conversation_id,
                dados={
                    "plan_count": len(plans),
                    "plans": [snapshot_semantic_plan(p) for p in plans],
                },
            )
        if not plans:
            return None

        if trace_enabled:
            log_pipeline_event(
                etapa="semantic_plan",
                fase="post",
                conversation_id=conversation_id,
                dados={
                    "plan_count": len(plans),
                    "plans": [snapshot_semantic_plan(p) for p in plans],
                },
            )

        async def _exec_one(plan: Any) -> AnalyticsResult:
            tpl = plan.hints.get("_template")
            if tpl is not None:
                params = plan.hints.get("template_params", {})
                return await exec_.execute_template(tpl, params)
            return await exec_.execute_plan(plan)

        if trace_enabled:
            for i, p in enumerate(plans):
                log_pipeline_event(
                    etapa=f"analytics_execute[{i}]",
                    fase="pre",
                    conversation_id=conversation_id,
                    dados=snapshot_semantic_plan(p),
                )

        results = await asyncio.gather(*[_exec_one(p) for p in plans], return_exceptions=True)

        if trace_enabled:
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    log_pipeline_event(
                        etapa=f"analytics_execute[{i}]",
                        fase="post",
                        conversation_id=conversation_id,
                        dados={"erro": type(r).__name__, "mensagem": str(r)[:300]},
                    )
                else:
                    log_pipeline_event(
                        etapa=f"analytics_execute[{i}]",
                        fase="post",
                        conversation_id=conversation_id,
                        dados=snapshot_analytics_result(r),
                    )

        results = [r for r in results if r is not None and not isinstance(r, Exception)]
        if not results:
            if trace_enabled:
                log_pipeline_event(
                    etapa="analytics_merge",
                    fase="pre",
                    conversation_id=conversation_id,
                    dados={"abortado": True, "motivo": "sem_resultados_validos"},
                )
            return None

        merge_pre = {
            "series_specs": [
                {
                    "value_key": s.value_key,
                    "time_key": s.time_key,
                    "grain": s.grain,
                    "template_slug": s.template_slug,
                    "intent_slug": s.intent_slug,
                }
                for s in resolve_evidence_series_specs(
                    results,
                    templates=ANALYTICS_TEMPLATES,
                    default_value_key="total_faturamento",
                    default_time_key=None,
                    default_grain="month",
                )
            ],
            "result_count": len(results),
            "por_resultado": [
                {
                    "i": i,
                    "template_slug": (r.plan.hints or {}).get("template_slug"),
                    "intent_slug": r.plan.intent_slug,
                    "row_count": r.row_count,
                    "chaves_primeira_linha": list(r.rows[0].keys())[:20] if r.rows else [],
                }
                for i, r in enumerate(results)
            ],
        }
        if trace_enabled:
            log_pipeline_event(
                etapa="analytics_merge",
                fase="pre",
                conversation_id=conversation_id,
                dados=merge_pre,
            )

        try:
            merged = EvidenceAggregator().merge(
                results,
                value_key="total_faturamento",
                time_key=None,
                grain="month",
                templates=ANALYTICS_TEMPLATES,
            )
            projected = build_projected_answer(message, results, templates=ANALYTICS_TEMPLATES)
            if projected is not None:
                projected_dict = projected.as_dict()
                complementary_summary = (
                    "Resumo estatístico complementar (não substitui a resposta direta):\n"
                    f"{merged.summary}"
                )
                merged = EvidenceBlock(
                    summary=f"{projected.summary}\n\n{complementary_summary}",
                    insights={**dict(merged.insights), "direct_answer": projected_dict},
                    metrics={**dict(merged.metrics), "answer_plan": projected_dict["plan"]},
                    confidence=merged.confidence,
                    coverage=merged.coverage,
                    provenance=merged.provenance,
                    sample_refs=merged.sample_refs,
                    supporting_data={**dict(merged.supporting_data), "direct_answer": projected_dict},
                )
                if trace_enabled:
                    log_pipeline_event(
                        etapa="answer_project",
                        fase="post",
                        conversation_id=conversation_id,
                        dados={
                            "presente": True,
                            "plan": projected_dict["plan"],
                            "summary": projected.summary,
                        },
                    )
            elif trace_enabled:
                log_pipeline_event(
                    etapa="answer_project",
                    fase="post",
                    conversation_id=conversation_id,
                    dados={"presente": False},
                )
            if trace_enabled:
                log_pipeline_event(
                    etapa="analytics_merge",
                    fase="post",
                    conversation_id=conversation_id,
                    dados=snapshot_evidence_block(merged),
                )
            return merged
        except Exception:
            _LOG.exception("analytics aggregation failed")
            if trace_enabled:
                log_pipeline_event(
                    etapa="analytics_merge",
                    fase="post",
                    conversation_id=conversation_id,
                    dados={"erro": "aggregation_exception"},
                )
            return None

    return router
