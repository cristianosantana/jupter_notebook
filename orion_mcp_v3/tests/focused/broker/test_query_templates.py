"""Testes para QueryTemplateRegistry, matching heurístico e integração com executor/expander."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from orion_mcp_v3.broker.query_templates import (
    ANALYTICS_TEMPLATES,
    QueryTemplate,
    QueryTemplateRegistry,
)
from orion_mcp_v3.broker.query_capability_catalog import build_query_capability_catalog
from orion_mcp_v3.broker.query_collections import ANALYTICS_COLLECTIONS, FECHAMENTO_GERENCIAL_TEMPLATES
from orion_mcp_v3.broker.executor import AnalyticsExecutor
from orion_mcp_v3.broker.query_expander import QueryExpander
from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST
from orion_mcp_v3.contracts.cognitive_plan import (
    AttentionProfile,
    CognitivePlan,
    IntentType,
)
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy


def _analytical_plan(**overrides) -> CognitivePlan:  # type: ignore[no-untyped-def]
    defaults = {
        "intent_type": IntentType.ANALYTICAL,
        "needs_analytics": True,
        "confidence": 0.9,
        "retrieval_strategy": RetrievalStrategy.BROKER_FANOUT,
        "attention_profile": AttentionProfile.ANALYTICAL,
    }
    defaults.update(overrides)
    return CognitivePlan(**defaults)


# ---------------------------------------------------------------------------
# Registry match
# ---------------------------------------------------------------------------


def test_registry_match_faturamento_diario() -> None:
    cp = _analytical_plan(
        metrics=("receita", "faturamento"),
        needs_temporal_context=True,
    )
    tpl = ANALYTICS_TEMPLATES.match(cp)
    assert tpl is not None
    assert tpl.slug == "faturamento_diario"


def test_registry_match_vendedor() -> None:
    cp = _analytical_plan(
        entities=("vendedor",),
        metrics=("faturamento",),
    )
    tpl = ANALYTICS_TEMPLATES.match(cp)
    assert tpl is not None
    assert tpl.slug == "performance_vendedor"


def test_registry_match_concessionaria() -> None:
    cp = _analytical_plan(
        entities=("concessionária",),
        metrics=("faturamento",),
        needs_comparison=True,
    )
    tpl = ANALYTICS_TEMPLATES.match(cp)
    assert tpl is not None
    assert tpl.slug == "performance_concessionaria"


def test_registry_match_formas_pagamento() -> None:
    cp = _analytical_plan(
        entities=("pagamento",),
        metrics=("receita",),
    )
    tpl = ANALYTICS_TEMPLATES.match(cp)
    assert tpl is not None
    assert tpl.slug == "formas_pagamento"


def test_registry_no_match_conversational() -> None:
    cp = CognitivePlan(intent_type=IntentType.CONVERSATIONAL)
    tpl = ANALYTICS_TEMPLATES.match(cp)
    assert tpl is None


# ---------------------------------------------------------------------------
# resolve_params
# ---------------------------------------------------------------------------


def test_resolve_params_with_defaults() -> None:
    from datetime import date, timedelta

    tpl = ANALYTICS_TEMPLATES.get("faturamento_diario")
    assert tpl is not None
    cp = _analytical_plan()
    params = ANALYTICS_TEMPLATES.resolve_params(tpl, cp)
    expected_from = (date.today() - timedelta(days=30)).isoformat()
    expected_to = (date.today() + timedelta(days=1)).isoformat()
    assert params == {"date_from": expected_from, "date_to": expected_to}


def test_resolve_params_with_overrides() -> None:
    tpl = ANALYTICS_TEMPLATES.get("faturamento_diario")
    assert tpl is not None
    cp = _analytical_plan(time_scope="2026-01-01/2026-06-01")
    params = ANALYTICS_TEMPLATES.resolve_params(
        tpl, cp, overrides={"date_to": "2026-07-01"}
    )
    assert params["date_from"] == "2026-01-01"
    assert params["date_to"] == "2026-07-01"


def test_resolve_params_uses_explicit_month_range_from_intent_resolver() -> None:
    from orion_mcp_v3.runtime.intent_resolver import IntentResolver

    tpl = ANALYTICS_TEMPLATES.get("formas_pagamento")
    assert tpl is not None
    cp = IntentResolver().resolve(
        "Qual forma de pagamento domina entre janeiro e abril de 2026?",
    )
    params = ANALYTICS_TEMPLATES.resolve_params(tpl, cp)
    assert params["date_from"] == "2026-01-01"
    assert params["date_to"] == "2026-04-30"


def test_resolve_params_uses_explicit_numeric_range_from_intent_resolver() -> None:
    from orion_mcp_v3.runtime.intent_resolver import IntentResolver

    tpl = ANALYTICS_TEMPLATES.get("faturamento_diario")
    assert tpl is not None
    cp = IntentResolver().resolve("Mostre o faturamento de 01/01/2026 a 30/04/2026")
    params = ANALYTICS_TEMPLATES.resolve_params(tpl, cp)
    assert params["date_from"] == "2026-01-01"
    assert params["date_to"] == "2026-04-30"


# ---------------------------------------------------------------------------
# execute_template
# ---------------------------------------------------------------------------


def test_execute_template() -> None:
    mysql = MagicMock()
    rows = [{"data_pagamento": "2026-05-01", "valor_total_recebido": 1500.0}]
    mysql.select = AsyncMock(return_value=rows)
    executor = AnalyticsExecutor(mysql, ANALYTICS_ALLOWLIST, timeout=10.0)

    tpl = ANALYTICS_TEMPLATES.get("faturamento_diario")
    assert tpl is not None

    async def run() -> None:
        result = await executor.execute_template(
            tpl, {"date_from": "2026-01-01", "date_to": "2026-06-01"}
        )
        assert result.row_count == 1
        assert result.rows == rows
        assert result.plan.intent_slug == "template.faturamento_diario"
        assert "template_slug" in result.plan.hints
        mysql.select.assert_awaited_once_with(
            tpl.sql, 
            params=("2026-01-01", "2026-06-01", "2026-01-01", "2026-06-01"), 
            timeout=10.0
        )

    asyncio.run(run())


# ---------------------------------------------------------------------------
# QueryExpander com registry
# ---------------------------------------------------------------------------


def test_expander_with_registry() -> None:
    cp = _analytical_plan(
        metrics=("receita", "faturamento"),
        needs_temporal_context=True,
    )
    expander = QueryExpander(registry=ANALYTICS_TEMPLATES)
    plans = expander.expand(cp, ANALYTICS_ALLOWLIST)
    assert len(plans) >= 1
    assert any("_template" in p.hints for p in plans)
    assert plans[0].intent_slug.startswith("template.")


def test_expander_prefers_validated_template_from_intent_contract() -> None:
    cp = _analytical_plan(
        metrics=("vendas",),
        entities=("vendedor",),
        hints={
            "template_slug": "performance_vendedor",
            "intent_contract": {
                "template_slug": "performance_vendedor",
                "metric": "vendas",
                "dimension": "vendedor",
                "operation": "ranking_desc",
            },
        },
    )

    plans = QueryExpander(registry=ANALYTICS_TEMPLATES).expand(
        cp,
        ANALYTICS_ALLOWLIST,
        query_text="qual vendedor vendeu mais?",
    )

    assert len(plans) == 1
    assert plans[0].intent_slug == "template.performance_vendedor"
    assert plans[0].hints["template_slug"] == "performance_vendedor"
    assert plans[0].hints["selected_metric"] == "vendas"
    assert plans[0].hints["selected_dimension"] == "vendedor"
    assert plans[0].hints["selected_operation"] == "ranking_desc"
    assert plans[0].hints["semantic_reason"] == "validated_intent_contract"


def test_expander_collection_fanout_overrides_llm_selection_for_broad_fechamento() -> None:
    cp = _analytical_plan(
        metrics=("total",),
        entities=("periodo",),
        time_scope="2026-05-01/2026-05-31",
        hints={
            "template_slug": "formas_pagamento",
            "selected_metric": "total",
            "selected_dimension": "periodo",
            "selected_operation": "list",
            "semantic_reason": "llm_query_selector",
        },
    )

    plans = QueryExpander(registry=ANALYTICS_TEMPLATES).expand(
        cp,
        ANALYTICS_ALLOWLIST,
        query_text="Faca o fechamento gerencial de maio de 2026.",
    )

    assert [p.hints["template_slug"] for p in plans] == list(FECHAMENTO_GERENCIAL_TEMPLATES)
    assert {p.hints["collection_slug"] for p in plans} == {"fechamento_gerencial_por_mes"}
    assert {p.hints["semantic_reason"] for p in plans} == {"collection_fanout"}
    dimensions_by_slug = {p.hints["template_slug"]: p.hints["selected_dimension"] for p in plans}
    assert dimensions_by_slug == {
        "fechamento_faturamento_comissao_concessionaria_periodo": "concessionaria",
        "fechamento_faturamento_comissao_tipo_os_concessionaria_periodo": "concessionaria",
        "fechamento_producao_servico": "servico",
        "fechamento_producao_produto": "produto",
        "fechamento_faturamento_tipo_pagamento": "caixa_tipo",
        "fechamento_faturamento_tipo_venda": "os_tipo",
        "fechamento_faturamento_tipo_venda_produtos": "os_tipo",
        "fechamento_parcelamento_cartao": "parcelas",
        "fechamento_taxas_cartao_credito": "empresa_nome",
    }
    assert "periodo" not in dimensions_by_slug.values()
    metrics_by_slug = {p.hints["template_slug"]: p.hints["selected_metric"] for p in plans}
    assert metrics_by_slug == {
        "fechamento_faturamento_comissao_concessionaria_periodo": "total_comissao",
        "fechamento_faturamento_comissao_tipo_os_concessionaria_periodo": "total_comissao",
        "fechamento_producao_servico": "total",
        "fechamento_producao_produto": "total",
        "fechamento_faturamento_tipo_pagamento": "total_liquido",
        "fechamento_faturamento_tipo_venda": "total",
        "fechamento_faturamento_tipo_venda_produtos": "total",
        "fechamento_parcelamento_cartao": "total",
        "fechamento_taxas_cartao_credito": "valor_taxa",
    }


def test_expander_prefers_explicit_collection_slug_from_selector() -> None:
    cp = _analytical_plan(
        metrics=("total",),
        entities=("periodo",),
        time_scope="2026-01-01/2026-01-31",
        hints={
            "collection_slug": "fechamento_gerencial_por_mes",
            "selected_operation": "list",
            "semantic_reason": "llm_collection_selector",
        },
    )

    plans = QueryExpander(registry=ANALYTICS_TEMPLATES).expand(
        cp,
        ANALYTICS_ALLOWLIST,
        query_text="quero o relatório executivo mensal consolidado de janeiro",
    )

    assert [p.hints["template_slug"] for p in plans] == list(FECHAMENTO_GERENCIAL_TEMPLATES)
    assert {p.hints["collection_slug"] for p in plans} == {"fechamento_gerencial_por_mes"}
    assert {p.hints["semantic_reason"] for p in plans} == {"collection_fanout"}


def test_query_collection_catalog_selects_specific_subset() -> None:
    collection = ANALYTICS_COLLECTIONS.get("fechamento_gerencial_por_mes")
    assert collection is not None

    assert collection.matched_template_slugs(
        "No fechamento gerencial de maio, quanto foi produzido por serviço?",
    ) == ("fechamento_producao_servico",)


def test_expander_without_registry_keeps_compiled_path() -> None:
    cp = _analytical_plan(
        metrics=("faturamento",),
        needs_temporal_context=True,
    )
    expander = QueryExpander()
    plans = expander.expand(cp, ANALYTICS_ALLOWLIST)
    assert len(plans) >= 1
    assert all("_template" not in p.hints for p in plans)


# ---------------------------------------------------------------------------
# Registos internos
# ---------------------------------------------------------------------------


def test_all_templates_registered() -> None:
    expected = {
        "faturamento_diario",
        "performance_concessionaria",
        "performance_vendedor",
        "formas_pagamento",
        "itens_vendidos",
        *FECHAMENTO_GERENCIAL_TEMPLATES,
    }
    assert set(ANALYTICS_TEMPLATES.slugs) == expected


def test_itens_vendidos_template_contract() -> None:
    tpl = ANALYTICS_TEMPLATES.get("itens_vendidos")
    assert tpl is not None

    cp = _analytical_plan(time_scope="2026-03-01/2026-04-30")
    params = ANALYTICS_TEMPLATES.resolve_params(tpl, cp)

    assert tpl.sql.count("%s") == len(tpl.parameters)
    assert tpl.parameters == ("date_from", "date_to", "date_from", "date_to")
    assert params == {"date_from": "2026-03-01", "date_to": "2026-04-30"}
    assert tpl.value_key == "vendas"
    assert tpl.time_key == "periodo"
    assert tpl.grain == "month"
    assert tpl.label_key == "item"
    assert "AVG(ticket_medio_item)" not in tpl.sql
    assert "SUM(vendas) / SUM(quantidade_vendida)" in tpl.sql
    assert "DATE_FORMAT(os.created_at, '%%Y-%%m')" in tpl.sql


def test_fechamento_faturamento_comissao_templates_use_period_aware_slugs() -> None:
    consolidated_slug = "fechamento_faturamento_comissao_concessionaria_periodo"
    detail_slug = "fechamento_faturamento_comissao_tipo_os_concessionaria_periodo"

    assert ANALYTICS_TEMPLATES.get("fechamento_comissao_concessionaria_servicos") is None
    assert ANALYTICS_TEMPLATES.get("fechamento_comissao_concessionaria_tipos") is None

    consolidated = ANALYTICS_TEMPLATES.get(consolidated_slug)
    detail = ANALYTICS_TEMPLATES.get(detail_slug)
    assert consolidated is not None
    assert detail is not None

    assert consolidated.time_key == "periodo"
    assert consolidated.grain == "month"
    assert consolidated.label_key == "concessionaria"
    assert consolidated.value_key == "total_comissao"
    assert "DATE_FORMAT(os.data_pagamento, '%%Y-%%m') AS periodo" in consolidated.sql
    assert "total_faturamento" in consolidated.capability.measures
    assert "total_comissao" in consolidated.capability.measures

    assert detail.time_key == "periodo"
    assert detail.grain == "month"
    assert detail.label_key == "concessionaria"
    assert detail.value_key == "total_comissao"
    assert "DATE_FORMAT(os.data_pagamento, '%%Y-%%m') AS periodo" in detail.sql
    assert "comissao_venda_normal" in detail.capability.measures
    assert "comissao_financiamento" in detail.capability.measures
    assert "total_comissao" in detail.capability.measures


def test_fechamento_gerencial_templates_follow_reference_sql_period_contract() -> None:
    period_aware_slugs = (
        "fechamento_faturamento_tipo_pagamento",
        "fechamento_faturamento_tipo_venda",
        "fechamento_faturamento_tipo_venda_produtos",
        "fechamento_parcelamento_cartao",
        "fechamento_producao_produto",
        "fechamento_producao_servico",
    )

    for slug in period_aware_slugs:
        tpl = ANALYTICS_TEMPLATES.get(slug)
        assert tpl is not None
        assert tpl.time_key == "periodo"
        assert tpl.grain == "month"
        assert "periodo" in tpl.capability.dimensions
        assert " AS periodo" in tpl.sql

    tipo_pagamento = ANALYTICS_TEMPLATES.get("fechamento_faturamento_tipo_pagamento")
    assert tipo_pagamento is not None
    assert "AND os.os_tipo_id IN (1, 2, 3, 4, 5, 11)" in tipo_pagamento.sql

    venda_produtos = ANALYTICS_TEMPLATES.get("fechamento_faturamento_tipo_venda_produtos")
    assert venda_produtos is not None
    assert venda_produtos.label_key == "os_tipo"
    assert venda_produtos.capability.default_dimension == "os_tipo"
    assert "ost.nome AS os_tipo" in venda_produtos.sql


def test_fechamento_taxas_cartao_credito_matches_grouped_reference_contract() -> None:
    tpl = ANALYTICS_TEMPLATES.get("fechamento_taxas_cartao_credito")

    assert tpl is not None
    assert "con_fin.quantidade_parcelas" not in tpl.sql
    assert "GROUP BY empresa_id, bandeira, quantidade_parcelas" not in tpl.sql
    assert "GROUP BY empresa_id" in tpl.sql
    assert "quantidade_parcelas" not in tpl.capability.dimensions


def test_capability_catalog_exposes_semantic_view_details() -> None:
    catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)
    entry = next(e for e in catalog.entries if e.template_slug == "performance_concessionaria")
    prompt_entry = entry.as_prompt_dict()

    assert entry.grain == "month"
    assert entry.time_key == "periodo"
    assert "qual concessionária fatura mais" in entry.descriptions
    assert prompt_entry["metrics"]["vendas"]["kind"] == "money"
    assert prompt_entry["metrics"]["ticket_medio_os"]["additive"] is False
    assert prompt_entry["dimensions"]["concessionaria"]["label"] == "concessionária"


def test_capability_catalog_builds_query_cards_for_selector() -> None:
    catalog = build_query_capability_catalog(ANALYTICS_TEMPLATES)
    cards = {card.template_slug: card for card in catalog.query_cards()}

    vendedor = cards["performance_vendedor"]
    formas = cards["formas_pagamento"]
    itens = cards["itens_vendidos"]

    assert "vendedor" in vendedor.dimensions
    assert "vendas" in vendedor.metrics
    assert any("ranking de vendedores" in item for item in vendedor.descriptions)
    assert "periodo" in formas.dimensions
    assert "pix" in formas.metrics
    assert any("forma de pagamento" in item for item in formas.descriptions)
    assert itens.default_metric == "vendas"
    assert itens.default_dimension == "item"
    assert itens.grain == "month"
    assert itens.time_key == "periodo"
    assert "item" in itens.dimensions
    assert "categoria" in itens.dimensions
    assert "ticket_medio_item" in itens.metrics
    assert any("itens" in item for item in itens.descriptions)


def test_template_sql_contains_placeholders() -> None:
    for slug in ANALYTICS_TEMPLATES.slugs:
        tpl = ANALYTICS_TEMPLATES.get(slug)
        assert tpl is not None
        assert "%s" in tpl.sql, f"Template {slug} sem placeholders %s"
        assert tpl.sql.count("%s") == len(tpl.parameters)


# ---------------------------------------------------------------------------
# Matching via query_text
# ---------------------------------------------------------------------------


def test_score_with_query_text_match() -> None:
    """Matching via texto da pergunta — 'forma de pagamento' deve activar formas_pagamento."""
    cp = _analytical_plan(metrics=(), entities=())
    tpl = ANALYTICS_TEMPLATES.match(
        cp,
        query_text="qual forma de pagamento domina o faturamento",
    )
    assert tpl is not None
    assert tpl.slug == "formas_pagamento"


def test_score_with_query_text_vendedor() -> None:
    cp = _analytical_plan(metrics=(), entities=())
    tpl = ANALYTICS_TEMPLATES.match(
        cp,
        query_text="ranking de vendedores este mês",
    )
    assert tpl is not None
    assert tpl.slug == "performance_vendedor"


# ---------------------------------------------------------------------------
# Métricas bilingues
# ---------------------------------------------------------------------------


def test_score_bilingual_metrics() -> None:
    """Métricas EN ('revenue') devem pontuar templates PT via sinónimos."""
    cp = _analytical_plan(metrics=("revenue",))
    matched = ANALYTICS_TEMPLATES.match_all(cp)
    assert len(matched) >= 1
    slugs = [t.slug for t in matched]
    assert "faturamento_diario" in slugs


def test_score_bilingual_sales() -> None:
    cp = _analytical_plan(metrics=("sales",))
    matched = ANALYTICS_TEMPLATES.match_all(cp)
    assert len(matched) >= 1
    slugs = [t.slug for t in matched]
    assert "performance_vendedor" in slugs
