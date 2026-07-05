"""Testes Fase 4B — preparação do documento."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.domain.knowledge_scoper import scope_knowledge
from orion_mcp_v3.public_chat.domain.section_parser import parse_document
from orion_mcp_v3.public_chat.tests.phase4.fixtures import march_hit, other_month_hit


def test_section_parser_splits_fechamento() -> None:
    document = parse_document(march_hit())
    titles = {section.title for section in document.sections}
    assert len(document.sections) >= 3
    assert any("pagamento" in title.lower() for title in titles)
    assert any("serviço" in title.lower() or "servico" in title.lower() for title in titles)


def test_section_parser_fallback_single_section() -> None:
    hit = KnowledgeHit(
        origin_id=1,
        context_key="ctx",
        category="fechamento_gerencial_mensal",
        validated_answer="Texto sem headers estruturados.",
        key_metrics={},
    )
    document = parse_document(hit)
    assert len(document.sections) == 1
    assert document.sections[0].title == "documento"


def test_period_scoper_filters_march() -> None:
    knowledge = ConhecimentoRecuperado(
        hits=(
            march_hit(origin_id=4),
            other_month_hit(origin_id=3, month_slug="fevereiro_2026", period="2026-02-01-to-2026-02-28"),
            other_month_hit(origin_id=2, month_slug="janeiro_2026", period="2026-01-01-to-2026-01-31"),
            other_month_hit(origin_id=5, month_slug="abril_2026", period="2026-04-01-to-2026-04-30"),
            other_month_hit(origin_id=6, month_slug="maio_2026", period="2026-05-01-to-2026-05-31"),
        )
    )
    scoped, degraded = scope_knowledge(knowledge, period="2026-03")
    assert len(scoped.hits) == 1
    assert scoped.hits[0].origin_id == 4
    assert degraded is False


def test_period_scoper_does_not_fallback_to_other_period() -> None:
    knowledge = ConhecimentoRecuperado(
        hits=(
            other_month_hit(origin_id=3, month_slug="fevereiro_2026", period="2026-02-01-to-2026-02-28"),
            other_month_hit(origin_id=2, month_slug="janeiro_2026", period="2026-01-01-to-2026-01-31"),
        )
    )
    scoped, degraded = scope_knowledge(knowledge, period="2026-03")
    assert len(scoped.hits) == 0
    assert degraded is True
