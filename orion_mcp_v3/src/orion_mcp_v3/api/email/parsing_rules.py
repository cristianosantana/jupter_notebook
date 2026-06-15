"""Regras declarativas de abertura de seção para o motor de parsing (Fase 2)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

SectionRuleBehavior = Literal["open", "open_with_detail", "append_note", "open_with_total"]
LineRuleEffect = Literal["set_highlight", "open_highlights", "append_note", "append_omitted"]
LineRulePhase = Literal["promotion_early", "promotion_late", "omitted"]
HeadingRouteEffect = Literal["open_section", "collect_alerts", "collect_actions"]
CollectionMode = Literal["alerts", "actions"]
SectionItemEffect = Literal["append_pipe_row", "append_metric"]

if TYPE_CHECKING:
    from orion_mcp_v3.api.email.parsing import SectionDraft


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
class HeadingRoute:
    """Rota de `## título` — primeira keyword casada define o efeito (PR5)."""

    id: str
    keywords: tuple[str, ...]
    effect: HeadingRouteEffect
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class MarkdownHeadingRouter:
    """Roteador de headings markdown — seção vs alerta vs ação."""

    pattern: str = r"^##\s+(?P<title>.+?)\s*$"
    routes: tuple[HeadingRoute, ...] = ()
    enabled: bool = True

    def compile(self) -> re.Pattern[str] | None:
        if not self.enabled:
            return None
        return re.compile(self.pattern)


@dataclass(frozen=True, slots=True)
class CollectionPrefixRule:
    """Gatilho standalone por prefixo de linha — entra em modo de coleta (PR6+)."""

    id: str
    collection_mode: CollectionMode
    prefixes: tuple[str, ...]
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class CollectionContinuationRule:
    """Append de linhas enquanto `collection_mode` coincide (PR8)."""

    collection_mode: CollectionMode
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class CollectionFallbackRule:
    """Fallback sem seção ativa — alertas já populados e ações vazias (PR8)."""

    id: str
    target: CollectionMode = "alerts"
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class CollectionContinuationPolicy:
    """Política de continuação e fallback do modo alertas/ações (PR8)."""

    continuation_rules: tuple[CollectionContinuationRule, ...] = ()
    fallback_rules: tuple[CollectionFallbackRule, ...] = ()
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class NoteLineRule:
    """Linha de nota em seção ativa — Detalhe / Top N / Observação (PR9)."""

    id: str
    pattern: str
    requires_active_section: bool = True
    split_inline_items: bool = True
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class CompiledNoteLineRule:
    rule: NoteLineRule
    pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class NoteLineMatch:
    rule: NoteLineRule
    groups: dict[str, str]


@dataclass(frozen=True, slots=True)
class SectionItemRule:
    """Regra de item em seção ativa — pipe table ou métrica (PR10)."""

    id: str
    effect: SectionItemEffect
    requires_active_section: bool = True
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SectionItemRulesPolicy:
    """Política de append de métricas e linhas pipe em seção ativa (PR10)."""

    item_rules: tuple[SectionItemRule, ...] = ()
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class ParsingRulesConfig:
    """Configuração do motor de regras — ordem de `sections` e `line_rules` define prioridade."""

    sections: tuple[SectionOpenRule, ...]
    line_rules: tuple[LineRule, ...] = ()
    heading_router: MarkdownHeadingRouter | None = None
    collection_prefix_rules: tuple[CollectionPrefixRule, ...] = ()
    collection_continuation: CollectionContinuationPolicy | None = None
    note_line_rules: tuple[NoteLineRule, ...] = ()
    section_item_rules: SectionItemRulesPolicy | None = None
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

    def compile_note_line_rules(self) -> tuple[CompiledNoteLineRule, ...]:
        return tuple(
            CompiledNoteLineRule(rule=rule, pattern=re.compile(rule.pattern, re.I))
            for rule in self.note_line_rules
            if rule.enabled
        )

    def rule_by_id(self, rule_id: str) -> SectionOpenRule | None:
        for rule in self.sections:
            if rule.id == rule_id and rule.enabled:
                return rule
        return None

    @classmethod
    def default(cls) -> ParsingRulesConfig:
        return cls(
            sections=default_section_rules(),
            line_rules=default_line_rules(),
            heading_router=default_heading_router(),
            collection_prefix_rules=default_collection_prefix_rules(),
            collection_continuation=default_collection_continuation_policy(),
            note_line_rules=default_note_line_rules(),
            section_item_rules=default_section_item_rules(),
        )


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


def default_heading_router() -> MarkdownHeadingRouter:
    """Rotas padrão espelhando o roteamento `##` do parser legado."""
    return MarkdownHeadingRouter(
        routes=(
            HeadingRoute(
                id="alerts_heading",
                keywords=("alerta", "concilia"),
                effect="collect_alerts",
            ),
            HeadingRoute(
                id="actions_heading",
                keywords=("conclus", "acion"),
                effect="collect_actions",
            ),
        ),
    )


def default_collection_continuation_policy() -> CollectionContinuationPolicy:
    """Continuação e fallback padrão espelhando `collection_mode` do parser legado."""
    return CollectionContinuationPolicy(
        continuation_rules=(
            CollectionContinuationRule(collection_mode="alerts"),
            CollectionContinuationRule(collection_mode="actions"),
        ),
        fallback_rules=(
            CollectionFallbackRule(id="alerts_without_section", target="alerts"),
        ),
    )


def default_collection_prefix_rules() -> tuple[CollectionPrefixRule, ...]:
    """Prefixos standalone padrão espelhando `is_alert()` e `is_action()` do parser legado."""
    return (
        CollectionPrefixRule(
            id="alert_standalone",
            collection_mode="alerts",
            prefixes=(
                "registros com valor zero",
                "discrepância",
                "discrepancia",
            ),
        ),
        CollectionPrefixRule(
            id="action_standalone",
            collection_mode="actions",
            prefixes=(
                "priorizar",
                "negociar",
                "corrigir",
                "conciliar",
                "revisar",
            ),
        ),
    )


def default_note_line_rules() -> tuple[NoteLineRule, ...]:
    """Regras padrão espelhando `_NOTE_RX` do parser legado."""
    return (
        NoteLineRule(
            id="detail_top_observation",
            pattern=r"^(Detalhe|Top\s+\d+|Observação)\b(?P<note>.*)$",
        ),
    )


def default_section_item_rules() -> SectionItemRulesPolicy:
    """Regras padrão espelhando pipe tables e métricas do parser legado."""
    return SectionItemRulesPolicy(
        item_rules=(
            SectionItemRule(id="pipe_table_row", effect="append_pipe_row"),
            SectionItemRule(id="metric_line", effect="append_metric"),
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


def match_note_line_rule(
    raw: str,
    compiled_rules: tuple[CompiledNoteLineRule, ...],
) -> NoteLineMatch | None:
    """Retorna a primeira regra de nota que corresponde à linha."""
    for compiled in compiled_rules:
        match = compiled.pattern.match(raw)
        if match is None:
            continue
        groups = {key: (value or "").strip() for key, value in match.groupdict().items() if value is not None}
        return NoteLineMatch(rule=compiled.rule, groups=groups)
    return None


def try_apply_section_item_rules(
    *,
    raw: str,
    policy: SectionItemRulesPolicy,
    current_section: SectionDraft | None,
) -> bool:
    """Append pipe row ou métrica se regra e detector casarem. Retorna True se tratou a linha."""
    from orion_mcp_v3.api.email.parsing import (
        looks_like_metric,
        looks_like_pipe_table_line,
        parse_metric_item,
    )

    if not policy.enabled or current_section is None:
        return False

    for rule in policy.item_rules:
        if not rule.enabled:
            continue
        if rule.requires_active_section and current_section is None:
            continue
        if rule.effect == "append_pipe_row":
            if looks_like_pipe_table_line(raw):
                current_section.add_table_line(raw)
                return True
        elif rule.effect == "append_metric":
            if looks_like_metric(raw):
                current_section.items.append(parse_metric_item(raw))
                return True
    return False


def try_apply_collection_continuation(
    *,
    raw: str,
    policy: CollectionContinuationPolicy,
    collection_mode: str | None,
    current_section: object | None,
    alerts: list[str],
    actions: list[str],
) -> bool:
    """Append em alertas/ações se continuação ou fallback aplicar. Retorna True se tratou a linha."""
    if not policy.enabled:
        return False

    if collection_mode is not None:
        for rule in policy.continuation_rules:
            if not rule.enabled:
                continue
            if collection_mode == rule.collection_mode:
                if rule.collection_mode == "alerts":
                    alerts.append(raw)
                else:
                    actions.append(raw)
                return True

    for rule in policy.fallback_rules:
        if not rule.enabled:
            continue
        if rule.target == "alerts" and current_section is None and alerts and not actions:
            alerts.append(raw)
            return True
    return False


def match_collection_prefix_rule(
    raw: str,
    rules: tuple[CollectionPrefixRule, ...],
) -> CollectionPrefixRule | None:
    """Retorna a primeira regra cujo prefixo casa com a linha normalizada."""
    normalized = raw.casefold()
    for rule in rules:
        if not rule.enabled:
            continue
        if normalized.startswith(rule.prefixes):
            return rule
    return None


def match_heading_route(title: str, routes: tuple[HeadingRoute, ...]) -> HeadingRoute | None:
    """Retorna a primeira rota cuja keyword aparece no título normalizado."""
    normalized = title.casefold()
    for route in routes:
        if not route.enabled:
            continue
        if any(keyword in normalized for keyword in route.keywords):
            return route
    return None


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
