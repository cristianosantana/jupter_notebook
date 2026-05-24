"""Resolução de :class:`~EvidenceSeriesSpec` por template vs plano compilado."""

from __future__ import annotations

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES, AnalyticsResult, EvidenceAggregator
from orion_mcp_v3.broker.evidence_series_resolve import (
    infer_value_key_from_compiled_plan,
    resolve_evidence_series_specs,
)
from orion_mcp_v3.contracts.evidence_series_spec import EvidenceSeriesSpec
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan


def _tpl_plan(slug: str, tpl: object) -> SemanticQueryPlan:
    return SemanticQueryPlan(
        intent_slug=f"template.{slug}",
        strategy=RetrievalStrategy.BROKER_FANOUT,
        hints={"_template": tpl, "template_slug": slug, "template_params": {}},
    )


def test_resolve_specs_use_per_template_value_keys() -> None:
    reg = ANALYTICS_TEMPLATES
    tpl_fat = reg.get("faturamento_diario")
    tpl_fp = reg.get("formas_pagamento")
    assert tpl_fat is not None and tpl_fp is not None

    p0 = _tpl_plan("faturamento_diario", tpl_fat)
    p1 = _tpl_plan("formas_pagamento", tpl_fp)

    r0 = AnalyticsResult(
        plan=p0,
        sql="s0",
        rows=[{"valor_total_recebido": 10.0, "data_pagamento": "2026-01-01"}],
        row_count=1,
    )
    r1 = AnalyticsResult(
        plan=p1,
        sql="s1",
        rows=[{"total": 99.0, "periodo": "2026-01"}],
        row_count=1,
    )

    specs = resolve_evidence_series_specs(
        (r0, r1),
        templates=reg,
        default_value_key="wrong_default",
    )
    assert specs[0].value_key == "valor_total_recebido"
    assert specs[0].time_key == "data_pagamento"
    assert specs[0].label_key is None
    assert specs[1].value_key == "total"
    assert specs[1].time_key == "periodo"
    assert specs[1].label_key == "periodo"

    block = EvidenceAggregator().merge((r0, r1), templates=reg, value_key="wrong_default")
    assert "total" in block.summary.lower() or "99" in block.summary
    assert "valor_total_recebido" in block.summary.lower() or "10" in block.summary
    assert "Sem valores numéricos" not in block.summary


def test_infer_value_key_sql_order_by_alias() -> None:
    plan = SemanticQueryPlan(
        intent_slug="primary",
        strategy=RetrievalStrategy.BROKER_FANOUT,
        hints={"sql_order_by": {"alias": "my_total"}},
    )
    r = AnalyticsResult(plan=plan, sql="x", rows=[{"my_total": 1.0}], row_count=1)
    assert infer_value_key_from_compiled_plan(r, default="total_faturamento") == "my_total"


def test_merge_accepts_explicit_series_specs() -> None:
    plan = SemanticQueryPlan(
        intent_slug="custom",
        strategy=RetrievalStrategy.BROKER_FANOUT,
        hints={},
    )
    r = AnalyticsResult(plan=plan, sql="x", rows=[{"x_metric": 5.0}], row_count=1)
    spec = EvidenceSeriesSpec(value_key="x_metric", time_key=None, grain="total", intent_slug="custom")
    block = EvidenceAggregator().merge([r], series_specs=(spec,), value_key="ignored")
    assert "x_metric" in block.summary or "5" in block.summary
