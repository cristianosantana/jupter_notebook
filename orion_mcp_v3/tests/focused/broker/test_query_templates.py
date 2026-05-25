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
    executor = AnalyticsExecutor(mysql, ANALYTICS_ALLOWLIST)

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
            tpl.sql, params=("2026-01-01", "2026-06-01", "2026-01-01", "2026-06-01")
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
    }
    assert set(ANALYTICS_TEMPLATES.slugs) == expected


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
