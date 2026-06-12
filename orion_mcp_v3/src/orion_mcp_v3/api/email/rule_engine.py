"""Motor de parsing baseado em regras — Fase 2 (paralelo ao parser legado, não ligado em produção)."""

from __future__ import annotations

import re
from collections.abc import Callable

from orion_mcp_v3.api.email.models import EmailReport, EmailSection
from orion_mcp_v3.api.email.parsing import (
    SectionDraft,
    extract_period,
    first_meaningful_line,
    inline_detail_items,
    is_action,
    is_alert,
    looks_like_metric,
    looks_like_pipe_table_line,
    normalized_lines,
    parse_metric_item,
    section_kind,
    strip_numbered_prefix,
)
from orion_mcp_v3.api.email.parsing_config import EmailParsingConfig, apply_parsing_policy
from orion_mcp_v3.api.email.parsing_rules import (
    LineRule,
    LineRuleMatch,
    ParsingRulesConfig,
    SectionOpenRule,
    SectionRuleMatch,
    match_line_rules,
)

_MIDDLE_SECTION_RULE_IDS = frozenset({"direct_answer", "section_total"})

_HEADLINE_RX = re.compile(r"^direct_answer_set\.headline:\s*(?P<headline>.+)$", re.I)
_HEADING_RX = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_NOTE_RX = re.compile(r"^(Detalhe|Top\s+\d+|Observação)\b(?P<note>.*)$", re.I)
_DOMINANTE_RX = re.compile(r"^Dominante:\s*(?P<text>.+)$", re.I)
_CONCENTRACAO_RX = re.compile(r"^Concentra[cç][aã]o:\s*(?P<text>.+)$", re.I)
_OMITTED_CATEGORIES_RX = re.compile(r"^\.\.\.\s*\(\+\s*\d+", re.I)


class RuleEngine:
    """Parser determinístico orientado por regras declarativas de seção."""

    def __init__(self, rules_config: ParsingRulesConfig | None = None) -> None:
        self._rules_config = rules_config or ParsingRulesConfig.default()
        self._compiled_by_id = self._rules_config.compile_by_id()
        self._compiled_line_rules = self._rules_config.compile_line_rules()

    def _match_rule(self, rule_id: str, raw: str) -> SectionRuleMatch | None:
        compiled = self._compiled_by_id.get(rule_id)
        if compiled is None:
            return None
        match = compiled.pattern.match(raw)
        if match is None:
            return None
        groups = {key: (value or "").strip() for key, value in match.groupdict().items() if value is not None}
        return SectionRuleMatch(rule=compiled.rule, groups=groups)

    def _match_middle_section_rules(self, raw: str) -> SectionRuleMatch | None:
        for rule in self._rules_config.sections:
            if rule.id in _MIDDLE_SECTION_RULE_IDS or not rule.enabled:
                continue
            matched = self._match_rule(rule.id, raw)
            if matched is not None:
                return matched
        return None

    def _apply_line_rule(
        self,
        match: LineRuleMatch,
        *,
        current: SectionDraft | None,
        flush: Callable[[], None],
    ) -> SectionDraft:
        rule = match.rule
        if rule.effect == "set_highlight":
            return _apply_set_highlight(
                match,
                rule,
                current=current,
                flush=flush,
            )
        return current

    def parse_report(
        self,
        *,
        subject: str,
        body: str,
        from_name: str = "Orion",
        report_type: str = "generic",
        parsing_config: EmailParsingConfig | None = None,
    ) -> EmailReport:
        headline: str | None = None
        period: str | None = None
        sections: list[EmailSection] = []
        alerts: list[str] = []
        actions: list[str] = []
        current: SectionDraft | None = None
        collection_mode: str | None = None

        def flush() -> None:
            nonlocal current
            if current is not None:
                sections.append(current.to_section())
            current = None

        def apply_section_match(match: SectionRuleMatch, *, raw_line: str) -> None:
            nonlocal current, collection_mode
            rule = match.rule
            if rule.behavior == "append_note":
                if current is None:
                    current = SectionDraft(title=rule.title, kind=rule.kind)
                current.notes.append(raw_line)
                return
            flush()
            collection_mode = None
            title = _resolve_title(rule, match)
            kind = _resolve_kind(rule, title)
            total = match.groups.get(rule.total_from_group or "") if rule.total_from_group else None
            current = SectionDraft(title=title, kind=kind, total=total or None)
            if rule.behavior == "open_with_detail" and rule.detail_from_group:
                detail = match.groups.get(rule.detail_from_group, "").strip()
                if detail:
                    current.notes.append(detail)

        for raw_line in normalized_lines(body):
            raw = strip_numbered_prefix(raw_line)

            headline_match = _HEADLINE_RX.match(raw)
            if headline_match:
                headline = headline_match.group("headline").strip()
                period = extract_period(headline) or period
                continue

            direct_match = self._match_rule("direct_answer", raw)
            if direct_match is not None:
                apply_section_match(direct_match, raw_line=raw)
                continue

            heading_match = _HEADING_RX.match(raw)
            if heading_match:
                flush()
                title = heading_match.group("title").strip()
                normalized_title = title.casefold()
                if "alerta" in normalized_title or "concilia" in normalized_title:
                    collection_mode = "alerts"
                    continue
                if "conclus" in normalized_title or "acion" in normalized_title:
                    collection_mode = "actions"
                    continue
                collection_mode = None
                current = SectionDraft(title=title, kind=section_kind(title))
                continue

            section_match = self._match_middle_section_rules(raw)
            if section_match is not None:
                apply_section_match(section_match, raw_line=raw)
                continue

            dominante_match = _DOMINANTE_RX.match(raw)
            if dominante_match:
                flush()
                collection_mode = None
                current = SectionDraft(title="Destaques", kind="default", total=None)
                current.highlight = dominante_match.group("text").strip()
                continue

            concentracao_match = _CONCENTRACAO_RX.match(raw)
            if concentracao_match:
                if current is None or current.title != "Destaques":
                    flush()
                    current = SectionDraft(title="Destaques", kind="default")
                note = f"Concentração: {concentracao_match.group('text').strip()}"
                current.notes.append(note)
                continue

            if _OMITTED_CATEGORIES_RX.match(raw):
                if current is not None:
                    current.notes.append(raw)
                continue

            if raw.casefold().startswith(self._rules_config.skip_line_prefixes):
                continue

            total_match = self._match_rule("section_total", raw)
            if total_match is not None:
                apply_section_match(total_match, raw_line=raw)
                continue

            line_match = match_line_rules(raw, self._compiled_line_rules, phase="promotion")
            if line_match is not None:
                current = self._apply_line_rule(line_match, current=current, flush=flush)
                continue

            note_match = _NOTE_RX.match(raw)
            if note_match and current is not None:
                inline_items = inline_detail_items(raw)
                if inline_items:
                    current.items.extend(inline_items)
                    current.notes.append(raw.split(":", 1)[0].strip() + ":")
                else:
                    current.notes.append(raw)
                continue

            if is_alert(raw):
                flush()
                collection_mode = "alerts"
                alerts.append(raw)
                continue

            if is_action(raw):
                flush()
                collection_mode = "actions"
                actions.append(raw)
                continue

            if collection_mode == "alerts":
                alerts.append(raw)
                continue

            if collection_mode == "actions":
                actions.append(raw)
                continue

            if current is None and alerts and not actions:
                alerts.append(raw)
                continue

            if current is not None and looks_like_pipe_table_line(raw):
                current.add_table_line(raw)
                continue

            if current is not None and looks_like_metric(raw):
                current.items.append(parse_metric_item(raw))
                continue

        flush()
        if headline is None:
            headline = first_meaningful_line(body)
        report = EmailReport(
            report_type=report_type,
            subject=subject,
            from_name=from_name,
            headline=headline,
            period=period,
            sections=tuple(sections),
            alerts=tuple(alerts),
            actions=tuple(actions),
        )
        if parsing_config is not None:
            return apply_parsing_policy(report, parsing_config)
        return report


def build_report_from_rules(
    *,
    subject: str,
    body: str,
    from_name: str = "Orion",
    report_type: str = "generic",
    rules_config: ParsingRulesConfig | None = None,
    parsing_config: EmailParsingConfig | None = None,
) -> EmailReport:
    """API pública do motor de regras — ainda não ligada ao factory/sender."""
    return RuleEngine(rules_config).parse_report(
        subject=subject,
        body=body,
        from_name=from_name,
        report_type=report_type,
        parsing_config=parsing_config,
    )


def _resolve_title(rule: SectionOpenRule, match: SectionRuleMatch) -> str:
    if rule.title_from_group:
        return match.groups.get(rule.title_from_group, rule.title).strip() or rule.title
    return rule.title


def _resolve_kind(rule: SectionOpenRule, title: str) -> str:
    if rule.kind_resolver == "section_kind":
        return section_kind(title)
    return rule.kind


def _apply_set_highlight(
    match: LineRuleMatch,
    rule: LineRule,
    *,
    current: SectionDraft | None,
    flush: callable,
) -> SectionDraft:
    if current is None or current.title in rule.flush_if_missing_or_current_title_in:
        flush()
        current = SectionDraft(title=rule.target_section_title, kind=rule.target_section_kind)
    highlight = match.groups.get(rule.value_from_group, "").strip()
    if highlight:
        current.highlight = highlight
    return current
