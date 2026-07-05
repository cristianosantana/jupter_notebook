"""Testes do Fact Planner analítico (5A)."""

from __future__ import annotations

import pytest

from orion_mcp_v3.public_chat.domain.fact_engine.requirement_kind import RequirementKind
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.intent_heuristics import apply_heuristic_enrichment
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.tests.phase4.fixtures import load_maio_contract_fixture, maio_hit, march_hit


@pytest.mark.asyncio
async def test_fact_planner_ranking_asc_marco():
    planner = FactPlanner(provider=None)
    message = "Qual a forma de pagamento menos usada em março de 2026?"
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-03",
            confidence=0.9,
            operation=PublicOperationType.RANKING_ASC.value,
            dimension="forma_pagamento",
        ),
        message,
    )
    knowledge = ConhecimentoRecuperado(hits=(march_hit(),))
    result = await planner.plan(message, contract=contract, knowledge=knowledge)
    assert result.composite is False
    assert len(result.requirements) >= 1
    assert result.requirements[0].fact_key.startswith("dynamic:")
    assert result.requirements[0].requirement_kind == RequirementKind.LOOKUP
    assert result.requirements[0].matched_key == "faturamento_por_tipo_de_pagamento"


@pytest.mark.asyncio
async def test_fact_planner_composite_servico_produto_maio():
    planner = FactPlanner(provider=None)
    message = "Quais servicos e produtos venderam mais em maio de 2026?"
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-05",
            confidence=0.85,
            operation=PublicOperationType.RANKING_DESC.value,
            dimension="servico",
        ),
        message,
    )
    knowledge = ConhecimentoRecuperado(hits=(maio_hit(),))
    result = await planner.plan(message, contract=contract, knowledge=knowledge)
    fact_keys = {req.fact_key for req in result.requirements}
    matched = {req.matched_key for req in result.requirements}
    assert result.composite is True
    assert "dynamic:producao_por_servico" in fact_keys
    assert "dynamic:producao_por_produto" in fact_keys
    assert matched == {"producao_por_servico", "producao_por_produto"}
    assert result.used_llm_disambiguation is False


@pytest.mark.asyncio
async def test_fact_planner_indexes_all_hits_and_tracks_source_origin_id():
    planner = FactPlanner(provider=None)
    fixture = load_maio_contract_fixture()
    parcelamento = KnowledgeHit(
        origin_id=37,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:2026-05",
        category="Fechamento Gerencial",
        validated_answer="Parcelamento de cartão em maio.",
        key_metrics={"parcelamento_de_cartao": fixture["key_metrics"]["parcelamento_de_cartao"]},
        score=0.275767,
    )
    faturamento = KnowledgeHit(
        origin_id=33,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_forma_pagamento:2026-05",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por forma de pagamento em maio.",
        key_metrics={
            "faturamento_por_tipo_de_pagamento": fixture["key_metrics"][
                "faturamento_por_tipo_de_pagamento"
            ],
        },
        score=0.354322,
    )
    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-05",
        confidence=0.78,
        operation="comparison",
        dimension=None,
    )

    result = await planner.plan(
        "qual o faturamento em maio de 2026?",
        contract=contract,
        knowledge=ConhecimentoRecuperado(hits=(parcelamento, faturamento)),
    )

    assert len(result.requirements) == 1
    requirement = result.requirements[0]
    assert requirement.matched_key == "faturamento_por_tipo_de_pagamento"
    assert requirement.source_origin_id == 33
    assert requirement.source_context_key == faturamento.context_key


@pytest.mark.asyncio
async def test_fact_planner_resolves_cartao_5x_to_parcelamento_de_cartao():
    planner = FactPlanner(provider=None)
    fixture = load_maio_contract_fixture()
    message = "qual o total de vendas com pagamento em cartão de credito em 5x em abril de 2026?"
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-04",
            dimension="forma_pagamento",
            operation="summary",
            confidence=0.95,
        ),
        message,
    )
    faturamento = KnowledgeHit(
        origin_id=25,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_forma_pagamento:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por forma de pagamento em abril.",
        key_metrics={
            "faturamento_por_tipo_de_pagamento": fixture["key_metrics"][
                "faturamento_por_tipo_de_pagamento"
            ],
        },
    )
    parcelamento = KnowledgeHit(
        origin_id=31,
        context_key="sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-2026-04",
        category="Fechamento Gerencial",
        validated_answer="Parcelamento de cartão em abril.",
        key_metrics={"parcelamento_de_cartao": fixture["key_metrics"]["parcelamento_de_cartao"]},
    )

    result = await planner.plan(
        message,
        contract=contract,
        knowledge=ConhecimentoRecuperado(hits=(faturamento, parcelamento)),
    )

    assert len(result.requirements) == 1
    requirement = result.requirements[0]
    assert requirement.matched_key == "parcelamento_de_cartao"
    assert requirement.entity == "5X"
    assert requirement.source_origin_id == 31
