"""Regras declarativas de abertura de seção para o motor de parsing (Fase 2)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SectionRuleBehavior = Literal["open", "open_with_detail", "append_note", "open_with_total"]


@dataclass(frozen=True, slots=True)
class SectionOpenRule:
    """Regra que identifica o início (ou continuação) de uma seção estruturada."""

    id: str
    title: str
    kind: str
    pattern: str
    behavior: SectionRuleBehavior = "open"
    title_from_group: str | None = None
    detail_from_group: str | None = None
    total_from_group: str | None = None
    kind_resolver: Literal["fixed", "section_kind"] = "fixed"
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class CompiledSectionRule:
    rule: SectionOpenRule
    pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class SectionRuleMatch:
    rule: SectionOpenRule
    groups: dict[str, str]


@dataclass(frozen=True, slots=True)
class ParsingRulesConfig:
    """Configuração do motor de regras — ordem de `sections` define prioridade."""

    sections: tuple[SectionOpenRule, ...]
    skip_line_prefixes: tuple[str, ...] = (
        "template:",
        "linhas disponíveis:",
        "linhas disponiveis:",
    )

    def compile(self) -> tuple[CompiledSectionRule, ...]:
        return tuple(
            CompiledSectionRule(rule=rule, pattern=re.compile(rule.pattern, re.I))
            for rule in self.sections
            if rule.enabled
        )

    def compile_by_id(self) -> dict[str, CompiledSectionRule]:
        return {compiled.rule.id: compiled for compiled in self.compile()}

    def rule_by_id(self, rule_id: str) -> SectionOpenRule | None:
        for rule in self.sections:
            if rule.id == rule_id and rule.enabled:
                return rule
        return None

    @classmethod
    def default(cls) -> ParsingRulesConfig:
        return cls(sections=default_section_rules())


def default_section_rules() -> tuple[SectionOpenRule, ...]:
    """Regras padrão espelhando os openers do parser legado."""
    return (
        SectionOpenRule(
            id="direct_answer",
            title="Resposta direta",
            kind="ranking",
            pattern=r"^Resposta direta:\s*(?P<detail>.*)$",
            behavior="open_with_detail",
            detail_from_group="detail",
        ),
        SectionOpenRule(
            id="complementary",
            title="Resumo estatístico complementar",
            kind="ranking",
            pattern=r"^Resumo estatístico complementar\b",
        ),
        SectionOpenRule(
            id="highlights",
            title="Destaques",
            kind="default",
            pattern=r"^Destaques?\s*:?\s*$",
        ),
        SectionOpenRule(
            id="ranking_header",
            title="Ranking",
            kind="ranking",
            pattern=r"^Ranking por\b",
            behavior="append_note",
        ),
        SectionOpenRule(
            id="section_total",
            title="",
            kind="default",
            pattern=r"^(?P<title>.+?)\s+—\s+Total(?:\s*\(.+?\))?:\s*(?P<total>R\$\s*[\d.,]+)",
            behavior="open_with_total",
            title_from_group="title",
            total_from_group="total",
            kind_resolver="section_kind",
        ),
    )


def match_section_rule(raw: str, compiled_rules: tuple[CompiledSectionRule, ...]) -> SectionRuleMatch | None:
    """Retorna a primeira regra compilada que corresponde à linha."""
    for compiled in compiled_rules:
        match = compiled.pattern.match(raw)
        if match is None:
            continue
        groups = {key: (value or "").strip() for key, value in match.groupdict().items() if value is not None}
        return SectionRuleMatch(rule=compiled.rule, groups=groups)
    return None


def match_section_rule_by_id(
    raw: str,
    *,
    config: ParsingRulesConfig,
    rule_id: str,
) -> SectionRuleMatch | None:
    rule = config.rule_by_id(rule_id)
    if rule is None:
        return None
    match = re.compile(rule.pattern, re.I).match(raw)
    if match is None:
        return None
    groups = {key: (value or "").strip() for key, value in match.groupdict().items() if value is not None}
    return SectionRuleMatch(rule=rule, groups=groups)
