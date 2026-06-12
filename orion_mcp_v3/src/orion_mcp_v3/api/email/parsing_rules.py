"""Regras declarativas de abertura de seção para o motor de parsing (Fase 2)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SectionRuleBehavior = Literal["open", "open_with_detail", "append_note", "open_with_total"]
LineRuleEffect = Literal["set_highlight", "open_highlights", "append_note", "append_omitted"]
LineRulePhase = Literal["promotion_early", "promotion_late", "omitted"]


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
class LineRule:
    """Regra de linha com efeito sobre a seção ativa (Fase 3 — PR1+)."""

    id: str
    pattern: str
    effect: LineRuleEffect
    phase: LineRulePhase = "promotion_late"
    value_from_group: str = "highlight"
    note_prefix: str = ""
    target_section_title: str = "Destaques"
    target_section_kind: str = "default"
    flush_if_missing_or_current_title_in: tuple[str, ...] = ("Resposta direta",)
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class CompiledLineRule:
    rule: LineRule
    pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class LineRuleMatch:
    rule: LineRule
    groups: dict[str, str]


@dataclass(frozen=True, slots=True)
class ParsingRulesConfig:
    """Configuração do motor de regras — ordem de `sections` e `line_rules` define prioridade."""

    sections: tuple[SectionOpenRule, ...]
    line_rules: tuple[LineRule, ...] = ()
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

    def compile_line_rules(self) -> tuple[CompiledLineRule, ...]:
        return tuple(
            CompiledLineRule(rule=rule, pattern=re.compile(rule.pattern, re.I))
            for rule in self.line_rules
            if rule.enabled
        )

    def rule_by_id(self, rule_id: str) -> SectionOpenRule | None:
        for rule in self.sections:
            if rule.id == rule_id and rule.enabled:
                return rule
        return None

    @classmethod
    def default(cls) -> ParsingRulesConfig:
        return cls(sections=default_section_rules(), line_rules=default_line_rules())


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


def default_line_rules() -> tuple[LineRule, ...]:
    """Regras de linha padrão — PR1–PR4 Destaque, Dominante, Concentração, Omitted."""
    return (
        LineRule(
            id="dominante",
            pattern=r"^Dominante:\s*(?P<text>.+)$",
            effect="open_highlights",
            phase="promotion_early",
            value_from_group="text",
            target_section_title="Destaques",
            target_section_kind="default",
        ),
        LineRule(
            id="concentracao",
            pattern=r"^Concentra[cç][aã]o:\s*(?P<text>.+)$",
            effect="append_note",
            phase="promotion_early",
            value_from_group="text",
            note_prefix="Concentração: ",
            target_section_title="Destaques",
            target_section_kind="default",
        ),
        LineRule(
            id="omitted_categories",
            pattern=r"^\.\.\.\s*\(\+\s*\d+",
            effect="append_omitted",
            phase="omitted",
        ),
        LineRule(
            id="highlight",
            pattern=r"^Destaque:\s*(?P<highlight>.+)$",
            effect="set_highlight",
            phase="promotion_late",
            value_from_group="highlight",
            target_section_title="Destaques",
            target_section_kind="default",
            flush_if_missing_or_current_title_in=("Resposta direta",),
        ),
    )


def match_line_rules(
    raw: str,
    compiled_rules: tuple[CompiledLineRule, ...],
    *,
    phase: LineRulePhase | None = None,
) -> LineRuleMatch | None:
    for compiled in compiled_rules:
        if phase is not None and compiled.rule.phase != phase:
            continue
        match = compiled.pattern.match(raw)
        if match is None:
            continue
        groups = {key: (value or "").strip() for key, value in match.groupdict().items() if value is not None}
        return LineRuleMatch(rule=compiled.rule, groups=groups)
    return None


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
