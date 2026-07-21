"""Seção 1 — ranking/comparação não colapsa em filtro único; preferir ranked_list."""

from __future__ import annotations

import pytest

from orion_mcp_v3.public_chat.application.workspace_pipeline import build_remissive_workspace
from orion_mcp_v3.public_chat.domain.fact_extractor import PARTIAL_RANKING_CONFIDENCE, FactExtractor
from orion_mcp_v3.public_chat.domain.fact_planner import FactPlanner
from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.intent_heuristics import (
    apply_heuristic_enrichment,
    sanitize_ranking_entity_filters,
)
from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.infrastructure.memory_resolver import MemoryResolver
from orion_mcp_v3.public_chat.tests.phase4.fixtures import load_maio_contract_fixture


class _CatalogReader:
    def __init__(self, hits: tuple[KnowledgeHit, ...]) -> None:
        self._hits = hits

    async def load_hits_by_theme_patterns(self, patterns, *, limit=20):
        return list(self._hits)


def _parcelamento_payload(rows: list[dict], *, truncated: bool = False) -> dict:
    return {
        "parcelamento_de_cartao": {
            "rows": rows,
            "_meta": {
                "schema": "ranked_list",
                "dimension": "parcelas",
                "metric_kind": "revenue",
                "value_field": "valor",
                "entity_field": "parcelas",
                "total_original_rows": len(rows),
                "truncated_head_tail": truncated,
            },
        },
    }


def _parcel_hit(*, origin_id: int, period: str, rows: list[dict], truncated: bool = False) -> KnowledgeHit:
    return KnowledgeHit(
        origin_id=origin_id,
        context_key=f"sistema_background:fechamento_gerencial:parcelamento_cartao:periodo-{period}",
        category="Fechamento Gerencial",
        validated_answer=f"Parcelamento de cartão em {period}.",
        key_metrics=_parcelamento_payload(rows, truncated=truncated),
        score=0.4,
    )


_JAN_ROWS = [
    {"parcelas": "10X", "valor": "R$ 681.772,80 (59,56%)", "percentual": "59,56%"},
    {"parcelas": "1X", "valor": "R$ 157.701,01 (13,78%)", "percentual": "13,78%"},
    {"parcelas": "6X", "valor": "R$ 103.233,90 (9,02%)", "percentual": "9,02%"},
    {"parcelas": "5X", "valor": "R$ 69.004,00 (6,03%)", "percentual": "6,03%"},
    {"parcelas": "3X", "valor": "R$ 49.109,00 (4,29%)", "percentual": "4,29%"},
    {"parcelas": "2X", "valor": "R$ 38.927,00 (3,40%)", "percentual": "3,40%"},
    {"parcelas": "4X", "valor": "R$ 36.559,00 (3,19%)", "percentual": "3,19%"},
    {"parcelas": "9X", "valor": "R$ 6.100,00 (0,53%)", "percentual": "0,53%"},
    {"parcelas": "8X", "valor": "R$ 2.350,00 (0,21%)", "percentual": "0,21%"},
]

_JUN_ROWS = [
    {"parcelas": "10X", "valor": "R$ 767.384,20 (65,14%)", "percentual": "65,14%"},
    {"parcelas": "6X", "valor": "R$ 139.341,10 (11,83%)", "percentual": "11,83%"},
    {"parcelas": "1X", "valor": "R$ 101.027,22 (8,58%)", "percentual": "8,58%"},
    {"parcelas": "3X", "valor": "R$ 70.383,04 (5,97%)", "percentual": "5,97%"},
    {"parcelas": "4X", "valor": "R$ 44.150,19 (3,75%)", "percentual": "3,75%"},
    {"parcelas": "5X", "valor": "R$ 30.526,80 (2,59%)", "percentual": "2,59%"},
    {"parcelas": "2X", "valor": "R$ 20.199,20 (1,71%)", "percentual": "1,71%"},
    {"parcelas": "9X", "valor": "R$ 5.000,00 (0,42%)", "percentual": "0,42%"},
]


def test_sanitize_drops_self_filter_on_ranking_dimension() -> None:
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-01",
        operation=PublicOperationType.RANKING_DESC.value,
        dimension="parcelas",
        entity_filters=(
            EntityFilter(dimension="parcelas", value="1X", match="contains"),
            EntityFilter(dimension="forma_pagamento", value="cartao de credito", match="contains"),
            EntityFilter(dimension="periodo", value="2026-06", match="exact"),
        ),
        confidence=0.9,
    )
    cleaned = sanitize_ranking_entity_filters(contract)
    dims = {filt.dimension for filt in cleaned.entity_filters}
    assert "parcelas" not in dims
    assert "forma_pagamento" in dims
    assert "periodo" in dims


def test_sanitize_keeps_filter_when_not_ranking() -> None:
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-03",
        operation=None,
        dimension="parcelas",
        entity_filters=(EntityFilter(dimension="parcelas", value="5X", match="contains"),),
        confidence=0.9,
    )
    cleaned = sanitize_ranking_entity_filters(contract)
    assert cleaned.entity_filters[0].value == "5X"


def test_senna_message_enrichment_drops_parcelas_1x_on_ranking() -> None:
    message = (
        "Das vendas parceladas em cartão de crédito em janeiro de 2026, "
        "qual parcela (1x a 10x) teve o maior crescimento percentual até junho?"
    )
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-01",
            operation=PublicOperationType.RANKING_DESC.value,
            dimension="parcelas",
            entity_filters=(EntityFilter(dimension="parcelas", value="1X", match="contains"),),
            confidence=0.9,
        ),
        message,
    )
    parcel_filters = [item for item in contract.entity_filters if item.dimension == "parcelas"]
    assert parcel_filters == []
    assert contract.dimension == "parcelas"
    assert contract.operation == PublicOperationType.RANKING_DESC.value


def test_intentional_5x_lookup_keeps_entity_filter() -> None:
    message = "qual o total de vendas com pagamento em cartão de credito em 5x em abril de 2026?"
    contract = apply_heuristic_enrichment(
        IntentContract(
            intent="consulta_metrica",
            metric="faturamento",
            period="2026-04",
            confidence=0.9,
        ),
        message,
    )
    assert contract.dimension == "parcelas"
    parcel_filters = [item for item in contract.entity_filters if item.dimension == "parcelas"]
    assert len(parcel_filters) == 1
    assert parcel_filters[0].value == "5X"


@pytest.mark.asyncio
async def test_planner_senna_uses_ranked_list_not_per_entity_keys() -> None:
    message = (
        "Das vendas parceladas em cartão de crédito em janeiro de 2026, "
        "qual parcela (1x a 10x) teve o maior crescimento percentual até junho?"
    )
    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-01",
        operation=PublicOperationType.RANKING_DESC.value,
        dimension="parcelas",
        entity_filters=(
            EntityFilter(dimension="parcelas", value="1X", match="contains"),
            EntityFilter(dimension="periodo", value="2026-06", match="exact"),
            EntityFilter(dimension="forma_pagamento", value="cartao de credito", match="contains"),
        ),
        confidence=0.9,
    )
    knowledge = ConhecimentoRecuperado(
        hits=(
            _parcel_hit(origin_id=8, period="2026-01", rows=_JAN_ROWS),
            _parcel_hit(origin_id=49, period="2026-06", rows=_JUN_ROWS),
        ),
    )
    result = await FactPlanner(provider=None).plan(message, contract=contract, knowledge=knowledge)

    assert len(result.requirements) == 2
    assert all(req.entity is None for req in result.requirements)
    assert all(req.matched_key == "parcelamento_de_cartao" for req in result.requirements)
    assert all("@1x" not in req.fact_key.lower() for req in result.requirements)
    periods = {req.period for req in result.requirements}
    assert periods == {"2026-01", "2026-06"}


@pytest.mark.asyncio
async def test_workspace_senna_winner_is_3x_growth() -> None:
    message = (
        "Das vendas parceladas em cartão de crédito em janeiro de 2026, "
        "qual parcela (1x a 10x) teve o maior crescimento percentual até junho?"
    )
    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-01",
        operation=PublicOperationType.RANKING_DESC.value,
        dimension="parcelas",
        entity_filters=(
            EntityFilter(dimension="parcelas", value="1X", match="contains"),
            EntityFilter(dimension="periodo", value="2026-06", match="exact"),
        ),
        confidence=0.9,
    )
    knowledge = ConhecimentoRecuperado(
        hits=(
            _parcel_hit(origin_id=8, period="2026-01", rows=_JAN_ROWS),
            _parcel_hit(origin_id=49, period="2026-06", rows=_JUN_ROWS),
        ),
    )
    workspace = await build_remissive_workspace(
        message,
        contract=contract,
        knowledge=knowledge,
        resolver=MemoryResolver(_CatalogReader(knowledge.hits)),
        extractor=FactExtractor(),
    )

    assert workspace.has_facts
    winner = workspace.facts[0]
    assert winner.label.upper().replace(" ", "") in {"3X", "3x".upper()}
    assert "43" in winner.value
    assert workspace.workspace_confidence > PARTIAL_RANKING_CONFIDENCE


@pytest.mark.asyncio
async def test_workspace_payment_ranking_across_periods_is_generic() -> None:
    """Dimensão aberta (forma_pagamento): mesmo mecanismo ranked_list, sem domínio estático."""
    fixture = load_maio_contract_fixture()
    payment_payload = fixture["key_metrics"]["faturamento_por_tipo_de_pagamento"]

    def _payment_hit(origin_id: int, period: str) -> KnowledgeHit:
        return KnowledgeHit(
            origin_id=origin_id,
            context_key=(
                "sistema_background:fechamento_gerencial:"
                f"faturamento_por_forma_pagamento:periodo-{period}"
            ),
            category="Fechamento Gerencial",
            validated_answer=f"Formas de pagamento em {period}.",
            key_metrics={"faturamento_por_tipo_de_pagamento": payment_payload},
            score=0.4,
        )

    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-05",
        operation=PublicOperationType.RANKING_DESC.value,
        dimension="forma_pagamento",
        entity_filters=(
            EntityFilter(dimension="forma_pagamento", value="PIX", match="contains"),
            EntityFilter(dimension="periodo", value="2026-06", match="exact"),
        ),
        confidence=0.9,
    )
    knowledge = ConhecimentoRecuperado(
        hits=(
            _payment_hit(33, "2026-05"),
            _payment_hit(40, "2026-06"),
        ),
    )
    result = await FactPlanner(provider=None).plan(
        "qual forma de pagamento teve maior crescimento de maio a junho?",
        contract=contract,
        knowledge=knowledge,
    )
    assert len(result.requirements) == 2
    assert all(req.entity is None for req in result.requirements)
    assert all("@pix" not in req.fact_key.lower() for req in result.requirements)


@pytest.mark.asyncio
async def test_entity_absent_in_one_period_uses_intersection_not_gap() -> None:
    jan_only_8x = [row for row in _JAN_ROWS if row["parcelas"] != "7X"]
    jun_without_8x = [row for row in _JUN_ROWS]  # 8X already absent in jun fixture
    assert not any(row["parcelas"] == "8X" for row in jun_without_8x)

    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-01",
        operation=PublicOperationType.RANKING_DESC.value,
        dimension="parcelas",
        entity_filters=(EntityFilter(dimension="periodo", value="2026-06", match="exact"),),
        confidence=0.9,
    )
    knowledge = ConhecimentoRecuperado(
        hits=(
            _parcel_hit(origin_id=8, period="2026-01", rows=jan_only_8x),
            _parcel_hit(origin_id=49, period="2026-06", rows=jun_without_8x),
        ),
    )
    workspace = await build_remissive_workspace(
        "qual parcela cresceu mais de janeiro a junho?",
        contract=contract,
        knowledge=knowledge,
        resolver=MemoryResolver(_CatalogReader(knowledge.hits)),
        extractor=FactExtractor(),
    )
    assert workspace.has_facts
    # 8X exists only in jan → not in intersection; still produce a winner
    assert workspace.facts[0].label.upper().replace(" ", "") == "3X"
    gap_details = " ".join(gap.detail or "" for gap in workspace.gaps)
    assert "8x" not in gap_details.lower()


@pytest.mark.asyncio
async def test_truncated_ranked_list_caps_workspace_confidence() -> None:
    contract = IntentContract(
        intent="comparacao",
        metric="faturamento",
        period="2026-01",
        operation=PublicOperationType.RANKING_DESC.value,
        dimension="parcelas",
        entity_filters=(EntityFilter(dimension="periodo", value="2026-06", match="exact"),),
        confidence=0.9,
    )
    knowledge = ConhecimentoRecuperado(
        hits=(
            _parcel_hit(origin_id=8, period="2026-01", rows=_JAN_ROWS, truncated=True),
            _parcel_hit(origin_id=49, period="2026-06", rows=_JUN_ROWS),
        ),
    )
    workspace = await build_remissive_workspace(
        "qual parcela cresceu mais de janeiro a junho?",
        contract=contract,
        knowledge=knowledge,
        resolver=MemoryResolver(_CatalogReader(knowledge.hits)),
        extractor=FactExtractor(),
    )
    assert workspace.workspace_confidence <= PARTIAL_RANKING_CONFIDENCE
