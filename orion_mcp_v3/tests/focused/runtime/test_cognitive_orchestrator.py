"""CognitiveOrchestrator §12 — fusão + scheduler + allocator + prompt."""

from __future__ import annotations

import asyncio

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES, AnalyticsResult, EvidenceAggregator
from orion_mcp_v3.broker.evidence_builder import EvidenceBuilder
from orion_mcp_v3.contracts.analytics_outcome import AnalyticsOutcome
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.evidence_contract import EvidenceContract
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan
from orion_mcp_v3.contracts.reasoning_result import AnalyticalReasoningResult, AnswerMode
from orion_mcp_v3.protocols.llm import NullLLMProvider
from orion_mcp_v3.runtime import AttentionPolicy, CognitiveNarrator, CognitiveOrchestrator
from orion_mcp_v3.runtime.analytical_reasoner import AnalyticalReasoner
from orion_mcp_v3.runtime.cognitive_orchestrator import build_fusion_layers


def _fechamento_result(slug: str, rows: list[dict]) -> AnalyticsResult:  # type: ignore[type-arg]
    return AnalyticsResult(
        plan=SemanticQueryPlan(
            intent_slug=f"template.{slug}",
            strategy=RetrievalStrategy.BROKER_FANOUT,
            hints={
                "template_slug": slug,
                "template_params": {},
                "collection_slug": "fechamento_gerencial_por_mes",
                "collection_presentation_mode": "sections",
                "selected_operation": "list",
                "result_scope": {"mode": "all", "limit": None},
            },
        ),
        sql="SELECT ...",
        rows=rows,
        row_count=len(rows),
    )


def _fechamento_results() -> list[AnalyticsResult]:
    return [
        _fechamento_result(
            "fechamento_faturamento_comissao_concessionaria_periodo",
            [
                {"periodo": "2026-05", "concessionaria": "GWM BAMAQ", "total_faturamento": "900.00", "total_comissao": "90.00"},
                {"periodo": "2026-05", "concessionaria": "STRADA JEEP", "total_faturamento": "700.00", "total_comissao": "70.00"},
                {"periodo": "2026-05", "concessionaria": "AUDI CARBEL", "total_faturamento": "500.00", "total_comissao": "50.00"},
            ],
        ),
        _fechamento_result(
            "fechamento_faturamento_comissao_tipo_os_concessionaria_periodo",
            [
                {
                    "periodo": "2026-05",
                    "concessionaria": "GWM BAMAQ",
                    "total_faturamento": "300.00",
                    "total_comissao": "30.00",
                    "comissao_venda_normal": "0.00",
                    "comissao_financiamento": "30.00",
                }
            ],
        ),
        _fechamento_result(
            "fechamento_producao_servico",
            [{"servico_id": 1, "servico": "PPF", "quantidade": 2, "total": "800.00", "custo": "0.00"}],
        ),
        _fechamento_result(
            "fechamento_producao_produto",
            [{"produto_id": 1, "produto": "FILME", "quantidade": 1, "total": "200.00"}],
        ),
        _fechamento_result(
            "fechamento_faturamento_tipo_pagamento",
            [
                {"caixa_tipo_id": 1, "caixa_tipo": "Cartão de Crédito", "total_pagamentos": "1300.00", "total_estornos": "100.00", "total_liquido": "1200.00"},
                {"caixa_tipo_id": 2, "caixa_tipo": "PIX", "total_pagamentos": "500.00", "total_estornos": "0.00", "total_liquido": "500.00"},
            ],
        ),
        _fechamento_result("fechamento_faturamento_tipo_venda", [{"id": 1, "os_tipo": "Venda Normal", "total": "1700.00"}]),
        _fechamento_result("fechamento_faturamento_tipo_venda_produtos", [{"id": 11, "os_tipo": "Venda de Materiais", "total": "200.00"}]),
        _fechamento_result("fechamento_parcelamento_cartao", [{"parcelas": "10X", "quant_parcelas": 10, "quantidade": 4, "total": "900.00"}]),
        _fechamento_result(
            "fechamento_taxas_cartao_credito",
            [{"empresa_id": 7, "empresa_nome": "MFP ESTETICA AUTOMOTIVA", "valor_bruto": "1200.00", "valor_liquido": "1160.00", "min_taxa": "1.90", "avg_taxa": "1.90", "max_taxa": "1.90", "valor_taxa": "40.00", "quantidade_registros": 1, "quantidade_parcelas": 10, "bandeira": "visa"}],
        ),
    ]


def test_finalize_prompt_produces_non_empty_prompt() -> None:
    utterance = "quantos registos?"
    user_like = ContextBlock(
        utterance,
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id="u",
        relevance_score=1.0,
    )
    orch = CognitiveOrchestrator()
    r = orch.finalize_prompt(
        utterance,
        policy=AttentionPolicy.ANALYTICAL,
        memory_blocks=[user_like],
        max_tokens=512,
    )
    assert "[USER]" in r.prompt_text
    assert len(r.packed_blocks) >= 1
    assert r.fusion.layer_priority == ("system", "user", "memory")


def test_fusion_layers_place_evidence_before_memory_context() -> None:
    evidence = EvidenceBuilder().build(
        [{"total_faturamento": 100.0}],
        value_key="total_faturamento",
    )
    essence = ContextBlock(
        "memória destilada",
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        block_id="essence",
    )
    memory = ContextBlock(
        "memória episódica",
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        block_id="memory",
    )

    layers = build_fusion_layers(
        "qual o faturamento?",
        evidence=evidence,
        essence_blocks=[essence],
        memory_blocks=[memory],
    )

    assert tuple(name for name, _ in layers) == ("user", "evidence", "essence", "memory")


def test_fusion_layers_place_reasoning_after_evidence_before_memory() -> None:
    evidence = EvidenceBuilder().build(
        [{"total_faturamento": 100.0}],
        value_key="total_faturamento",
    )
    reasoning = AnalyticalReasoningResult(
        facts=("Evidência analítica disponível.",),
        evidence_contract=EvidenceContract.present(row_count=1),
        answer_mode=AnswerMode.EXECUTIVE,
    )
    memory = ContextBlock(
        "memória episódica",
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        block_id="memory",
    )

    layers = build_fusion_layers(
        "resumo executivo",
        evidence=evidence,
        reasoning_result=reasoning,
        memory_blocks=[memory],
    )

    assert tuple(name for name, _ in layers) == ("user", "evidence", "reasoning", "memory")
    reasoning_block = layers[2][1][0]
    assert reasoning_block.metadata["fusion_kind"] == "reasoning_result"
    assert reasoning_block.metadata["answer_mode"] == "executive"


def test_managerial_closing_reaches_narrator_as_structured_contract_without_coverage_duplication() -> None:
    message = "Faça o fechamento gerencial de maio de 2026"
    evidence = EvidenceAggregator().merge(
        _fechamento_results(),
        templates=ANALYTICS_TEMPLATES,
        query_text=message,
    )
    direct_answer_set = evidence.supporting_data["direct_answer_set"]
    assert direct_answer_set["headline"] == "Faturamento líquido por forma de pagamento: R$ 1.700,00"
    assert direct_answer_set["executive_sections"]
    contract = EvidenceContract.from_mapping(evidence.supporting_data.get("evidence_contract"))
    assert contract.operational_confidence.data_coverage == 1.0
    assert direct_answer_set["executive_summary"] == direct_answer_set["summary"]
    assert evidence.metrics["input_rows"] == 12
    assert "STRADA JEEP" in evidence.summary
    assert "PIX" in evidence.summary
    assert "STRADA JEEP" not in direct_answer_set["executive_summary"]

    plan = CognitivePlan(intent_type=IntentType.ANALYTICAL, needs_analytics=True, confidence=0.8)
    reasoning = AnalyticalReasoner().reason(
        message,
        cognitive_plan=plan,
        analytics_outcome=AnalyticsOutcome.executed(
            evidence=evidence,
            row_count=9,
            plan_count=9,
        ),
    )
    assert reasoning.answer_mode == AnswerMode.EXECUTIVE
    assert reasoning.insights

    result = CognitiveOrchestrator().finalize_prompt(
        message,
        policy=AttentionPolicy.ANALYTICAL,
        cognitive_plan=plan,
        evidence=evidence,
        reasoning_result=reasoning,
        max_tokens=20_000,
    )
    assert "Fechamento gerencial por mês requer" in result.prompt_text

    narration = asyncio.run(CognitiveNarrator(NullLLMProvider()).narrate(result))
    assert "coverage_note_injected" in narration.safeguards_applied
    assert len(narration.coverage_note) < len(evidence.summary) * 0.25
    assert "GWM BAMAQ" not in narration.coverage_note
