from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from orion_mcp_v3.protocols.llm import LLMResponse, LLMStreamChunk
from orion_mcp_v3.public_chat.application.consulta_turn_runner import (
    ConsultaTurnRunner,
    should_store_resolution_cache,
)
from orion_mcp_v3.public_chat.config.settings import PublicChatSettings
from orion_mcp_v3.public_chat.domain.fact_engine.confidence import MIN_CACHE_STORE_CONFIDENCE
from orion_mcp_v3.public_chat.domain.fact_engine.fact_type import FactType
from orion_mcp_v3.public_chat.domain.fact_engine.gap import FactGap, GapReason
from orion_mcp_v3.public_chat.domain.fact_engine.models import ExtractedFact, RemissiveWorkspace
from orion_mcp_v3.public_chat.domain.fact_engine.trace import ExtractionPath, FactTrace, ResolutionRule
from orion_mcp_v3.public_chat.domain.knowledge import (
    ConhecimentoRecuperado,
    KnowledgeHit,
)
from orion_mcp_v3.public_chat.domain.knowledge_fingerprint import (
    build_knowledge_fingerprint_from_knowledge,
)
from orion_mcp_v3.public_chat.infrastructure.analytical_narrator import (
    AnalyticalNarrator,
    NO_FACTS_FALLBACK_MESSAGE,
)
from orion_mcp_v3.public_chat.infrastructure.intent_interpreter import PublicIntentInterpreter
from orion_mcp_v3.public_chat.infrastructure.narrator import PublicNarrator
from orion_mcp_v3.public_chat.infrastructure.remissive_retriever import RemissiveRetriever
from orion_mcp_v3.public_chat.infrastructure.response_store import ResponseStore
from orion_mcp_v3.public_chat.tests.phase4.helpers import PassthroughContextSelector


def _pool_with_conn(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


def _insert_row(*, question_id, thread_id, topic="faturamento:2026-05", semantic_hash="hash1"):
    return {
        "id": question_id,
        "thread_id": thread_id,
        "parent_question_id": None,
        "topic": topic,
        "intent_contract": {
            "intent": "consulta_metrica",
            "metric": "faturamento",
            "period": "2026-05",
            "confidence": 0.9,
        },
        "semantic_hash": semantic_hash,
        "query_original": "faturamento maio?",
        "created_at": "2026-06-16T00:00:00+00:00",
    }


def _cached_row(*, response_id, topic, semantic_hash, fingerprint="fp-stable"):
    return {
        "id": response_id,
        "topic": topic,
        "semantic_hash": semantic_hash,
        "answer_payload": {"knowledge_ids": [42], "context_keys": [], "essence_themes": []},
        "knowledge_fingerprint": fingerprint,
        "presentation_snapshot": None,
        "expires_at": "2099-01-01T00:00:00+00:00",
    }


def _knowledge() -> ConhecimentoRecuperado:
    return ConhecimentoRecuperado(
        hits=(
            KnowledgeHit(
                origin_id=42,
                context_key="ctx",
                category="Financeiro",
                validated_answer="validado",
                key_metrics={"faturamento": 1},
            ),
        )
    )


def _period_hit(origin_id: int, period: str) -> KnowledgeHit:
    return KnowledgeHit(
        origin_id=origin_id,
        context_key=f"sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-{period}",
        category="Fechamento Gerencial",
        validated_answer=f"Faturamento {period}.",
        key_metrics={"faturamento_por_tipo_de_venda": {"rows": [], "_meta": {}}},
    )


def _runner(store: ResponseStore, retriever: AsyncMock, llm: AsyncMock | None = None) -> ConsultaTurnRunner:
    llm = llm or AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='{"intent":"consulta_metrica","metric":"faturamento","period":"2026-05","confidence":0.9}'
    )

    async def _stream(*_args, **_kwargs):
        yield LLMStreamChunk(delta="Resposta narrada.")
        yield LLMStreamChunk(delta="", finish_reason="stop")

    llm.stream = _stream
    return ConsultaTurnRunner(
        settings=PublicChatSettings(cache_ttl_days=90),
        store=store,
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
    )


@pytest.mark.asyncio
async def test_cache_hit_by_semantic_hash() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(question_id=question_id, thread_id=thread_id)

    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        insert,
        {"thread_id": thread_id},
        insert,
        _cached_row(response_id=response_id, topic=insert["topic"], semantic_hash=insert["semantic_hash"]),
    ]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.reload_from_payload.return_value = _knowledge()

    runner = _runner(ResponseStore(_pool_with_conn(conn)), retriever)
    result, _ = await runner.run_turn_with_metadata("faturamento maio?")

    assert result.cached is True
    retriever.retrieve.assert_not_awaited()
    retriever.reload_from_payload.assert_awaited_once()
    link_args = conn.execute.await_args.args
    assert link_args[3] is True


@pytest.mark.asyncio
async def test_cache_hit_serves_presentation_snapshot_without_narrator() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(question_id=question_id, thread_id=thread_id)

    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        insert,
        {"thread_id": thread_id},
        insert,
        {
            **_cached_row(
                response_id=response_id,
                topic=insert["topic"],
                semantic_hash=insert["semantic_hash"],
                fingerprint=build_knowledge_fingerprint_from_knowledge(_knowledge()),
            ),
            "presentation_snapshot": "Resposta cacheada pronta.",
        },
    ]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='{"intent":"consulta_metrica","metric":"faturamento","period":"2026-05","confidence":0.9}'
    )
    stream_calls = 0

    async def _stream(*_args, **_kwargs):
        nonlocal stream_calls
        stream_calls += 1
        yield LLMStreamChunk(delta="Narrativa inesperada.")

    llm.stream = _stream

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.reload_from_payload.return_value = _knowledge()

    runner = ConsultaTurnRunner(
        settings=PublicChatSettings(),
        store=ResponseStore(_pool_with_conn(conn)),
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
    )

    _, presentation = await runner.run_turn_with_metadata("faturamento maio?")

    assert stream_calls == 0
    assert presentation == "Resposta cacheada pronta."


@pytest.mark.asyncio
async def test_cache_hit_regenerates_narrative() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(question_id=question_id, thread_id=thread_id)

    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        insert,
        {"thread_id": thread_id},
        insert,
        _cached_row(response_id=response_id, topic=insert["topic"], semantic_hash=insert["semantic_hash"]),
    ]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='{"intent":"consulta_metrica","metric":"faturamento","period":"2026-05","confidence":0.9}'
    )
    stream_calls = 0

    async def _stream(*_args, **_kwargs):
        nonlocal stream_calls
        stream_calls += 1
        yield LLMStreamChunk(delta="Nova narrativa.")

    llm.stream = _stream

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.reload_from_payload.return_value = _knowledge()

    runner = ConsultaTurnRunner(
        settings=PublicChatSettings(use_presentation_snapshot=False),
        store=ResponseStore(_pool_with_conn(conn)),
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
    )

    _, presentation = await runner.run_turn_with_metadata("faturamento maio?")

    assert stream_calls >= 1
    assert "Nova narrativa." in presentation


@pytest.mark.asyncio
async def test_knowledge_fingerprint_invalidation() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(question_id=question_id, thread_id=thread_id)

    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        insert,
        {"thread_id": thread_id},
        insert,
        _cached_row(
            response_id=response_id,
            topic=insert["topic"],
            semantic_hash=insert["semantic_hash"],
            fingerprint="stale-fp",
        ),
    ]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.reload_from_payload.return_value = _knowledge()

    runner = _runner(ResponseStore(_pool_with_conn(conn)), retriever)
    await runner.run_turn_with_metadata("faturamento maio?")

    fingerprint_arg = conn.fetchval.await_args.args[4]
    assert fingerprint_arg != "stale-fp"


@pytest.mark.asyncio
async def test_cache_hit_completes_multi_period_evidence_before_updating_payload() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(
        question_id=question_id,
        thread_id=thread_id,
        topic="faturamento:2026-04",
        semantic_hash="hash-comparison",
    )
    cached = _cached_row(
        response_id=response_id,
        topic="faturamento:2026-04",
        semantic_hash="hash-comparison",
        fingerprint="stale-fp",
    )

    conn = AsyncMock()
    conn.fetchrow.side_effect = [
        insert,
        {"thread_id": thread_id},
        insert,
        cached,
    ]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text=(
            '{"intent":"comparacao","metric":"faturamento","period":"2026-04",'
            '"operation":"comparison","entity_filters":[{"dimension":"periodo","value":"2026-05","match":"exact"}],'
            '"confidence":0.9}'
        )
    )

    async def _stream(*_args, **_kwargs):
        yield LLMStreamChunk(delta="Comparação narrada.")

    llm.stream = _stream

    maio = _period_hit(34, "2026-05")
    abril = _period_hit(28, "2026-04")
    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.reload_from_payload.return_value = ConhecimentoRecuperado(hits=(maio,))
    retriever.complete_period_evidence.return_value = ConhecimentoRecuperado(hits=(maio, abril))

    runner = ConsultaTurnRunner(
        settings=PublicChatSettings(cache_ttl_days=90),
        store=ResponseStore(_pool_with_conn(conn)),
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
    )

    await runner.run_turn_with_metadata("qual o faturamento em maio de 2026 vs abril de 2026?")

    retriever.complete_period_evidence.assert_awaited_once()
    payload_arg = json.loads(conn.fetchval.await_args.args[3])
    assert set(payload_arg["knowledge_ids"]) == {28, 34}


@pytest.mark.asyncio
async def test_runner_full_hit_then_miss() -> None:
    question_id = uuid4()
    response_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(question_id=question_id, thread_id=thread_id)

    conn = AsyncMock()
    conn.fetchrow.side_effect = [insert, {"thread_id": thread_id}, insert, None]
    conn.fetchval.return_value = response_id
    conn.execute.return_value = "INSERT 0 1"

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.retrieve.return_value = _knowledge()

    runner = _runner(ResponseStore(_pool_with_conn(conn)), retriever)
    result, _ = await runner.run_turn_with_metadata("faturamento maio?")

    assert result.cached is False
    retriever.retrieve.assert_awaited_once()


def _fact(fact_key: str = "dynamic:parcelamento_de_cartao@growth") -> ExtractedFact:
    return ExtractedFact(
        fact_key=fact_key,
        label="3X",
        value="43.32%",
        unit="pct",
        fact_type=FactType.DERIVED,
        confidence=0.85,
        origin_id=49,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-06",
        trace=FactTrace(
            fact_key=fact_key,
            resolved_from=(8, 49),
            context_keys=(
                "sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-01",
                "sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-06",
            ),
            rule_applied=ResolutionRule.JOIN_PLAN,
            extraction_path=ExtractionPath.RANKING_DERIVED,
        ),
    )


def _weak_workspace(*, gap_count: int = 1, fact_count: int = 0, confidence: float = 0.0) -> RemissiveWorkspace:
    gaps = tuple(
        FactGap(fact_key=f"dynamic:periodo-{index}", reason=GapReason.KEY_METRICS_INDEX_AMBIGUOUS)
        for index in range(gap_count)
    )
    facts = tuple(_fact(f"dynamic:fact-{index}") for index in range(fact_count))
    return RemissiveWorkspace(
        period="2026-02",
        facts=facts,
        gaps=gaps if gap_count else (),
        requirements=(),
        join_plan=None,
        workspace_confidence=confidence,
    )


def test_should_store_resolution_cache_legacy_path() -> None:
    assert should_store_resolution_cache(None) is True


def test_should_store_resolution_cache_rejects_no_facts_fallback() -> None:
    assert should_store_resolution_cache(None, presentation=NO_FACTS_FALLBACK_MESSAGE) is False


def test_should_store_resolution_cache_rejects_weak_workspace() -> None:
    assert should_store_resolution_cache(_weak_workspace()) is False
    assert should_store_resolution_cache(_weak_workspace(gap_count=0, fact_count=0, confidence=0.9)) is False
    assert (
        should_store_resolution_cache(
            _weak_workspace(gap_count=0, fact_count=1, confidence=MIN_CACHE_STORE_CONFIDENCE - 0.01)
        )
        is False
    )


def test_should_store_resolution_cache_allows_partial_with_facts_and_high_confidence() -> None:
    workspace = _weak_workspace(gap_count=2, fact_count=1, confidence=0.85)
    assert workspace.gaps
    assert should_store_resolution_cache(workspace) is True
    assert should_store_resolution_cache(
        _weak_workspace(gap_count=0, fact_count=1, confidence=MIN_CACHE_STORE_CONFIDENCE)
    ) is True


@pytest.mark.asyncio
async def test_cache_miss_skips_store_when_workspace_has_gaps(monkeypatch: pytest.MonkeyPatch) -> None:
    question_id = uuid4()
    thread_id = uuid4()
    insert = _insert_row(
        question_id=question_id,
        thread_id=thread_id,
        topic="faturamento:2026-02",
        semantic_hash="hash-fev",
    )

    conn = AsyncMock()
    conn.fetchrow.side_effect = [insert, {"thread_id": thread_id}, insert, None]
    conn.execute.return_value = "INSERT 0 1"

    retriever = AsyncMock(spec=RemissiveRetriever)
    retriever.retrieve.return_value = _knowledge()

    llm = AsyncMock()
    llm.chat.return_value = LLMResponse(
        text='{"intent":"consulta_metrica","metric":"faturamento","period":"2026-02","confidence":0.9}'
    )

    async def _stream(*_args, **_kwargs):
        yield LLMStreamChunk(delta="Não encontrei fatos validados suficientes para responder.")

    llm.stream = _stream

    store = ResponseStore(_pool_with_conn(conn))
    upsert = AsyncMock(wraps=store.upsert_resolution)
    link = AsyncMock(wraps=store.link_question_response)
    store.upsert_resolution = upsert
    store.link_question_response = link

    async def _fake_build(*_args, **_kwargs):
        return _weak_workspace()

    monkeypatch.setattr(
        "orion_mcp_v3.public_chat.application.consulta_turn_runner.build_remissive_workspace",
        _fake_build,
    )

    runner = ConsultaTurnRunner(
        settings=PublicChatSettings(use_workspace=True),
        store=store,
        intent_interpreter=PublicIntentInterpreter(llm),
        retriever=retriever,
        narrator=PublicNarrator(llm),
        context_selector=PassthroughContextSelector(llm),
        fact_planner=AsyncMock(),
        memory_resolver=AsyncMock(),
        analytical_narrator=AnalyticalNarrator(llm),
    )

    result, _ = await runner.run_turn_with_metadata("qual o faturamento total em fevereiro de 2026?")

    assert result.cached is False
    assert result.response_id == question_id
    upsert.assert_not_awaited()
    link.assert_not_awaited()
    conn.fetchval.assert_not_awaited()
