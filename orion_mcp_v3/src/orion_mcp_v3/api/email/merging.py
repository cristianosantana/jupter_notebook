"""Fusão de relatórios LLM com fallback determinístico e narrativa."""

from __future__ import annotations

import re

from orion_mcp_v3.api.email.constants import CROSS_SECTION_PREFIXES, FECHAMENTO_SECTION_TITLES
from orion_mcp_v3.api.email.models import EmailReport, EmailSection


def merge_narrative_reports(
    report: EmailReport,
    fallback: EmailReport,
    *,
    prefer_fallback_summary: bool = False,
) -> EmailReport:
    executive_summary = (
        fallback.executive_summary
        if prefer_fallback_summary and fallback.executive_summary
        else report.executive_summary or fallback.executive_summary
    )
    return EmailReport(
        report_type=report.report_type or fallback.report_type,
        subject=report.subject or fallback.subject,
        from_name=report.from_name or fallback.from_name,
        headline=report.headline or fallback.headline,
        executive_summary=executive_summary,
        period=report.period or fallback.period,
        sections=report.sections or fallback.sections,
        alerts=merge_texts(report.alerts, fallback.alerts),
        actions=merge_texts(report.actions, fallback.actions),
    )


def merge_data_with_narrative(data_report: EmailReport, narrative_report: EmailReport) -> EmailReport:
    return EmailReport(
        report_type=data_report.report_type,
        subject=narrative_report.subject or data_report.subject,
        from_name=narrative_report.from_name or data_report.from_name,
        headline=narrative_report.headline or data_report.headline,
        executive_summary=narrative_report.executive_summary,
        period=narrative_report.period or data_report.period,
        sections=data_report.sections,
        alerts=merge_texts(narrative_report.alerts, data_report.alerts),
        actions=merge_texts(narrative_report.actions, data_report.actions),
    )


def merge_texts(primary: tuple[str, ...], secondary: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in (*primary, *secondary):
        key = item.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(item)
    return tuple(merged)


def merge_with_fallback(report: EmailReport, fallback: EmailReport) -> EmailReport:
    if fallback_is_authoritative(fallback):
        return authoritative_fallback_report(report, fallback)
    fallback_by_title = {normalize_title(section.title): section for section in fallback.sections}
    merged_sections: list[EmailSection] = []
    seen: set[str] = set()
    for section in report.sections:
        key = normalize_title(section.title)
        merged_sections.append(merge_section(section, fallback_by_title.get(key)))
        seen.add(key)
    for section in fallback.sections:
        key = normalize_title(section.title)
        if key not in seen:
            merged_sections.append(section)
    return EmailReport(
        report_type=preferred_report_type(report, fallback),
        subject=report.subject or fallback.subject,
        from_name=report.from_name or fallback.from_name,
        headline=report.headline or fallback.headline,
        executive_summary=report.executive_summary or fallback.executive_summary,
        period=report.period or fallback.period,
        sections=tuple(merged_sections),
        alerts=report.alerts or fallback.alerts,
        actions=report.actions or fallback.actions,
    )


def fallback_is_authoritative(fallback: EmailReport) -> bool:
    titles = {normalize_title(section.title) for section in fallback.sections}
    return len(titles.intersection(FECHAMENTO_SECTION_TITLES)) >= 3


def authoritative_fallback_report(report: EmailReport, fallback: EmailReport) -> EmailReport:
    report_by_title = {normalize_title(section.title): section for section in report.sections}
    sections: list[EmailSection] = []
    for fallback_section in fallback.sections:
        report_section = report_by_title.get(normalize_title(fallback_section.title))
        sections.append(fallback_section_with_llm_metadata(fallback_section, report_section))
    return EmailReport(
        report_type=preferred_report_type(report, fallback),
        subject=report.subject or fallback.subject,
        from_name=report.from_name or fallback.from_name,
        headline=report.headline or fallback.headline,
        executive_summary=report.executive_summary or fallback.executive_summary,
        period=report.period or fallback.period,
        sections=tuple(sections),
        alerts=fallback.alerts or report.alerts,
        actions=fallback.actions or report.actions,
    )


def preferred_report_type(report: EmailReport, fallback: EmailReport) -> str:
    if report.report_type and report.report_type != "generic":
        return report.report_type
    return fallback.report_type or report.report_type


def fallback_section_with_llm_metadata(fallback: EmailSection, report: EmailSection | None) -> EmailSection:
    if report is None:
        return fallback
    return EmailSection(
        title=fallback.title,
        kind=fallback.kind,
        total=report.total or fallback.total,
        highlight=report.highlight or fallback.highlight,
        items=fallback.items,
        tables=fallback.tables,
        notes=fallback.notes,
    )


def merge_section(section: EmailSection, fallback: EmailSection | None) -> EmailSection:
    if fallback is None:
        return EmailSection(
            title=section.title,
            kind=section.kind,
            total=section.total,
            highlight=section.highlight,
            items=section.items,
            tables=section.tables,
            notes=section.notes,
        )
    items = fallback.items if should_prefer_fallback_items(section, fallback) else section.items
    return EmailSection(
        title=section.title or fallback.title,
        kind=section.kind or fallback.kind,
        total=section.total or fallback.total,
        highlight=section.highlight or fallback.highlight,
        items=items,
        tables=section.tables or fallback.tables,
        notes=section.notes or fallback.notes,
    )


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.casefold()).strip()


def should_prefer_fallback_items(section: EmailSection, fallback: EmailSection) -> bool:
    if not fallback.items:
        return False
    if len(fallback.items) > len(section.items):
        return True
    return any(looks_like_cross_section_item(item.label) for item in section.items)


def looks_like_cross_section_item(label: str) -> bool:
    normalized = label.casefold()
    if "— total" in normalized or " - total" in normalized:
        return True
    return normalized.startswith(CROSS_SECTION_PREFIXES)
