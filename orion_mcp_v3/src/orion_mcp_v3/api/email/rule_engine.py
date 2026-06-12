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
    MarkdownHeadingRouter,
    ParsingRulesConfig,
    SectionOpenRule,
    SectionRuleMatch,
    default_collection_prefix_rules,
    default_heading_router,
    match_collection_prefix_rule,
    match_heading_route,
    match_line_rules,
)

_MIDDLE_SECTION_RULE_IDS = frozenset({"direct_answer", "section_total"})

_HEADLINE_RX = re.compile(r"^direct_answer_set\.headline:\s*(?P<headline>.+)$", re.I)
_NOTE_RX = re.compile(r"^(Detalhe|Top\s+\d+|Observação)\b(?P<note>.*)$", re.I)


class RuleEngine:
    """Parser determinístico orientado por regras declarativas de seção."""

    def __init__(self, rules_config: ParsingRulesConfig | None = None) -> None:
        self._rules_config = rules_config or ParsingRulesConfig.default()
        self._compiled_by_id = self._rules_config.compile_by_id()
        self._compiled_line_rules = self._rules_config.compile_line_rules()
        self._heading_router = self._rules_config.heading_router or default_heading_router()
        self._heading_rx = self._heading_router.compile()
        self._collection_prefix_rules = (
            self._rules_config.collection_prefix_rules or default_collection_prefix_rules()
        )

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
        raw_line: str,
        flush: Callable[[], None],
        clear_collection_mode: Callable[[], None],
    ) -> SectionDraft | None:
        rule = match.rule
        if rule.effect == "set_highlight":
            return _apply_set_highlight(
                match,
                rule,
                current=current,
                flush=flush,
            )
        if rule.effect == "open_highlights":
            return _apply_open_highlights(
                match,
                rule,
                flush=flush,
                clear_collection_mode=clear_collection_mode,
            )
        if rule.effect == "append_note":
            return _apply_append_note(
                match,
                rule,
                current=current,
                flush=flush,
            )
        if rule.effect == "append_omitted":
            return _apply_append_omitted(current=current, raw_line=raw_line)
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

        def clear_collection_mode() -> None:
            nonlocal collection_mode
            collection_mode = None

        def set_collection_mode(mode: str) -> None:
            nonlocal collection_mode
            collection_mode = mode

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

            heading_match = self._heading_rx.match(raw) if self._heading_rx is not None else None
            if heading_match is not None:
                title = heading_match.group("title").strip()
                current = _apply_markdown_heading(
                    title,
                    router=self._heading_router,
                    flush=flush,
                    clear_collection_mode=clear_collection_mode,
                    set_collection_mode=set_collection_mode,
                )
                continue

            section_match = self._match_middle_section_rules(raw)
            if section_match is not None:
                apply_section_match(section_match, raw_line=raw)
                continue

            early_line_match = match_line_rules(raw, self._compiled_line_rules, phase="promotion_early")
            if early_line_match is not None:
                current = self._apply_line_rule(
                    early_line_match,
                    current=current,
                    raw_line=raw,
                    flush=flush,
                    clear_collection_mode=clear_collection_mode,
                )
                continue

            omitted_line_match = match_line_rules(raw, self._compiled_line_rules, phase="omitted")
            if omitted_line_match is not None:
                current = self._apply_line_rule(
                    omitted_line_match,
                    current=current,
                    raw_line=raw,
                    flush=flush,
                    clear_collection_mode=clear_collection_mode,
                )
                continue

            if raw.casefold().startswith(self._rules_config.skip_line_prefixes):
                continue

            total_match = self._match_rule("section_total", raw)
            if total_match is not None:
                apply_section_match(total_match, raw_line=raw)
                continue

            line_match = match_line_rules(raw, self._compiled_line_rules, phase="promotion_late")
            if line_match is not None:
                current = self._apply_line_rule(
                    line_match,
                    current=current,
                    raw_line=raw,
                    flush=flush,
                    clear_collection_mode=clear_collection_mode,
                )
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

            prefix_rule = match_collection_prefix_rule(raw, self._collection_prefix_rules)
            if prefix_rule is not None:
                flush()
                set_collection_mode(prefix_rule.collection_mode)
                if prefix_rule.collection_mode == "alerts":
                    alerts.append(raw)
                else:
                    actions.append(raw)
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
    flush: Callable[[], None],
) -> SectionDraft:
    if current is None or current.title in rule.flush_if_missing_or_current_title_in:
        flush()
        current = SectionDraft(title=rule.target_section_title, kind=rule.target_section_kind)
    highlight = match.groups.get(rule.value_from_group, "").strip()
    if highlight:
        current.highlight = highlight
    return current


def _apply_open_highlights(
    match: LineRuleMatch,
    rule: LineRule,
    *,
    flush: Callable[[], None],
    clear_collection_mode: Callable[[], None],
) -> SectionDraft:
    flush()
    clear_collection_mode()
    current = SectionDraft(title=rule.target_section_title, kind=rule.target_section_kind, total=None)
    highlight = match.groups.get(rule.value_from_group, "").strip()
    if highlight:
        current.highlight = highlight
    return current


def _apply_append_note(
    match: LineRuleMatch,
    rule: LineRule,
    *,
    current: SectionDraft | None,
    flush: Callable[[], None],
) -> SectionDraft:
    if current is None or current.title != rule.target_section_title:
        flush()
        current = SectionDraft(title=rule.target_section_title, kind=rule.target_section_kind)
    text = match.groups.get(rule.value_from_group, "").strip()
    if text:
        current.notes.append(f"{rule.note_prefix}{text}")
    return current


def _apply_append_omitted(
    *,
    current: SectionDraft | None,
    raw_line: str,
) -> SectionDraft | None:
    if current is not None:
        current.notes.append(raw_line)
    return current


def _apply_markdown_heading(
    title: str,
    *,
    router: MarkdownHeadingRouter,
    flush: Callable[[], None],
    clear_collection_mode: Callable[[], None],
    set_collection_mode: Callable[[str], None],
) -> SectionDraft | None:
    flush()
    route = match_heading_route(title, router.routes)
    if route is None:
        clear_collection_mode()
        return SectionDraft(title=title, kind=section_kind(title))
    if route.effect == "collect_alerts":
        set_collection_mode("alerts")
        return None
    if route.effect == "collect_actions":
        set_collection_mode("actions")
        return None
    clear_collection_mode()
    return SectionDraft(title=title, kind=section_kind(title))
