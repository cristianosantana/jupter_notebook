from __future__ import annotations

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES, AnalyticsResult
from orion_mcp_v3.broker.answer_projector import build_projected_answer
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan
from orion_mcp_v3.runtime.intent_resolver import IntentResolver


def _result(slug: str, rows: list[dict]) -> AnalyticsResult:  # type: ignore[type-arg]
    return AnalyticsResult(
        plan=SemanticQueryPlan(
            intent_slug=f"template.{slug}",
            strategy=RetrievalStrategy.BROKER_FANOUT,
            hints={"template_slug": slug, "template_params": {}},
        ),
        sql="SELECT ...",
        rows=rows,
        row_count=len(rows),
    )


def test_performance_concessionaria_projects_top_and_bottom_sales() -> None:
    rows = [
        {
            "periodo": "04/2026",
            "concessionaria": "osaka",
            "quantidade_os": 176,
            "vendas": "187547.00",
            "ticket_medio_os": "1041.93",
            "recebido": "13020.00",
            "percentual_recebido": "6.94",
        },
        {
            "periodo": "04/2026",
            "concessionaria": "strada jeep",
            "quantidade_os": 261,
            "vendas": "112575.00",
            "ticket_medio_os": "428.04",
            "recebido": "9405.00",
            "percentual_recebido": "8.35",
        },
    ]

    projected = build_projected_answer(
        "Qual concessionária possui maior/menor receita em abril de 2026?",
        [_result("performance_concessionaria", rows)],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.plan.measure == "vendas"
    assert projected.plan.operation == "top_and_bottom"
    assert projected.top is not None
    assert projected.bottom is not None
    assert projected.top["concessionaria"] == "osaka"
    assert projected.bottom["concessionaria"] == "strada jeep"
    assert "Resposta direta" in projected.summary


def test_performance_vendedor_projects_ticket_not_total_value() -> None:
    rows = [
        {"vendedor": "ana", "quantidade_os": 10, "vendas": "10000.00", "ticket_medio_os": "1000.00"},
        {"vendedor": "bia", "quantidade_os": 20, "vendas": "12000.00", "ticket_medio_os": "600.00"},
    ]

    projected = build_projected_answer(
        "Qual o ticket médio por vendedor em abril de 2026?",
        [_result("performance_vendedor", rows)],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.plan.measure == "ticket_medio_os"
    assert projected.top is not None
    assert projected.top["vendedor"] == "ana"


def test_performance_vendedor_projects_sales_volume_not_revenue() -> None:
    rows = [
        {"vendedor": "ana", "quantidade_os": 10, "vendas": "20000.00", "ticket_medio_os": "2000.00"},
        {"vendedor": "bia", "quantidade_os": 20, "vendas": "12000.00", "ticket_medio_os": "600.00"},
    ]

    projected = build_projected_answer(
        "Qual vendedor tem maior volume de vendas em abril de 2026?",
        [_result("performance_vendedor", rows)],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.plan.measure == "quantidade_os"
    assert projected.top is not None
    assert projected.top["vendedor"] == "bia"


def test_performance_concessionaria_list_summary_materializes_ticket_values() -> None:
    rows = [
        {
            "periodo": "04/2026",
            "concessionaria": "osaka",
            "quantidade_os": 176,
            "vendas": "187547.00",
            "ticket_medio_os": "1041.93",
            "recebido": "13020.00",
            "percentual_recebido": "6.94",
        },
        {
            "periodo": "04/2026",
            "concessionaria": "distribuição ppf",
            "quantidade_os": 48,
            "vendas": "118669.99",
            "ticket_medio_os": "2282.12",
            "recebido": "7600.00",
            "percentual_recebido": "6.40",
        },
    ]

    projected = build_projected_answer(
        "Qual o ticket médio por concessionárias entre janeiro e abriu de 2026?",
        [_result("performance_concessionaria", rows)],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.plan.measure == "ticket_medio_os"
    assert projected.plan.operation == "list"
    assert "distribuição ppf: R$ 2.282,12" in projected.summary
    assert "osaka: R$ 1.041,93" in projected.summary
    assert "registro(s) projetados" not in projected.summary


def test_intent_resolver_accepts_common_april_typo() -> None:
    plan = IntentResolver().resolve("Qual concessionária possui maior/menor receita de abriu de 2026?")

    assert plan.time_scope == "2026-04-01/2026-04-30"
    assert plan.hints["date_from"] == "2026-04-01"
    assert plan.hints["date_to"] == "2026-04-30"


def test_receipt_question_is_analytical_without_policy_bias() -> None:
    plan = IntentResolver().resolve(
        "Qual o maior recebimento por concessionária entre janeiro e abriu de 2026?",
    )

    assert plan.needs_analytics is True
    assert plan.intent_type.value == "analytical"
    assert plan.metrics == ("revenue",)
    assert plan.entities == ("concessionária",)
    assert plan.time_scope == "2026-01-01/2026-04-30"


def test_analytical_policy_bias_helps_data_like_temporal_question() -> None:
    plan = IntentResolver().resolve(
        "maior por concessionária entre janeiro e abriu de 2026?",
        policy_request="analytical",
    )

    assert plan.needs_analytics is True
    assert plan.intent_type.value == "analytical"
    assert plan.hints["signals"]["policy_analytical_bias"] is True
    assert plan.time_scope == "2026-01-01/2026-04-30"


def test_analytical_policy_does_not_force_small_talk() -> None:
    plan = IntentResolver().resolve("bom dia", policy_request="analytical")

    assert plan.needs_analytics is False
    assert plan.intent_type.value == "conversational"


def test_comparative_sales_question_sets_needs_comparison() -> None:
    plan = IntentResolver().resolve(
        "faça uma comparação entre março e abriu de 2026? "
        "quero saber qual vendedor teve queda nas vendas e qual teve aumento",
        policy_request="memory_focused",
    )

    assert plan.intent_type.value == "comparative"
    assert plan.needs_analytics is True
    assert plan.needs_comparison is True
    assert plan.time_scope == "2026-03-01/2026-04-30"


def test_crossing_revenue_question_without_dates_is_comparative() -> None:
    plan = IntentResolver().resolve(
        "quero que vc cruze os faturamentos e me diga quais houve queda e quais subiram?",
        policy_request="analytical",
    )

    assert plan.intent_type.value == "comparative"
    assert plan.needs_analytics is True
    assert plan.needs_comparison is True
    assert plan.hints["signals"]["comparative"] is True
    assert plan.time_scope is None
