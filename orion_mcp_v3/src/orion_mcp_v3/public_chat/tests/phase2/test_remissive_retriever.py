from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract
from orion_mcp_v3.public_chat.domain.knowledge import AnswerPayload, ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.infrastructure.remissive_retriever import RemissiveRetriever


@pytest.mark.asyncio
async def test_retriever_returns_knowledge() -> None:
    reader = AsyncMock()
    reader.search_origin_ids.return_value = [(42, 0.12)]
    reader.load_hits_by_origin_ids.return_value = [
        KnowledgeHit(
            origin_id=42,
            context_key="financeiro:faturamento:2026-05",
            category="Financeiro",
            validated_answer="Faturamento validado.",
            key_metrics={"faturamento": 100.0},
            score=0.12,
        )
    ]

    retriever = RemissiveRetriever(reader)
    knowledge = await retriever.retrieve("faturamento maio")

    assert knowledge.has_hits
    assert knowledge.hits[0].origin_id == 42
    assert knowledge.hits[0].category == "Financeiro"


@pytest.mark.asyncio
async def test_reload_from_payload() -> None:
    reader = AsyncMock()
    reader.load_hits_by_origin_ids.return_value = [
        KnowledgeHit(
            origin_id=42,
            context_key="ctx",
            category="Financeiro",
            validated_answer="Resposta.",
            key_metrics={},
        )
    ]
    reader.load_essence_by_themes.return_value = []

    retriever = RemissiveRetriever(reader)
    knowledge = await retriever.reload_from_payload(
        AnswerPayload(context_keys=("ctx",), knowledge_ids=(42,), essence_themes=())
    )

    reader.load_hits_by_origin_ids.assert_awaited_once_with([42])
    assert knowledge.hits[0].origin_id == 42


@pytest.mark.asyncio
async def test_complete_period_evidence_adds_missing_period_with_same_metric_key() -> None:
    maio = KnowledgeHit(
        origin_id=34,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-05",
        category="Fechamento Gerencial",
        validated_answer="Maio.",
        key_metrics={"faturamento_por_tipo_de_venda": {"rows": [], "_meta": {}}},
    )
    abril = KnowledgeHit(
        origin_id=28,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Abril.",
        key_metrics={"faturamento_por_tipo_de_venda": {"rows": [], "_meta": {}}},
    )
    taxas = KnowledgeHit(
        origin_id=32,
        context_key="sistema_background:fechamento_gerencial:taxas_cartao_credito:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Taxas.",
        key_metrics={"taxas_cartao_credito": {"rows": [], "_meta": {}}},
    )
    reader = AsyncMock()
    reader.load_hits_by_theme_patterns.return_value = [taxas, abril, maio]
    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-04",
        operation="comparison",
        entity_filters=(EntityFilter(dimension="periodo", value="2026-05", match="exact"),),
        confidence=0.9,
    )

    retriever = RemissiveRetriever(reader)
    enriched = await retriever.complete_period_evidence(
        knowledge=ConhecimentoRecuperado(hits=(maio,)),
        contract=contract,
    )

    assert {hit.origin_id for hit in enriched.hits} == {28, 34}


@pytest.mark.asyncio
async def test_complete_period_evidence_uses_canonical_revenue_keys_not_cache_noise() -> None:
    maio_faturamento = KnowledgeHit(
        origin_id=34,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-05",
        category="Fechamento Gerencial",
        validated_answer="Maio.",
        key_metrics={"faturamento_por_tipo_de_venda": {"rows": [], "_meta": {}}},
    )
    maio_parcelamento = KnowledgeHit(
        origin_id=39,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-05",
        category="Fechamento Gerencial",
        validated_answer="Parcelamento maio.",
        key_metrics={"parcelamento_de_cartao": {"rows": [], "_meta": {}}},
    )
    abril_faturamento = KnowledgeHit(
        origin_id=28,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Abril.",
        key_metrics={"faturamento_por_tipo_de_venda": {"rows": [], "_meta": {}}},
    )
    abril_parcelamento = KnowledgeHit(
        origin_id=31,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Parcelamento abril.",
        key_metrics={"parcelamento_de_cartao": {"rows": [], "_meta": {}}},
    )
    reader = AsyncMock()
    reader.load_hits_by_context_key_patterns.return_value = [
        abril_faturamento,
        abril_parcelamento,
    ]
    reader.load_hits_by_theme_patterns.return_value = [
        abril_parcelamento,
        maio_parcelamento,
        maio_faturamento,
    ]
    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-04",
        operation="comparison",
        entity_filters=(EntityFilter(dimension="periodo", value="2026-05", match="exact"),),
        confidence=0.9,
    )

    retriever = RemissiveRetriever(reader)
    enriched = await retriever.complete_period_evidence(
        knowledge=ConhecimentoRecuperado(hits=(maio_faturamento, maio_parcelamento)),
        contract=contract,
    )

    assert {hit.origin_id for hit in enriched.hits} == {28, 34, 39}
    assert 31 not in {hit.origin_id for hit in enriched.hits}


@pytest.mark.asyncio
async def test_complete_period_evidence_adds_targeted_single_period_revenue_hit() -> None:
    fevereiro = KnowledgeHit(
        origin_id=10,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-02",
        category="Fechamento Gerencial",
        validated_answer="Fevereiro.",
        key_metrics={"faturamento_por_tipo_de_venda": {"rows": [], "_meta": {}}},
    )
    junho = KnowledgeHit(
        origin_id=42,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-06",
        category="Fechamento Gerencial",
        validated_answer="Junho.",
        key_metrics={"faturamento_por_tipo_de_venda": {"rows": [], "_meta": {}}},
    )
    reader = AsyncMock()
    reader.load_hits_by_context_key_patterns.return_value = [junho]
    reader.load_hits_by_theme_patterns.return_value = []
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-06",
        operation="summary",
        confidence=0.92,
    )

    retriever = RemissiveRetriever(reader)
    enriched = await retriever.complete_period_evidence(
        knowledge=ConhecimentoRecuperado(hits=(fevereiro,)),
        contract=contract,
    )

    assert {hit.origin_id for hit in enriched.hits} == {10, 42}


@pytest.mark.asyncio
async def test_complete_period_evidence_adds_comissao_janeiro_for_queda_query() -> None:
    """Token context_key mapeia faturamento_e_comissao_* → comissao_por_concessionaria."""
    maio = KnowledgeHit(
        origin_id=37,
        context_key="sistema_background:fechamento_gerencial:comissao_por_concessionaria:periodo-2026-05",
        category="Fechamento Gerencial",
        validated_answer="Maio.",
        key_metrics={"faturamento_e_comissao_por_concessionaria": {"rows": [], "_meta": {}}},
    )
    janeiro = KnowledgeHit(
        origin_id=4,
        context_key="sistema_background:fechamento_gerencial:comissao_por_concessionaria:periodo-2026-01",
        category="Fechamento Gerencial",
        validated_answer="Janeiro.",
        key_metrics={"faturamento_e_comissao_por_concessionaria": {"rows": [], "_meta": {}}},
    )
    reader = AsyncMock()
    reader.load_hits_by_context_key_patterns.return_value = [janeiro]
    reader.load_hits_by_theme_patterns.return_value = []
    contract = IntentContract(
        intent="consulta_metrica",
        metric="comissao",
        period="2026-01",
        operation="ranking_asc",
        dimension="concessionaria",
        entity_filters=(EntityFilter(dimension="periodo", value="2026-05", match="exact"),),
        confidence=0.75,
    )

    retriever = RemissiveRetriever(reader)
    enriched = await retriever.complete_period_evidence(
        knowledge=ConhecimentoRecuperado(hits=(maio,)),
        contract=contract,
    )

    assert {hit.origin_id for hit in enriched.hits} == {37, 4}
    patterns = reader.load_hits_by_context_key_patterns.await_args.args[0]
    assert any("comissao_por_concessionaria" in p and "2026-01" in p for p in patterns)


@pytest.mark.asyncio
async def test_complete_period_evidence_adds_parcelamento_for_parcelas_query() -> None:
    faturamento = KnowledgeHit(
        origin_id=25,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_forma_pagamento:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Abril.",
        key_metrics={"faturamento_por_tipo_de_pagamento": {"rows": [], "_meta": {}}},
    )
    parcelamento = KnowledgeHit(
        origin_id=31,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Parcelamento abril.",
        key_metrics={"parcelamento_de_cartao": {"rows": [], "_meta": {}}},
    )
    reader = AsyncMock()
    reader.load_hits_by_context_key_patterns.return_value = [parcelamento]
    reader.load_hits_by_theme_patterns.return_value = []
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-04",
        operation="summary",
        dimension="parcelas",
        entity_filters=(EntityFilter(dimension="parcelas", value="5X", match="contains"),),
        confidence=0.95,
    )

    retriever = RemissiveRetriever(reader)
    enriched = await retriever.complete_period_evidence(
        knowledge=ConhecimentoRecuperado(hits=(faturamento,)),
        contract=contract,
    )

    assert {hit.origin_id for hit in enriched.hits} == {25, 31}


@pytest.mark.asyncio
async def test_synonymy_via_remissive_on_miss() -> None:
    reader = AsyncMock()
    reader.search_origin_ids.side_effect = [
        [(42, 0.2)],
        [(42, 0.18)],
    ]
    reader.load_hits_by_origin_ids.return_value = [
        KnowledgeHit(
            origin_id=42,
            context_key="ctx",
            category="Financeiro",
            validated_answer="Mesmo conhecimento.",
            key_metrics={},
        )
    ]

    retriever = RemissiveRetriever(reader)
    first = await retriever.retrieve("Qual o faturamento de maio?")
    second = await retriever.retrieve("Quanto faturou em maio?")

    assert first.hits[0].origin_id == second.hits[0].origin_id == 42
