from __future__ import annotations

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES, AnalyticsResult, EvidenceAggregator
from orion_mcp_v3.broker.answer_projector import (
    build_full_section_detail,
    build_projected_answer,
    build_projected_answer_set,
)
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan
from orion_mcp_v3.runtime.intent_resolver import IntentResolver


def _result(
    slug: str,
    rows: list[dict],  # type: ignore[type-arg]
    *,
    hints: dict | None = None,  # type: ignore[type-arg]
) -> AnalyticsResult:
    return AnalyticsResult(
        plan=SemanticQueryPlan(
            intent_slug=f"template.{slug}",
            strategy=RetrievalStrategy.BROKER_FANOUT,
            hints={"template_slug": slug, "template_params": {}, **(hints or {})},
        ),
        sql="SELECT ...",
        rows=rows,
        row_count=len(rows),
    )


def _fechamento_result(slug: str, rows: list[dict]) -> AnalyticsResult:  # type: ignore[type-arg]
    return _result(
        slug,
        rows,
        hints={
            "collection_slug": "fechamento_gerencial_por_mes",
            "collection_presentation_mode": "sections",
            "selected_operation": "list",
            "result_scope": {"mode": "all", "limit": None},
        },
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


def test_fechamento_gerencial_projects_executive_contract_without_parallel_payload() -> None:
    projected = build_projected_answer_set(
        "Faça o fechamento gerencial de maio de 2026",
        [
            _fechamento_result(
                "fechamento_faturamento_tipo_pagamento",
                [
                    {
                        "caixa_tipo": "Cartão de Crédito",
                        "total_pagamentos": "1300.00",
                        "total_estornos": "100.00",
                        "total_liquido": "1200.00",
                    },
                    {
                        "caixa_tipo": "PIX",
                        "total_pagamentos": "500.00",
                        "total_estornos": "0.00",
                        "total_liquido": "500.00",
                    },
                ],
            ),
            _fechamento_result(
                "fechamento_faturamento_comissao_concessionaria_periodo",
                [
                    {"periodo": "2026-05", "concessionaria": "GWM BAMAQ", "total_faturamento": "900.00", "total_comissao": "90.00"},
                    {"periodo": "2026-05", "concessionaria": "STRADA JEEP", "total_faturamento": "600.00", "total_comissao": "60.00"},
                ],
            ),
            _fechamento_result(
                "fechamento_taxas_cartao_credito",
                [
                    {
                        "empresa_nome": "MFP ESTETICA AUTOMOTIVA",
                        "valor_bruto": "1200.00",
                        "valor_liquido": "1160.00",
                        "valor_taxa": "40.00",
                    }
                ],
            ),
        ],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    payload = projected.as_dict()
    assert payload["collection_slug"] == "fechamento_gerencial_por_mes"
    assert payload["headline"] == "Faturamento líquido por forma de pagamento: R$ 1.700,00"
    assert payload["managerial_totals"]["financial_net"]["source_template"] == "fechamento_faturamento_tipo_pagamento"
    assert payload["managerial_totals"]["financial_net"]["value"] == "R$ 1.700,00"
    assert payload["data_quality"]["templates_projected"] == 3
    assert payload["data_quality"]["rows_projected"] == 5
    assert payload["executive_summary"] == payload["summary"]
    assert "STRADA JEEP" not in payload["summary"]
    assert "STRADA JEEP" in payload["section_detail"]
    assert "PIX" in payload["section_detail"]

    sections = payload["executive_sections"]
    assert [section["template_slug"] for section in sections] == [
        "fechamento_faturamento_tipo_pagamento",
        "fechamento_faturamento_comissao_concessionaria_periodo",
        "fechamento_taxas_cartao_credito",
    ]
    assert sections[0]["top"] == "Cartão de Crédito"
    assert sections[0]["top_value"] == "R$ 1.200,00"
    assert sections[0]["share_percent"] == "70,59%"
    assert projected.answers[0].rows[0]["caixa_tipo"] == "Cartão de Crédito"


def _comissao_concessionaria_rows(count: int) -> list[dict]:  # type: ignore[type-arg]
    """Linhas ordenadas por total_comissao decrescente (maior primeiro)."""
    return [
        {
            "periodo": "2026-05",
            "concessionaria": f"Concessionária {index:02d}",
            "total_faturamento": f"{(count - index + 1) * 100:.2f}",
            "total_comissao": f"{(count - index + 1) * 10:.2f}",
        }
        for index in range(1, count + 1)
    ]


def _section_detail_for_comissao_count(count: int) -> str:
    projected = build_projected_answer_set(
        "Faça o fechamento gerencial de maio de 2026",
        [
            _fechamento_result(
                "fechamento_faturamento_comissao_concessionaria_periodo",
                _comissao_concessionaria_rows(count),
            ),
        ],
        templates=ANALYTICS_TEMPLATES,
    )
    assert projected is not None
    assert projected.section_detail is not None
    return projected.section_detail


def test_fechamento_section_detail_lists_all_rows_when_at_most_20() -> None:
    detail_8 = _section_detail_for_comissao_count(8)
    assert "1. Concessionária 01:" in detail_8
    assert "8. Concessionária 08:" in detail_8
    assert "Omitidas" not in detail_8
    assert "answers[].rows" not in detail_8

    detail_20 = _section_detail_for_comissao_count(20)
    assert "1. Concessionária 01:" in detail_20
    assert "20. Concessionária 20:" in detail_20
    assert "Omitidas" not in detail_20


def test_fechamento_section_detail_shows_head_and_tail_when_more_than_20_rows() -> None:
    detail = _section_detail_for_comissao_count(31)
    assert "1. Concessionária 01:" in detail
    assert "10. Concessionária 10:" in detail
    assert "11. Concessionária 11:" not in detail
    assert "Omitidas 11 linha(s) intermediárias" in detail
    assert "Exibindo os 10 piores resultados abaixo" in detail
    assert "22. Concessionária 22:" in detail
    assert "31. Concessionária 31:" in detail
    assert "answers[].rows" not in detail


def test_build_full_section_detail_lists_every_row_without_head_tail() -> None:
    projected = build_projected_answer_set(
        "Faça o fechamento gerencial de maio de 2026",
        [
            _fechamento_result(
                "fechamento_faturamento_comissao_concessionaria_periodo",
                _comissao_concessionaria_rows(31),
            ),
        ],
        templates=ANALYTICS_TEMPLATES,
    )
    assert projected is not None

    full_detail = build_full_section_detail(projected, templates=ANALYTICS_TEMPLATES)
    assert full_detail is not None
    assert "Omitidas" not in full_detail
    assert "11. Concessionária 11:" in full_detail
    assert "21. Concessionária 21:" in full_detail
    assert "31. Concessionária 31:" in full_detail


def test_fechamento_tipo_os_projects_commission_composition_table() -> None:
    projected = build_projected_answer_set(
        "Faça o fechamento gerencial de fevereiro de 2026",
        [
            _fechamento_result(
                "fechamento_faturamento_comissao_tipo_os_concessionaria_periodo",
                [
                    {
                        "periodo": "2026-02",
                        "concessionaria": "Concessionária A",
                        "total_faturamento": "170000.00",
                        "total_comissao": "170000.00",
                        "comissao_venda_normal": "100000.00",
                        "comissao_financiamento": "70000.00",
                    },
                    {
                        "periodo": "2026-03",
                        "concessionaria": "Concessionária A",
                        "total_faturamento": "30000.00",
                        "total_comissao": "30000.00",
                        "comissao_venda_normal": "20000.00",
                        "comissao_financiamento": "10000.00",
                    },
                    {
                        "periodo": "2026-02",
                        "concessionaria": "Concessionária B",
                        "total_faturamento": "90000.00",
                        "total_comissao": "90000.00",
                        "comissao_venda_normal": "90000.00",
                        "comissao_financiamento": "0.00",
                    },
                ],
            ),
        ],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.section_detail is not None
    assert "## Comissão por tipo de O.S." in projected.section_detail
    assert "concessionaria | venda normal | financiamento | total comissão" in projected.section_detail
    assert "Concessionária A | R$ 120.000,00 | R$ 80.000,00 | R$ 200.000,00" in projected.section_detail
    assert "Concessionária B | R$ 90.000,00 | R$ 0,00 | R$ 90.000,00" in projected.section_detail


def test_evidence_aggregator_embeds_direct_answer_before_narration() -> None:
    rows = [
        {"vendedor": "ana", "quantidade_os": 10, "vendas": "10000.00", "ticket_medio_os": "1000.00"},
        {"vendedor": "bia", "quantidade_os": 20, "vendas": "12000.00", "ticket_medio_os": "600.00"},
    ]

    evidence = EvidenceAggregator().merge(
        [_result("performance_vendedor", rows)],
        templates=ANALYTICS_TEMPLATES,
        query_text="Qual vendedor tem maior volume de vendas em abril de 2026?",
    )

    assert evidence.summary.startswith("Resposta direta")
    assert evidence.metrics["answer_plan"]["measure"] == "quantidade_os"
    assert "direct_answer" in evidence.supporting_data
    assert "Resumo estatístico complementar" in evidence.summary


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


def test_itens_vendidos_projects_ranking_by_sales() -> None:
    rows = [
        {
            "periodo": "2026-04",
            "categoria": "servico",
            "item": "martelinho de ouro",
            "quantidade_vendida": 7,
            "quantidade_os": 6,
            "vendas": "14000.00",
            "ticket_medio_item": "2000.00",
            "ticket_medio_os": "2333.33",
            "percentual_faturamento": "70.00",
        },
        {
            "periodo": "2026-04",
            "categoria": "produto",
            "item": "película",
            "quantidade_vendida": 12,
            "quantidade_os": 10,
            "vendas": "6000.00",
            "ticket_medio_item": "500.00",
            "ticket_medio_os": "600.00",
            "percentual_faturamento": "30.00",
        },
    ]

    projected = build_projected_answer(
        "Quais itens mais faturaram em abril de 2026?",
        [_result("itens_vendidos", rows)],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.plan.measure == "vendas"
    assert projected.plan.dimension == "item"
    assert projected.plan.operation == "ranking_desc"
    assert projected.top is not None
    assert projected.top["item"] == "martelinho de ouro"


def test_itens_vendidos_all_scope_lists_every_row_ordered_desc() -> None:
    rows = [
        {
            "periodo": "2025-12",
            "categoria": "servico",
            "item": f"item {i:02d}",
            "quantidade_vendida": i,
            "quantidade_os": i,
            "vendas": str(i * 1000),
            "ticket_medio_item": "1000.00",
            "ticket_medio_os": "1000.00",
            "percentual_faturamento": "1.00",
        }
        for i in range(1, 13)
    ]

    projected = build_projected_answer(
        "total vendido no periodo, ordenar do maior para o menor, inclua todos",
        [
            _result(
                "itens_vendidos",
                rows,
                hints={
                    "selected_metric": "vendas",
                    "selected_dimension": "item",
                    "selected_operation": "ranking_desc",
                    "result_scope": {"mode": "all", "limit": None},
                    "sort": {"field": "vendas", "direction": "desc"},
                },
            )
        ],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.plan.operation == "list"
    assert len(projected.rows) == 12
    assert "1. item 12: R$ 12.000,00" in projected.summary
    assert "12. item 01: R$ 1.000,00" in projected.summary


def test_itens_vendidos_projects_quantity_not_revenue() -> None:
    rows = [
        {
            "periodo": "2026-04",
            "categoria": "servico",
            "item": "martelinho de ouro",
            "quantidade_vendida": 7,
            "quantidade_os": 6,
            "vendas": "14000.00",
            "ticket_medio_item": "2000.00",
            "ticket_medio_os": "2333.33",
            "percentual_faturamento": "70.00",
        },
        {
            "periodo": "2026-04",
            "categoria": "produto",
            "item": "película",
            "quantidade_vendida": 12,
            "quantidade_os": 10,
            "vendas": "6000.00",
            "ticket_medio_item": "500.00",
            "ticket_medio_os": "600.00",
            "percentual_faturamento": "30.00",
        },
    ]

    projected = build_projected_answer(
        "Quais itens mais venderam em quantidade em abril de 2026?",
        [_result("itens_vendidos", rows)],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.plan.measure == "quantidade_vendida"
    assert projected.top is not None
    assert projected.top["item"] == "película"


def test_itens_vendidos_quantity_evidence_summary_is_not_money() -> None:
    rows = [
        {
            "periodo": "2025-12",
            "categoria": "servico",
            "item": "filme solar",
            "quantidade_vendida": "946",
            "quantidade_os": 910,
            "vendas": "283800.00",
            "ticket_medio_item": "300.00",
            "ticket_medio_os": "311.87",
            "percentual_faturamento": "24.60",
        },
        {
            "periodo": "2025-12",
            "categoria": "servico",
            "item": "clear comfort parabrisa",
            "quantidade_vendida": "420",
            "quantidade_os": 420,
            "vendas": "328116.55",
            "ticket_medio_item": "781.23",
            "ticket_medio_os": "781.23",
            "percentual_faturamento": "28.40",
        },
    ]

    evidence = EvidenceAggregator().merge(
        [
            _result(
                "itens_vendidos",
                rows,
                hints={
                    "selected_metric": "quantidade_vendida",
                    "selected_dimension": "item",
                    "selected_operation": "ranking_desc",
                },
            )
        ],
        templates=ANALYTICS_TEMPLATES,
        query_text="Quais itens, produtos ou serviços mais venderam em dezembro de 2025?",
    )

    assert evidence.metrics["value_key"] == "quantidade_vendida"
    assert evidence.metrics["value_kind"] == "count"
    assert "filme solar  946" in evidence.summary
    assert "R$ 946,00" not in evidence.summary


def test_itens_vendidos_filters_specific_item_before_projecting_answer() -> None:
    rows = [
        {
            "periodo": "2025-12",
            "categoria": "servico",
            "item": "filme solar",
            "quantidade_vendida": "946",
            "quantidade_os": 910,
            "vendas": "283800.00",
            "ticket_medio_item": "300.00",
            "ticket_medio_os": "311.87",
            "percentual_faturamento": "24.60",
        },
        {
            "periodo": "2025-12",
            "categoria": "servico",
            "item": "ppf-maçanetas",
            "quantidade_vendida": "184",
            "quantidade_os": 170,
            "vendas": "55200.00",
            "ticket_medio_item": "300.00",
            "ticket_medio_os": "324.71",
            "percentual_faturamento": "4.78",
        },
        {
            "periodo": "2025-12",
            "categoria": "servico",
            "item": "ppf-proteção das portas",
            "quantidade_vendida": "168",
            "quantidade_os": 160,
            "vendas": "50400.00",
            "ticket_medio_item": "300.00",
            "ticket_medio_os": "315.00",
            "percentual_faturamento": "4.36",
        },
    ]

    evidence = EvidenceAggregator().merge(
        [
            _result(
                "itens_vendidos",
                rows,
                hints={
                    "selected_metric": "quantidade_vendida",
                    "selected_dimension": "item",
                    "selected_operation": "list",
                    "entity_filters": ({"dimension": "item", "value": "PPF", "match": "exact"},),
                },
            )
        ],
        templates=ANALYTICS_TEMPLATES,
        query_text="quero saber quanto foi vendido de PPF nesse periodo?",
    )

    assert "ppf-maçanetas: 184" in evidence.summary
    assert "ppf-proteção das portas: 168" in evidence.summary
    assert "filme solar" not in evidence.summary
    direct = evidence.supporting_data["direct_answer"]
    assert len(direct["rows"]) == 2


def test_entity_filter_applies_to_any_template_dimension() -> None:
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

    evidence = EvidenceAggregator().merge(
        [
            _result(
                "performance_concessionaria",
                rows,
                hints={
                    "selected_metric": "vendas",
                    "selected_dimension": "concessionaria",
                    "selected_operation": "list",
                    "entity_filters": ({"dimension": "concessionaria", "value": "osaka", "match": "contains"},),
                },
            )
        ],
        templates=ANALYTICS_TEMPLATES,
        query_text="quanto a concessionária Osaka vendeu?",
    )

    assert "osaka: R$ 187.547,00" in evidence.summary
    assert "strada jeep" not in evidence.summary


def test_itens_vendidos_sales_evidence_summary_keeps_money_format() -> None:
    rows = [
        {
            "periodo": "2025-12",
            "categoria": "servico",
            "item": "filme solar",
            "quantidade_vendida": "946",
            "quantidade_os": 910,
            "vendas": "283800.00",
            "ticket_medio_item": "300.00",
            "ticket_medio_os": "311.87",
            "percentual_faturamento": "24.60",
        },
        {
            "periodo": "2025-12",
            "categoria": "servico",
            "item": "clear comfort parabrisa",
            "quantidade_vendida": "420",
            "quantidade_os": 420,
            "vendas": "328116.55",
            "ticket_medio_item": "781.23",
            "ticket_medio_os": "781.23",
            "percentual_faturamento": "28.40",
        },
    ]

    evidence = EvidenceAggregator().merge(
        [
            _result(
                "itens_vendidos",
                rows,
                hints={
                    "selected_metric": "vendas",
                    "selected_dimension": "item",
                    "selected_operation": "ranking_desc",
                },
            )
        ],
        templates=ANALYTICS_TEMPLATES,
        query_text="Quais itens mais faturaram em dezembro de 2025?",
    )

    assert evidence.metrics["value_key"] == "vendas"
    assert evidence.metrics["value_kind"] == "money"
    assert "R$ 328.116,55" in evidence.summary


def test_itens_vendidos_percent_evidence_summary_keeps_percent_format() -> None:
    rows = [
        {
            "periodo": "2025-12",
            "categoria": "servico",
            "item": "filme solar",
            "quantidade_vendida": "946",
            "quantidade_os": 910,
            "vendas": "283800.00",
            "ticket_medio_item": "300.00",
            "ticket_medio_os": "311.87",
            "percentual_faturamento": "24.60",
        },
        {
            "periodo": "2025-12",
            "categoria": "servico",
            "item": "clear comfort parabrisa",
            "quantidade_vendida": "420",
            "quantidade_os": 420,
            "vendas": "328116.55",
            "ticket_medio_item": "781.23",
            "ticket_medio_os": "781.23",
            "percentual_faturamento": "28.40",
        },
    ]

    evidence = EvidenceAggregator().merge(
        [
            _result(
                "itens_vendidos",
                rows,
                hints={
                    "selected_metric": "percentual_faturamento",
                    "selected_dimension": "item",
                    "selected_operation": "list",
                },
            )
        ],
        templates=ANALYTICS_TEMPLATES,
        query_text="Qual participação de cada item no faturamento em dezembro de 2025?",
    )

    assert evidence.metrics["value_key"] == "percentual_faturamento"
    assert evidence.metrics["value_kind"] == "percent"
    assert "clear comfort parabrisa  28,40%" in evidence.summary
    assert "R$ 28,40" not in evidence.summary


def test_itens_vendidos_projects_ticket_medio_item() -> None:
    rows = [
        {
            "periodo": "2026-04",
            "categoria": "servico",
            "item": "martelinho de ouro",
            "quantidade_vendida": 7,
            "quantidade_os": 6,
            "vendas": "14000.00",
            "ticket_medio_item": "2000.00",
            "ticket_medio_os": "2333.33",
            "percentual_faturamento": "70.00",
        },
        {
            "periodo": "2026-04",
            "categoria": "produto",
            "item": "película",
            "quantidade_vendida": 12,
            "quantidade_os": 10,
            "vendas": "6000.00",
            "ticket_medio_item": "500.00",
            "ticket_medio_os": "600.00",
            "percentual_faturamento": "30.00",
        },
    ]

    projected = build_projected_answer(
        "Qual item tem maior ticket médio em abril de 2026?",
        [_result("itens_vendidos", rows)],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.plan.measure == "ticket_medio_item"
    assert projected.top is not None
    assert projected.top["item"] == "martelinho de ouro"


def test_itens_vendidos_projects_participation_percentage() -> None:
    rows = [
        {
            "periodo": "2026-04",
            "categoria": "servico",
            "item": "martelinho de ouro",
            "quantidade_vendida": 7,
            "quantidade_os": 6,
            "vendas": "14000.00",
            "ticket_medio_item": "2000.00",
            "ticket_medio_os": "2333.33",
            "percentual_faturamento": "70.00",
        },
        {
            "periodo": "2026-04",
            "categoria": "produto",
            "item": "película",
            "quantidade_vendida": 12,
            "quantidade_os": 10,
            "vendas": "6000.00",
            "ticket_medio_item": "500.00",
            "ticket_medio_os": "600.00",
            "percentual_faturamento": "30.00",
        },
    ]

    projected = build_projected_answer(
        "Qual participação de cada item no faturamento em abril de 2026?",
        [_result("itens_vendidos", rows)],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.plan.measure == "percentual_faturamento"
    assert projected.plan.operation == "list"
    assert "martelinho de ouro: 70,00%" in projected.summary
    assert "película: 30,00%" in projected.summary


def test_itens_vendidos_projects_category_comparison() -> None:
    rows = [
        {
            "periodo": "2026-04",
            "categoria": "servico",
            "item": "martelinho de ouro",
            "quantidade_vendida": 7,
            "quantidade_os": 6,
            "vendas": "14000.00",
            "ticket_medio_item": "2000.00",
            "ticket_medio_os": "2333.33",
            "percentual_faturamento": "70.00",
        },
        {
            "periodo": "2026-04",
            "categoria": "produto",
            "item": "película",
            "quantidade_vendida": 12,
            "quantidade_os": 10,
            "vendas": "6000.00",
            "ticket_medio_item": "500.00",
            "ticket_medio_os": "600.00",
            "percentual_faturamento": "30.00",
        },
    ]

    projected = build_projected_answer(
        "Produtos versus serviços: qual categoria gera mais receita?",
        [_result("itens_vendidos", rows)],
        templates=ANALYTICS_TEMPLATES,
    )

    assert projected is not None
    assert projected.plan.measure == "vendas"
    assert projected.plan.dimension == "categoria"
    assert projected.top is not None
    assert projected.top["categoria"] == "servico"


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


def test_evidence_aggregator_stores_full_summary_when_result_scope_is_top_n() -> None:
    rows = [
        {
            "caixa_tipo_id": 1,
            "caixa_tipo": "Cartão de Crédito",
            "periodo": "2025-09",
            "total_pagamentos": "1755398.76",
            "total_estornos": "0.00",
            "total_liquido": "1755398.76",
        },
        {
            "caixa_tipo_id": 2,
            "caixa_tipo": "PIX",
            "periodo": "2025-09",
            "total_pagamentos": "382387.40",
            "total_estornos": "0.00",
            "total_liquido": "382387.40",
        },
        {
            "caixa_tipo_id": 3,
            "caixa_tipo": "Dinheiro",
            "periodo": "2025-09",
            "total_pagamentos": "79382.50",
            "total_estornos": "0.00",
            "total_liquido": "79382.50",
        },
    ]

    evidence = EvidenceAggregator().merge(
        [
            _result(
                "fechamento_faturamento_tipo_pagamento",
                rows,
                hints={
                    "selected_metric": "total_liquido",
                    "selected_dimension": "caixa_tipo",
                    "selected_operation": "ranking_desc",
                    "result_scope": {"mode": "top_n", "limit": 1},
                    "sort": {"field": "total_liquido", "direction": "desc"},
                },
            )
        ],
        templates=ANALYTICS_TEMPLATES,
        query_text="Qual forma de pagamento domina o faturamento em setembro de 2025?",
    )

    direct = evidence.supporting_data["direct_answer"]
    assert "Cartão de Crédito" in direct["summary"]
    assert "PIX" not in direct["summary"]
    assert "full_summary" in direct
    assert "Cartão de Crédito" in direct["full_summary"]
    assert "PIX" in direct["full_summary"]
    assert "Dinheiro" in direct["full_summary"]
    assert "1. Cartão de Crédito" in direct["full_summary"]
    assert "2. PIX" in direct["full_summary"]
