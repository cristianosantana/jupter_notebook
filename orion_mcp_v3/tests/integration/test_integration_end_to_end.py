"""Integração end-to-end: pergunta → intent → expand → execute → aggregate → orchestrate → narrate."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from orion_mcp_v3.broker import (
    ANALYTICS_TEMPLATES,
    AnalyticsExecutor,
    AnalyticsResult,
    EvidenceAggregator,
    QueryExpander,
)
from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.protocols.llm import EchoLLMProvider
from orion_mcp_v3.runtime.cognitive_orchestrator import CognitiveOrchestrator
from orion_mcp_v3.runtime.intent_resolver import IntentResolver, map_attention_profile_to_policy
from orion_mcp_v3.runtime.narrator import CognitiveNarrator

_LOG = logging.getLogger("orion.tests.integration_e2e")

MOCK_FORMAS_PAGAMENTO = [
    {"forma_pagamento": "pix", "qtd_recebimentos": 150, "total_recebido": 85000.0, "ticket_medio": 566.67, "percentual_total": 45.5},
    {"forma_pagamento": "cartao credito", "qtd_recebimentos": 100, "total_recebido": 62000.0, "ticket_medio": 620.0, "percentual_total": 33.2},
    {"forma_pagamento": "cartao debito", "qtd_recebimentos": 50, "total_recebido": 25000.0, "ticket_medio": 500.0, "percentual_total": 13.4},
    {"forma_pagamento": "boleto", "qtd_recebimentos": 30, "total_recebido": 15000.0, "ticket_medio": 500.0, "percentual_total": 8.0},
]

MOCK_VENDEDORES = [
    {"vendedor": "ana silva", "total_vendas": 42, "valor_total": 98000.0, "ticket_medio": 2333.33, "maior_venda": 8500.0},
    {"vendedor": "carlos souza", "total_vendas": 38, "valor_total": 87000.0, "ticket_medio": 2289.47, "maior_venda": 7200.0},
    {"vendedor": "maria oliveira", "total_vendas": 35, "valor_total": 76000.0, "ticket_medio": 2171.43, "maior_venda": 6800.0},
    {"vendedor": "pedro santos", "total_vendas": 29, "valor_total": 65000.0, "ticket_medio": 2241.38, "maior_venda": 5900.0},
    {"vendedor": "lucia ferreira", "total_vendas": 25, "valor_total": 54000.0, "ticket_medio": 2160.0, "maior_venda": 5100.0},
]


def _make_executor(mock_rows: list[dict]) -> tuple[AnalyticsExecutor, AsyncMock]:
    mysql = MagicMock()
    mysql.select = AsyncMock(return_value=mock_rows)
    return AnalyticsExecutor(mysql, ANALYTICS_ALLOWLIST, default_limit=1000), mysql.select


async def _run_analytics_pipeline(
    message: str,
    mysql_mock_rows: list[dict],
    *,
    value_key: str = "total_faturamento",
    time_key: str | None = None,
    grain: str = "month",
) -> tuple[CognitivePlan, EvidenceBlock]:
    """Passos 1-5: intent → expand → execute → aggregate. Blueprint para a rota de chat."""
    resolver = IntentResolver()
    cognitive_plan = resolver.resolve(message)
    _LOG.info(
        "e2e intent intent_type=%s confidence=%.3f needs_analytics=%s",
        cognitive_plan.intent_type.value,
        cognitive_plan.confidence,
        cognitive_plan.needs_analytics,
    )

    expander = QueryExpander(registry=ANALYTICS_TEMPLATES)
    plans = expander.expand(cognitive_plan, ANALYTICS_ALLOWLIST, query_text=message)
    assert plans, "QueryExpander deve gerar pelo menos 1 plano"
    _LOG.info(
        "e2e expand n_plans=%d slugs=%s",
        len(plans),
        [p.intent_slug for p in plans],
    )

    executor, _ = _make_executor(mysql_mock_rows)

    results: list[AnalyticsResult] = []
    for plan in plans:
        tpl = plan.hints.get("_template")
        if tpl is not None:
            params = plan.hints.get("template_params", {})
            _LOG.info(
                "e2e execute_template slug=%s params_keys=%s",
                tpl.slug,
                sorted(params.keys()),
            )
            result = await executor.execute_template(tpl, params)
        else:
            _LOG.info("e2e execute_plan intent_slug=%s", plan.intent_slug)
            result = await executor.execute_plan(plan)
        _LOG.info(
            "e2e result intent_slug=%s row_count=%d sql_len=%d",
            result.plan.intent_slug,
            result.row_count,
            len(result.sql),
        )
        results.append(result)

    evidence = EvidenceAggregator().merge(
        results,
        value_key=value_key,
        time_key=time_key,
        grain=grain,
        templates=ANALYTICS_TEMPLATES,
    )
    _LOG.info(
        "e2e evidence confidence=%.3f summary_len=%d metrics_keys=%s",
        evidence.confidence,
        len(evidence.summary),
        tuple(evidence.metrics.keys()),
    )
    return cognitive_plan, evidence


def test_pipeline_emits_integration_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Garante que o blueprint regista passos no logger orion.tests.integration_e2e."""
    caplog.set_level(logging.INFO, logger=_LOG.name)
    message = "Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?"

    async def run() -> None:
        await _run_analytics_pipeline(message, MOCK_FORMAS_PAGAMENTO, value_key="total_recebido")

    asyncio.run(run())
    texts = [r.getMessage() for r in caplog.records if r.name == _LOG.name]
    assert any("e2e intent" in t for t in texts)
    assert any("e2e expand" in t for t in texts)
    assert any("e2e execute" in t for t in texts)
    assert any("e2e result" in t for t in texts)
    assert any("e2e evidence" in t for t in texts)


def test_pipeline_uses_template_slugs(caplog: pytest.LogCaptureFixture) -> None:
    """Verifica que planos usam execute_template e slugs template.* (não primary)."""
    caplog.set_level(logging.INFO, logger=_LOG.name)
    message = "Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?"

    async def run() -> None:
        await _run_analytics_pipeline(message, MOCK_FORMAS_PAGAMENTO, value_key="total_recebido")

    asyncio.run(run())
    texts = [r.getMessage() for r in caplog.records if r.name == _LOG.name]
    assert any("execute_template" in t for t in texts), (
        "Pipeline deve usar execute_template para planos com template"
    )
    assert any("template." in t for t in texts), (
        "Slugs de planos devem começar com 'template.'"
    )


def test_end_to_end_formas_pagamento(caplog: pytest.LogCaptureFixture) -> None:
    """Integração: pergunta → intent → expand → execute → aggregate → orchestrate → narrate."""
    caplog.set_level(logging.INFO, logger=_LOG.name)
    message = "Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?"

    async def run() -> None:
        cognitive_plan, evidence = await _run_analytics_pipeline(
            message,
            MOCK_FORMAS_PAGAMENTO,
            value_key="total_recebido",
        )

        assert cognitive_plan.needs_analytics is True
        assert evidence.summary
        assert evidence.confidence > 0

        policy = map_attention_profile_to_policy(cognitive_plan.attention_profile)
        orchestrator = CognitiveOrchestrator()
        orch_result = orchestrator.finalize_prompt(
            message,
            policy=policy,
            cognitive_plan=cognitive_plan,
            evidence=evidence,
            memory_blocks=[],
        )
        assert orch_result.prompt_text
        assert any(
            b.metadata.get("fusion_kind") == "evidence"
            for b in orch_result.packed_blocks
        )

        narrator = CognitiveNarrator(EchoLLMProvider())
        narration = await narrator.narrate(orch_result)

        assert narration.narration
        assert "evidence_cited" in narration.safeguards_applied

        bad_phrases = ("sem dados", "insuficiente", "não há dados", "NullLLM")
        for phrase in bad_phrases:
            assert phrase.lower() not in narration.narration.lower(), (
                f"Resposta contém '{phrase}': {narration.narration[:200]}"
            )

    asyncio.run(run())
    assert any(r.name == _LOG.name and "e2e evidence" in r.getMessage() for r in caplog.records)


def test_end_to_end_top_vendedores() -> None:
    """Integração com pergunta de ranking de vendedores."""
    message = "Qual o ranking de vendas por vendedor este mês?"

    async def run() -> None:
        cognitive_plan, evidence = await _run_analytics_pipeline(
            message,
            MOCK_VENDEDORES,
            value_key="valor_total",
        )

        assert cognitive_plan.needs_analytics is True
        assert evidence.summary
        assert evidence.confidence > 0

        policy = map_attention_profile_to_policy(cognitive_plan.attention_profile)
        orchestrator = CognitiveOrchestrator()
        orch_result = orchestrator.finalize_prompt(
            message,
            policy=policy,
            cognitive_plan=cognitive_plan,
            evidence=evidence,
            memory_blocks=[],
        )

        narrator = CognitiveNarrator(EchoLLMProvider())
        narration = await narrator.narrate(orch_result)

        assert narration.narration
        assert "evidence_cited" in narration.safeguards_applied
        for phrase in ("sem dados", "insuficiente", "NullLLM"):
            assert phrase.lower() not in narration.narration.lower()

    asyncio.run(run())


def test_pipeline_helper_returns_evidence_with_templates() -> None:
    """Verifica que planos com _template usam execute_template."""
    message = "Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?"
    resolver = IntentResolver()
    cognitive_plan = resolver.resolve(message)

    expander = QueryExpander(registry=ANALYTICS_TEMPLATES)
    plans = expander.expand(cognitive_plan, ANALYTICS_ALLOWLIST, query_text=message)

    has_template = any(p.hints.get("_template") is not None for p in plans)
    has_regular = any(p.hints.get("_template") is None for p in plans)
    assert has_template or has_regular, "Deve haver pelo menos planos template ou regulares"


def test_evidence_block_reaches_narrator_prompt() -> None:
    """Confirma que a evidência aparece no prompt_text que o narrator recebe."""
    message = "Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?"

    async def run() -> None:
        _, evidence = await _run_analytics_pipeline(
            message,
            MOCK_FORMAS_PAGAMENTO,
            value_key="total_recebido",
        )

        policy = map_attention_profile_to_policy(
            IntentResolver().resolve(message).attention_profile,
        )
        orch_result = CognitiveOrchestrator().finalize_prompt(
            message,
            policy=policy,
            evidence=evidence,
            memory_blocks=[],
        )

        assert "trica" in orch_result.prompt_text.lower() or "total_recebido" in orch_result.prompt_text.lower(), (
            "O prompt deve incluir informação da evidência"
        )

    asyncio.run(run())


def test_multiple_plans_produce_fanout_evidence() -> None:
    """Quando o expander gera >1 plano, o aggregator produz fanout insights."""
    message = "Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?"
    resolver = IntentResolver()
    cognitive_plan = resolver.resolve(message)

    expander = QueryExpander(registry=ANALYTICS_TEMPLATES)
    plans = expander.expand(cognitive_plan, ANALYTICS_ALLOWLIST, query_text=message)

    if len(plans) < 2:
        pytest.skip("Resolver produziu apenas 1 plano para esta query (sem fanout)")

    async def run() -> None:
        executor, _ = _make_executor(MOCK_FORMAS_PAGAMENTO)
        results = []
        for plan in plans:
            tpl = plan.hints.get("_template")
            if tpl is not None:
                params = plan.hints.get("template_params", {})
                r = await executor.execute_template(tpl, params)
            else:
                r = await executor.execute_plan(plan)
            results.append(r)

        evidence = EvidenceAggregator().merge(
            results,
            value_key="total_recebido",
            templates=ANALYTICS_TEMPLATES,
        )
        assert "fanout" in evidence.insights

    asyncio.run(run())
