"""
Rota ``POST /api/v1/chat`` (Fase 6.1).

Fluxo: request → session → orchestrator → narrator → response.
Suporta SSE streaming quando ``request.stream=True``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from orion_mcp_v3.api.models import (
    ChatOptionsResponse,
    ChatRequest,
    ChatResponse,
    ChatResponseMeta,
    EmailDeliveryInfo,
    ErrorResponse,
    SessionListItem,
    SessionListResponse,
    UsageInfo,
)
from orion_mcp_v3.api.email_sender import EmailSendRequest, EmailSendResult
from orion_mcp_v3.broker import ANALYTICS_TEMPLATES
from orion_mcp_v3.broker.executor import AnalyticsExecutor
from orion_mcp_v3.broker.query_capability_catalog import build_query_capability_catalog
from orion_mcp_v3.broker.query_template_selector import QuerySelectionValidator, QueryTemplateSelector
from orion_mcp_v3.broker.sql_compiler import SqlAllowlist
from orion_mcp_v3.contracts.answer_presentation import AnswerPresentationContract
from orion_mcp_v3.contracts.analytics_outcome import AnalyticsOutcome
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.evidence_contract import PipelineFailure
from orion_mcp_v3.contracts.query_selection import QuerySelectionContract
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
    snapshot_analytics_outcome,
    snapshot_analytics_result,
    snapshot_cognitive_plan,
    snapshot_evidence_contract,
    snapshot_evidence_block,
    snapshot_orchestration,
    snapshot_query_cards,
    snapshot_reasoning_result,
    snapshot_semantic_plan,
)
from orion_mcp_v3.runtime.analytical_context_policy import AnalyticalContextIsolationPolicy
from orion_mcp_v3.runtime.analytical_reasoner import AnalyticalReasoner
from orion_mcp_v3.runtime.analytical_signature import signature_from_evidence, signature_from_plan
from orion_mcp_v3.runtime.analytical_intent_interpreter import (
    AnalyticalIntentInterpreter,
    memory_context_from_messages,
)
from orion_mcp_v3.runtime.analytical_intent_validator import IntentContractValidator
from orion_mcp_v3.runtime.answer_presentation_interpreter import (
    AnswerPresentationInterpreter,
    AnswerPresentationValidator,
)
from orion_mcp_v3.runtime.heuristic_signal_catalog import (
    HeuristicSignalCatalog,
    extract_heuristic_signals,
)
from orion_mcp_v3.runtime.intent_resolver import IntentResolver, map_attention_profile_to_policy
from orion_mcp_v3.runtime.narrator import CognitiveNarrator
from orion_mcp_v3.runtime.period_adequacy import resolve_period_adequacy
from orion_mcp_v3.runtime.session_manager import SessionManager

_LOG = logging.getLogger("orion.api.chat")


def _is_all_records_followup(message: str) -> bool:
    text = (message or "").strip().lower()
    return bool(
        re.search(r"\btod[oa]s?\s+(os\s+)?registros\b", text)
        or re.search(r"\btod[oa]s?\s+(os\s+)?registos\b", text)
        or "lista completa" in text
    )


def _format_followup_value(value: Any, measure: str | None) -> str:
    try:
        n = float(str(value))
    except (TypeError, ValueError):
        return str(value)
    if measure and "percentual" in measure:
        return f"{n:.2f}%".replace(".", ",")
    if measure and any(token in measure for token in ("quantidade", "qtd", "total_os")):
        return f"{n:,.0f}".replace(",", ".")
    whole = f"{n:,.2f}"
    left, right = whole.rsplit(".", 1)
    return f"R$ {left.replace(',', '.')},{right}"


def _all_records_evidence_from_last(evidence: Any, message: str) -> EvidenceBlock | None:
    if not isinstance(evidence, EvidenceBlock):
        return None
    direct = evidence.supporting_data.get("direct_answer") if evidence.supporting_data else None
    if not isinstance(direct, dict):
        return None
    plan = direct.get("plan")
    rows = direct.get("rows")
    if not isinstance(plan, dict) or not isinstance(rows, list) or not rows:
        return None
    measure = str(plan.get("measure") or "")
    dimension = plan.get("dimension")
    dim = str(dimension) if dimension else None
    lines = [f"Resposta direta da memória analítica: todos os registros de {measure}:"]
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        label = str(row.get(dim, f"registro {i}")) if dim else f"registro {i}"
        value = _format_followup_value(row.get(measure), measure)
        period = row.get("periodo")
        suffix = f" ({period})" if period else ""
        lines.append(f"{i}. {label}{suffix}: {value}")
    if len(lines) == 1:
        return None
    summary = "\n".join(lines)
    return EvidenceBlock(
        summary=summary,
        insights={**dict(evidence.insights), "memory_followup": True, "followup_query": message},
        metrics={**dict(evidence.metrics), "memory_followup": True, "input_rows": len(lines) - 1},
        confidence=evidence.confidence,
        coverage=evidence.coverage,
        provenance=evidence.provenance,
        sample_refs=evidence.sample_refs,
        supporting_data={**dict(evidence.supporting_data), "memory_followup": True},
    )


def _resolve_policy(name: str) -> AttentionPolicy:
    try:
        return AttentionPolicy(name.strip().lower())
    except ValueError:
        return AttentionPolicy.BALANCED


def _period_context_missing_reply() -> str:
    return (
        "Preciso que você informe o período da análise para responder com segurança. "
        "Não encontrei um período analítico anterior confiável para herdar."
    )


def _direct_answer_literal_preservation_enabled(evidence: EvidenceBlock | None) -> bool:
    if evidence is None:
        return False
    direct_set = evidence.supporting_data.get("direct_answer_set") if evidence.supporting_data else None
    if isinstance(direct_set, Mapping):
        return True
    direct = evidence.supporting_data.get("direct_answer") if evidence.supporting_data else None
    if not isinstance(direct, Mapping):
        return False
    plan = direct.get("plan")
    if not isinstance(plan, Mapping):
        return False
    scope = plan.get("result_scope")
    return (
        (isinstance(scope, Mapping) and scope.get("mode") == "all")
        or plan.get("operation") == "list"
    )


def _should_interpret_with_llm(
    plan: CognitivePlan,
    *,
    policy_request: str | None,
    memory_context_has_analytics: bool,
    regex_signals: HeuristicSignalCatalog,
    provider: LLMProvider,
) -> bool:
    if isinstance(provider, NullLLMProvider):
        return False
    signal_labels = {s.label for s in regex_signals.signals}
    followup = any(s.kind == "followup_signal" for s in regex_signals.signals)
    policy = (policy_request or "").strip().lower()
    return (
        plan.confidence < 0.7
        or followup
        or plan.needs_comparison
        or (policy == "analytical" and plan.time_scope is None and bool(signal_labels))
        or (memory_context_has_analytics and (plan.needs_analytics or "comparative" in signal_labels))
    )


def _plan_with_query_selection(
    plan: CognitivePlan,
    selection: QuerySelectionContract,
) -> CognitivePlan:
    hints = dict(plan.hints or {})
    intent_contract = hints.get("intent_contract")
    if isinstance(intent_contract, Mapping):
        intent_contract = {
            **dict(intent_contract),
            "template_slug": selection.template_slug,
            "entity_filters": [dict(item) for item in selection.entity_filters],
        }
    else:
        intent_contract = {
            "template_slug": selection.template_slug,
            "metric": selection.measure,
            "dimension": selection.dimension,
            "operation": selection.operation,
            "entity_filters": [dict(item) for item in selection.entity_filters],
        }
    hints.update(
        {
            "template_slug": selection.template_slug,
            "intent_contract": intent_contract,
            "selected_metric": selection.measure,
            "selected_dimension": selection.dimension,
            "selected_operation": selection.operation,
            "entity_filters": selection.entity_filters,
            "semantic_reason": "llm_query_selector",
            "query_selection": selection.as_dict(),
        }
    )
    metrics = (selection.measure,) if selection.measure else plan.metrics
    entities = (selection.dimension,) if selection.dimension else plan.entities
    return replace(plan, metrics=metrics, entities=entities, hints=hints)


def _plan_with_answer_presentation(
    plan: CognitivePlan,
    presentation: AnswerPresentationContract,
) -> CognitivePlan:
    hints = dict(plan.hints or {})
    hints.update(
        {
            "result_scope": presentation.result_scope,
            "sort": presentation.sort,
            "answer_presentation": presentation.as_dict(),
        }
    )
    return replace(plan, hints=hints)


def create_chat_router(
    *,
    session_manager: SessionManager | None = None,
    llm_provider: LLMProvider | None = None,
    narrator: CognitiveNarrator | None = None,
    analytics_executor: AnalyticsExecutor | None = None,
    analytics_allowlist: SqlAllowlist | None = None,
    analytics_state: dict | None = None,
    email_sender: Any | None = None,
) -> APIRouter:
    """Factory que retorna o router de chat com dependências injectadas."""
    router = APIRouter(prefix="/api/v1", tags=["chat"])
    sm = session_manager or SessionManager()
    provider = llm_provider or NullLLMProvider()
    narr = narrator or CognitiveNarrator(provider)
    orchestrator = CognitiveOrchestrator()
    resolver = IntentResolver()
    context_policy = AnalyticalContextIsolationPolicy()
    capability_catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)
    intent_interpreter = AnalyticalIntentInterpreter(provider)
    intent_validator = IntentContractValidator(capability_catalog)
    query_selector = QueryTemplateSelector(provider)
    query_selection_validator = QuerySelectionValidator(capability_catalog)
    presentation_interpreter = AnswerPresentationInterpreter(provider)
    presentation_validator = AnswerPresentationValidator(capability_catalog)
    _fixed_executor = analytics_executor
    _fixed_allowlist = analytics_allowlist
    # Não usar ``analytics_state or {}``: um dict vazio é falsy e seria substituído
    # por um novo {}, quebrando o partilhamento com o lifespan (executor nunca visto).
    _state: dict = analytics_state if analytics_state is not None else {}

    async def _send_response_email(
        req: ChatRequest,
        body: str,
        *,
        conversation_id: str,
        trace_enabled: bool = False,
    ) -> EmailSendResult:
        def _trace(phase: str, data: Mapping[str, Any]) -> None:
            if trace_enabled:
                log_pipeline_event(
                    etapa="email_delivery",
                    fase=phase,
                    conversation_id=conversation_id,
                    dados=dict(data),
                )

        _trace(
            "pre",
            {
                "requested": bool(req.email_to),
                "to": req.email_to,
                "subject_present": bool(req.email_subject),
                "sender_present": email_sender is not None,
                "body_chars": len(body or ""),
            },
        )
        if not req.email_to:
            _LOG.info("email_delivery not_requested conversation_id=%s", conversation_id)
            result = EmailSendResult(status="not_requested")
            _trace("post", result.as_dict())
            return result
        if email_sender is None:
            _LOG.warning(
                "email_delivery skipped conversation_id=%s to=%s reason=email_sender_missing",
                conversation_id,
                req.email_to,
            )
            result = EmailSendResult(status="skipped", to=req.email_to, message="envio de e-mail não configurado")
            _trace("post", result.as_dict())
            return result
        try:
            _LOG.info(
                "email_delivery requested conversation_id=%s to=%s subject_present=%s",
                conversation_id,
                req.email_to,
                bool(req.email_subject),
            )
            result = await email_sender.send_response(
                EmailSendRequest(
                    to=req.email_to,
                    subject=req.email_subject or "Resposta Orion",
                    body=body,
                    conversation_id=conversation_id,
                )
            )
            _LOG.info(
                "email_delivery result conversation_id=%s to=%s status=%s message=%s",
                conversation_id,
                result.to,
                result.status,
                result.message,
            )
            _trace("post", result.as_dict())
            return result
        except Exception:
            _LOG.exception("email sender failed")
            result = EmailSendResult(status="failed", to=req.email_to, message="falha ao enviar e-mail")
            _trace("post", result.as_dict())
            return result

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
        recent_messages = await sm.get_recent_messages(session)
        memory_context = memory_context_from_messages(recent_messages, current_message=req.message)
        regex_signals = extract_heuristic_signals(req.message)
        interpret_with_llm = _should_interpret_with_llm(
            cognitive_plan,
            policy_request=req.policy,
            memory_context_has_analytics=memory_context.has_analytical_memory,
            regex_signals=regex_signals,
            provider=provider,
        )
        if trace_pipe:
            log_pipeline_event(
                etapa="intent_interpret",
                fase="pre",
                conversation_id=cid,
                dados={
                    "used_llm": interpret_with_llm,
                    "regex_signal_count": len(regex_signals.signals),
                    "has_analytical_memory": memory_context.has_analytical_memory,
                },
            )
        accepted_contract = None
        rejected_reason = "not_needed"
        if interpret_with_llm:
            contract = await intent_interpreter.interpret(
                req.message,
                recent_context=memory_context,
                capabilities=capability_catalog,
                regex_signals=regex_signals,
                heuristic_plan=cognitive_plan,
            )
            if contract is None:
                rejected_reason = "no_valid_json"
            else:
                validation = intent_validator.validate(
                    contract,
                    heuristic_plan=cognitive_plan,
                    has_analytical_memory=memory_context.has_analytical_memory,
                )
                if validation.accepted and validation.cognitive_plan is not None:
                    accepted_contract = validation.contract
                    cognitive_plan = validation.cognitive_plan
                    rejected_reason = None
                else:
                    rejected_reason = validation.rejected_reason or "validator_rejected"
        if trace_pipe:
            log_pipeline_event(
                etapa="intent_interpret",
                fase="post",
                conversation_id=cid,
                dados={
                    "used_llm": interpret_with_llm,
                    "accepted": accepted_contract is not None,
                    "rejected_reason": rejected_reason,
                    "operation": accepted_contract.operation.value if accepted_contract else None,
                    "metric": accepted_contract.metric if accepted_contract else None,
                    "dimension": accepted_contract.dimension if accepted_contract else None,
                    "regex_signal_count": len(regex_signals.signals),
                },
            )
        query_select_with_llm = cognitive_plan.needs_analytics and not isinstance(provider, NullLLMProvider)
        query_selection = None
        accepted_query_selection = None
        query_selection_rejected_reason = "not_needed"
        if trace_pipe:
            log_pipeline_event(
                etapa="query_select",
                fase="pre",
                conversation_id=cid,
                dados={
                    "used_llm": query_select_with_llm,
                    "message_preview": (req.message or "")[:240],
                    "cognitive_plan": snapshot_cognitive_plan(cognitive_plan),
                    "query_cards": snapshot_query_cards(capability_catalog.query_cards()),
                },
            )
        if query_select_with_llm:
            query_selection = await query_selector.select(
                req.message,
                cognitive_plan=cognitive_plan,
                capabilities=capability_catalog,
            )
            if query_selection is not None:
                query_selection_validation = query_selection_validator.validate(query_selection)
                if query_selection_validation.accepted and query_selection_validation.contract is not None:
                    accepted_query_selection = query_selection_validation.contract
                    cognitive_plan = _plan_with_query_selection(
                        cognitive_plan,
                        accepted_query_selection,
                    )
                    query_selection_rejected_reason = None
                else:
                    query_selection_rejected_reason = (
                        query_selection_validation.rejected_reason or "validator_rejected"
                    )
            else:
                query_selection_rejected_reason = "no_valid_json"
        if trace_pipe:
            log_pipeline_event(
                etapa="query_select",
                fase="post",
                conversation_id=cid,
                dados={
                    "used_llm": query_select_with_llm,
                    "accepted": query_selection_rejected_reason is None,
                    "rejected_reason": query_selection_rejected_reason,
                    "selection": query_selection.as_dict() if query_selection is not None else None,
                    "cognitive_plan": snapshot_cognitive_plan(cognitive_plan),
                },
            )
        presentation_with_llm = accepted_query_selection is not None and not isinstance(provider, NullLLMProvider)
        answer_presentation = None
        presentation_rejected_reason = "not_needed"
        if trace_pipe:
            log_pipeline_event(
                etapa="answer_present",
                fase="pre",
                conversation_id=cid,
                dados={
                    "used_llm": presentation_with_llm,
                    "query_selection": accepted_query_selection.as_dict()
                    if accepted_query_selection is not None
                    else None,
                },
            )
        if presentation_with_llm and accepted_query_selection is not None:
            answer_presentation = await presentation_interpreter.interpret(
                req.message,
                cognitive_plan=cognitive_plan,
                query_selection=accepted_query_selection,
                capabilities=capability_catalog,
            )
            if answer_presentation is not None:
                presentation_validation = presentation_validator.validate(
                    answer_presentation,
                    query_selection=accepted_query_selection,
                )
                if presentation_validation.accepted and presentation_validation.contract is not None:
                    cognitive_plan = _plan_with_answer_presentation(
                        cognitive_plan,
                        presentation_validation.contract,
                    )
                    presentation_rejected_reason = None
                else:
                    presentation_rejected_reason = (
                        presentation_validation.rejected_reason or "validator_rejected"
                    )
            else:
                presentation_rejected_reason = "no_valid_json"
        if trace_pipe:
            log_pipeline_event(
                etapa="answer_present",
                fase="post",
                conversation_id=cid,
                dados={
                    "used_llm": presentation_with_llm,
                    "accepted": presentation_rejected_reason is None,
                    "rejected_reason": presentation_rejected_reason,
                    "presentation": answer_presentation.as_dict()
                    if answer_presentation is not None
                    else None,
                    "cognitive_plan": snapshot_cognitive_plan(cognitive_plan),
                },
            )
        period_decision = resolve_period_adequacy(
            req.message,
            cognitive_plan,
            last_evidence=session.extra.get("last_analytical_evidence"),
        )
        cognitive_plan = period_decision.plan
        if trace_pipe:
            log_pipeline_event(
                etapa="period_gate",
                fase="post",
                conversation_id=cid,
                dados=period_decision.as_trace(),
            )
        if period_decision.should_block:
            reply = _period_context_missing_reply()
            await sm.record_assistant_message(session, reply)
            sm.update_phase(session, CognitivePhase.IDLE)
            elapsed = (time.monotonic() - t0) * 1000.0
            meta = ChatResponseMeta(
                conversation_id=session.conversation_id,
                model="period_gate",
                finish_reason=period_decision.blocked_reason or "blocked",
                latency_ms=elapsed,
                usage=UsageInfo(),
                safeguards=["period_context_required"],
                cognitive_intent=cognitive_plan.intent_type.value,
                coverage_note="",
            )
            return ChatResponse(reply=reply, meta=meta)
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

        analytics_outcome = AnalyticsOutcome.not_required()
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
            analytics_outcome = await _run_analytics(
                exec_, al, cognitive_plan, req.message, trace_enabled=trace_pipe, conversation_id=cid,
            )
            evidence = analytics_outcome.evidence
            if evidence is not None:
                session.extra["last_analytical_evidence"] = evidence
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
        if trace_pipe:
            log_pipeline_event(
                etapa="analytics_outcome",
                fase="post",
                conversation_id=cid,
                dados=snapshot_analytics_outcome(analytics_outcome),
            )
            log_pipeline_event(
                etapa="evidence_contract",
                fase="post",
                conversation_id=cid,
                dados=snapshot_evidence_contract(analytics_outcome.evidence_contract),
            )

        if evidence is None and _is_all_records_followup(req.message):
            memory_evidence = _all_records_evidence_from_last(
                session.extra.get("last_analytical_evidence"),
                req.message,
            )
            if memory_evidence is not None:
                evidence = memory_evidence
                analytics_outcome = AnalyticsOutcome.executed(
                    evidence=memory_evidence,
                    row_count=int((memory_evidence.metrics or {}).get("input_rows") or 0),
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

        reasoning_result = AnalyticalReasoner().reason(
            req.message,
            cognitive_plan=cognitive_plan,
            analytics_outcome=analytics_outcome,
            last_analytical_evidence=session.extra.get("last_analytical_evidence"),
        )
        if trace_pipe:
            log_pipeline_event(
                etapa="analytical_reasoner",
                fase="post",
                conversation_id=cid,
                dados=snapshot_reasoning_result(reasoning_result),
            )

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
            reasoning_result=reasoning_result,
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
            return _sse_response(narr, orch_result, session, sm, t0, cognitive_plan, req, trace_pipe=trace_pipe)

        if trace_pipe:
            log_pipeline_event(
                etapa="narrate",
                fase="pre",
                conversation_id=cid,
                dados={
                    "orch_prompt_chars": len(orch_result.prompt_text or ""),
                    "direct_answer_literal_preservation": _direct_answer_literal_preservation_enabled(evidence),
                },
            )

        narration = await narr.narrate(orch_result)
        email_delivery = await _send_response_email(
            req,
            narration.narration,
            conversation_id=session.conversation_id,
            trace_enabled=trace_pipe,
        )

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
            email_delivery=EmailDeliveryInfo(**email_delivery.as_dict()),
        )
        return ChatResponse(reply=narration.narration, meta=meta)

    def _sse_response(narr, orch_result, session, sm, t0, cognitive_plan, req: ChatRequest, *, trace_pipe: bool = False):
        cid = session.conversation_id

        async def event_generator():
            full_text: list[str] = []
            email_delivery = EmailSendResult(status="not_requested")
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
                email_delivery = await _send_response_email(
                    req,
                    text,
                    conversation_id=session.conversation_id,
                    trace_enabled=trace_pipe,
                )
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
                    "email_delivery": email_delivery.as_dict(),
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
    ) -> AnalyticsOutcome:
        from orion_mcp_v3.broker import (
            ANALYTICS_TEMPLATES,
            AnalyticsResult,
            EvidenceAggregator,
            QueryExpander,
        )
        from orion_mcp_v3.broker.evidence_series_resolve import resolve_evidence_series_specs

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
            return AnalyticsOutcome.no_plan()

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
                return await exec_.execute_template(tpl, params, plan=plan)
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

        failures = [r for r in results if isinstance(r, Exception)]
        results = [r for r in results if r is not None and not isinstance(r, Exception)]
        if not results:
            if trace_enabled:
                log_pipeline_event(
                    etapa="analytics_merge",
                    fase="pre",
                    conversation_id=conversation_id,
                    dados={"abortado": True, "motivo": "sem_resultados_validos"},
                )
            failure = failures[0] if failures else None
            return AnalyticsOutcome.execution_failure(
                PipelineFailure(
                    stage="analytics_execute",
                    failure_type=type(failure).__name__ if failure is not None else "no_valid_results",
                    impact="nenhum resultado analítico válido foi produzido",
                    analytical_consequence="não há evidência nova segura para a narração",
                    recoverable=True,
                ),
                plan_count=len(plans),
            )

        total_rows = sum(r.row_count for r in results)
        if total_rows == 0:
            return AnalyticsOutcome.executed_empty(row_count=0, plan_count=len(plans))

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
                query_text=message,
            )
            projected_dict = (
                merged.supporting_data.get("direct_answer")
                if isinstance(merged.supporting_data, Mapping)
                else None
            )
            if isinstance(projected_dict, Mapping):
                if trace_enabled:
                    log_pipeline_event(
                        etapa="answer_project",
                        fase="post",
                        conversation_id=conversation_id,
                        dados={
                            "presente": True,
                            "plan": projected_dict.get("plan"),
                            "summary": projected_dict.get("summary"),
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
            return AnalyticsOutcome.executed(
                evidence=merged,
                row_count=total_rows,
                plan_count=len(plans),
            )
        except Exception:
            _LOG.exception("analytics aggregation failed")
            if trace_enabled:
                log_pipeline_event(
                    etapa="analytics_merge",
                    fase="post",
                    conversation_id=conversation_id,
                    dados={"erro": "aggregation_exception"},
                )
            return AnalyticsOutcome.aggregation_failure(
                PipelineFailure(
                    stage="analytics_merge",
                    failure_type="aggregation_exception",
                    impact="a execução retornou linhas, mas a agregação falhou",
                    analytical_consequence="não há EvidenceBlock confiável para narrar",
                    recoverable=True,
                ),
                row_count=total_rows,
            )

    return router
