from __future__ import annotations

from pathlib import Path

import pytest

from orion_mcp_v3.api.email.models import EmailReport, EmailSection
from orion_mcp_v3.api.email.parsing import build_report_from_text
from orion_mcp_v3.api.email.parsing_rules import (
    LineRule,
    ParsingRulesConfig,
    SectionOpenRule,
    default_line_rules,
    default_section_rules,
)
from orion_mcp_v3.api.email.rule_engine import RuleEngine, build_report_from_rules

FIXTURE = Path("tests/fixtures/email/fechamento_gerencial_marco.txt")

_RANKING_EVIDENCE_BODY = (
    "Resposta direta: maior total liquido por tipo de pagamento: "
    "Cartão de Crédito (R$ 1.088.298,35).\n\n"
    "Resumo estatístico complementar (não substitui a resposta direta):\n"
    "Ranking por `total_liquido`:\n"
    "  1. Cartão de Crédito  R$ 1.088.298,35  (41,6%)\n"
    "  2. Concessionária  R$ 996.963,01  (38,1%)\n"
    "  3. PIX  R$ 367.870,98  (14,1%)\n"
    "  ... (+ 3 categorias)\n"
    "Dominante: Cartão de Crédito (41,6% do total). Concentração: alta (HHI=0,35)."
)

_DIRECT_ANSWER_BODY = (
    "Resposta direta: total pagamentos por tipo de pagamento:\n"
    "1. Cartão de Crédito: R$ 1.286.059,42\n"
    "2. Concessionária: R$ 913.134,71\n"
    "3. PIX: R$ 401.301,70"
)


def _section_snapshot(sections: tuple[EmailSection, ...]) -> list[dict[str, object]]:
    return [
        {
            "title": section.title,
            "kind": section.kind,
            "total": section.total,
            "highlight": section.highlight,
            "items": [(item.label, item.value, item.detail) for item in section.items],
            "notes": section.notes,
            "table_rows": len(section.tables[0].rows) if section.tables else 0,
        }
        for section in sections
    ]


def _report_core_snapshot(report: EmailReport) -> dict[str, object]:
    return {
        "headline": report.headline,
        "period": report.period,
        "sections": _section_snapshot(report.sections),
        "alerts": report.alerts,
        "actions": report.actions,
    }


def test_rule_engine_default_rules_match_legacy_parser() -> None:
    legacy = build_report_from_text(
        subject="Ranking",
        body=_RANKING_EVIDENCE_BODY,
        from_name="CarSoul",
        report_type="ranking",
    )
    rules = build_report_from_rules(
        subject="Ranking",
        body=_RANKING_EVIDENCE_BODY,
        from_name="CarSoul",
        report_type="ranking",
    )
    assert _report_core_snapshot(legacy) == _report_core_snapshot(rules)


def test_rule_engine_matches_direct_answer_list_sections() -> None:
    legacy = build_report_from_text(
        subject="Formas de pagamento",
        body=_DIRECT_ANSWER_BODY,
        from_name="CarSoul",
        report_type="ranking",
    )
    rules = build_report_from_rules(
        subject="Formas de pagamento",
        body=_DIRECT_ANSWER_BODY,
        from_name="CarSoul",
        report_type="ranking",
    )
    assert _report_core_snapshot(legacy) == _report_core_snapshot(rules)


def test_rule_engine_matches_fechamento_fixture_sections() -> None:
    body = FIXTURE.read_text(encoding="utf-8")
    legacy = build_report_from_text(subject="Fechamento", body=body, from_name="CarSoul", report_type="fechamento_gerencial")
    rules = build_report_from_rules(subject="Fechamento", body=body, from_name="CarSoul", report_type="fechamento_gerencial")
    assert [section.title for section in legacy.sections] == [section.title for section in rules.sections]
    assert _section_snapshot(legacy.sections) == _section_snapshot(rules.sections)


def test_rule_engine_matches_pipe_table_section() -> None:
    body = "\n".join(
        [
            "Detalhe por seção do fechamento gerencial:",
            "",
            "## Comissão por tipo de O.S.",
            "Template: fechamento_faturamento_comissao_tipo_os_concessionaria_periodo",
            "Linhas disponíveis: 2",
            "concessionaria | venda normal | financiamento | total comissão",
            "Concessionária A | R$ 120.000,00 | R$ 80.000,00 | R$ 200.000,00",
        ]
    )
    legacy = build_report_from_text(subject="Fechamento", body=body, from_name="CarSoul", report_type="fechamento_gerencial")
    rules = build_report_from_rules(subject="Fechamento", body=body, from_name="CarSoul", report_type="fechamento_gerencial")
    assert _report_core_snapshot(legacy) == _report_core_snapshot(rules)


def test_line_rule_highlight_sets_highlight_on_active_section() -> None:
    body = (
        "Faturamento por forma de pagamento — Total: R$ 2.713.158,18\n"
        "Destaque: Cartão de Crédito — R$ 1.352.045,28 (49,83%)\n"
        "Cartão de Crédito: R$ 1.352.045,28 (49,83%)"
    )
    legacy = build_report_from_text(subject="Fechamento", body=body, from_name="CarSoul", report_type="fechamento_gerencial")
    rules = build_report_from_rules(subject="Fechamento", body=body, from_name="CarSoul", report_type="fechamento_gerencial")

    assert _report_core_snapshot(legacy) == _report_core_snapshot(rules)
    section = rules.sections[0]
    assert section.title == "Faturamento por forma de pagamento"
    assert section.highlight is not None
    assert "Cartão de Crédito" in section.highlight


def test_line_rule_highlight_opens_destaques_from_direct_answer() -> None:
    body = "Resposta direta: total por tipo:\nDestaque: PIX lidera o período"
    legacy = build_report_from_text(subject="Ranking", body=body, from_name="Orion", report_type="ranking")
    rules = build_report_from_rules(subject="Ranking", body=body, from_name="Orion", report_type="ranking")

    assert _report_core_snapshot(legacy) == _report_core_snapshot(rules)
    destaques = next(section for section in rules.sections if section.title == "Destaques")
    assert destaques.highlight == "PIX lidera o período"


def test_line_rule_highlight_disabled_skips_destaque_lines() -> None:
    config = ParsingRulesConfig(
        sections=default_section_rules(),
        line_rules=(
            LineRule(
                id="dominante",
                pattern=r"^Dominante:\s*(?P<text>.+)$",
                effect="open_highlights",
                phase="promotion_early",
                enabled=False,
            ),
            LineRule(
                id="highlight",
                pattern=r"^Destaque:\s*(?P<highlight>.+)$",
                effect="set_highlight",
                phase="promotion_late",
                enabled=False,
            ),
        ),
    )
    body = (
        "Faturamento por forma de pagamento — Total: R$ 2.713.158,18\n"
        "Destaque: Cartão de Crédito — R$ 1.352.045,28 (49,83%)"
    )
    report = RuleEngine(config).parse_report(subject="Fechamento", body=body, from_name="Orion")
    section = report.sections[0]
    assert section.highlight is None


def test_line_rule_dominante_opens_destaques_with_highlight() -> None:
    body = (
        "Resumo estatístico complementar (não substitui a resposta direta):\n"
        "Ranking por `total_liquido`:\n"
        "  1. Cartão de Crédito  R$ 1.088.298,35  (41,6%)\n"
        "Dominante: Cartão de Crédito (41,6% do total)."
    )
    legacy = build_report_from_text(subject="Ranking", body=body, from_name="Orion", report_type="ranking")
    rules = build_report_from_rules(subject="Ranking", body=body, from_name="Orion", report_type="ranking")

    assert _report_core_snapshot(legacy) == _report_core_snapshot(rules)
    destaques = next(section for section in rules.sections if section.title == "Destaques")
    assert destaques.highlight == "Cartão de Crédito (41,6% do total)."


def test_line_rule_dominante_disabled_skips_dominante_lines() -> None:
    config = ParsingRulesConfig(
        sections=default_section_rules(),
        line_rules=(
            LineRule(
                id="dominante",
                pattern=r"^Dominante:\s*(?P<text>.+)$",
                effect="open_highlights",
                phase="promotion_early",
                enabled=False,
            ),
            *default_line_rules()[1:],
        ),
    )
    body = "Dominante: Cartão de Crédito (41,6% do total)."
    report = RuleEngine(config).parse_report(subject="Ranking", body=body, from_name="Orion")
    assert not any(section.title == "Destaques" for section in report.sections)


def test_line_rule_concentracao_appends_note_to_destaques() -> None:
    body = (
        "Resumo estatístico complementar (não substitui a resposta direta):\n"
        "Dominante: Cartão de Crédito (41,6% do total).\n"
        "Concentração: alta (HHI=0,35)."
    )
    legacy = build_report_from_text(subject="Ranking", body=body, from_name="Orion", report_type="ranking")
    rules = build_report_from_rules(subject="Ranking", body=body, from_name="Orion", report_type="ranking")

    assert _report_core_snapshot(legacy) == _report_core_snapshot(rules)
    destaques = next(section for section in rules.sections if section.title == "Destaques")
    assert destaques.highlight == "Cartão de Crédito (41,6% do total)."
    assert list(destaques.notes) == ["Concentração: alta (HHI=0,35)."]


def test_line_rule_concentracao_opens_destaques_when_missing() -> None:
    body = "Concentração: alta (HHI=0,35)."
    legacy = build_report_from_text(subject="Ranking", body=body, from_name="Orion", report_type="ranking")
    rules = build_report_from_rules(subject="Ranking", body=body, from_name="Orion", report_type="ranking")

    assert _report_core_snapshot(legacy) == _report_core_snapshot(rules)
    destaques = next(section for section in rules.sections if section.title == "Destaques")
    assert list(destaques.notes) == ["Concentração: alta (HHI=0,35)."]


def test_line_rule_concentracao_disabled_skips_concentracao_lines() -> None:
    config = ParsingRulesConfig(
        sections=default_section_rules(),
        line_rules=(
            default_line_rules()[0],
            LineRule(
                id="concentracao",
                pattern=r"^Concentra[cç][aã]o:\s*(?P<text>.+)$",
                effect="append_note",
                phase="promotion_early",
                value_from_group="text",
                note_prefix="Concentração: ",
                enabled=False,
            ),
            default_line_rules()[3],
        ),
    )
    body = "Concentração: alta (HHI=0,35)."
    report = RuleEngine(config).parse_report(subject="Ranking", body=body, from_name="Orion")
    assert not any(section.title == "Destaques" for section in report.sections)


def test_line_rule_omitted_appends_note_to_active_section() -> None:
    body = (
        "Resumo estatístico complementar (não substitui a resposta direta):\n"
        "Ranking por `total_liquido`:\n"
        "  1. Cartão de Crédito  R$ 1.088.298,35  (41,6%)\n"
        "  ... (+ 3 categorias)\n"
        "Dominante: Cartão de Crédito (41,6% do total)."
    )
    legacy = build_report_from_text(subject="Ranking", body=body, from_name="Orion", report_type="ranking")
    rules = build_report_from_rules(subject="Ranking", body=body, from_name="Orion", report_type="ranking")

    assert _report_core_snapshot(legacy) == _report_core_snapshot(rules)
    ranking = next(section for section in rules.sections if section.title == "Resumo estatístico complementar")
    assert any("... (+ 3 categorias)" in note for note in ranking.notes)


def test_line_rule_omitted_skips_when_no_active_section() -> None:
    body = "... (+ 3 categorias)"
    legacy = build_report_from_text(subject="Ranking", body=body, from_name="Orion", report_type="ranking")
    rules = build_report_from_rules(subject="Ranking", body=body, from_name="Orion", report_type="ranking")

    assert _report_core_snapshot(legacy) == _report_core_snapshot(rules)
    assert not rules.sections


def test_line_rule_omitted_disabled_skips_omitted_lines() -> None:
    config = ParsingRulesConfig(
        sections=default_section_rules(),
        line_rules=(
            default_line_rules()[0],
            default_line_rules()[1],
            LineRule(
                id="omitted_categories",
                pattern=r"^\.\.\.\s*\(\+\s*\d+",
                effect="append_omitted",
                phase="omitted",
                enabled=False,
            ),
            default_line_rules()[3],
        ),
    )
    body = (
        "Resumo estatístico complementar (não substitui a resposta direta):\n"
        "Ranking por `total_liquido`:\n"
        "  ... (+ 3 categorias)"
    )
    report = RuleEngine(config).parse_report(subject="Ranking", body=body, from_name="Orion")
    ranking = next(section for section in report.sections if section.title == "Resumo estatístico complementar")
    assert not any("... (+ 3 categorias)" in note for note in ranking.notes)


def test_rule_engine_respects_custom_section_rule() -> None:
    custom = ParsingRulesConfig(
        sections=(
            *default_section_rules(),
            SectionOpenRule(
                id="custom_overview",
                title="Visão geral",
                kind="overview",
                pattern=r"^Visão geral\b",
            ),
        ),
        line_rules=default_line_rules(),
    )
    body = "Visão geral\nResposta direta: total: R$ 10,00"
    report = RuleEngine(custom).parse_report(subject="Teste", body=body, from_name="Orion")
    titles = [section.title for section in report.sections]
    assert titles[0] == "Visão geral"
    assert "Resposta direta" in titles


@pytest.mark.parametrize(
    "body",
    [
        _RANKING_EVIDENCE_BODY,
        _DIRECT_ANSWER_BODY,
    ],
)
def test_rule_engine_section_titles_match_legacy(body: str) -> None:
    legacy = build_report_from_text(subject="Teste", body=body, from_name="Orion", report_type="ranking")
    rules = build_report_from_rules(subject="Teste", body=body, from_name="Orion", report_type="ranking")
    assert [section.title for section in legacy.sections] == [section.title for section in rules.sections]
