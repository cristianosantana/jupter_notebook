"""Configuração declarativa e política de exibição para parsing de e-mail (Fase 1)."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from orion_mcp_v3.api.email.models import EmailReport, EmailSection

if TYPE_CHECKING:
    from orion_mcp_v3.config.settings import OrionSettings

EmailParsingProfile = Literal["default", "minimal", "executive"]

_SECTION_DIRECT_ANSWER = "resposta direta"
_SECTION_COMPLEMENTARY = "resumo estatistico complementar"
_SECTION_HIGHLIGHTS = "destaques"
_SECTION_RANKING = "ranking"


@dataclass(frozen=True, slots=True)
class EmailParsingConfig:
    """Política de exibição aplicada após o parse determinístico."""

    include_complementary: bool = True
    include_highlights: bool = True
    include_ranking_items: bool = True
    include_alerts: bool = True
    include_actions: bool = True
    expand_inline_numbered: bool = True

    @classmethod
    def default(cls) -> EmailParsingConfig:
        return cls()

    @classmethod
    def minimal(cls) -> EmailParsingConfig:
        """Apenas resposta direta — sem complementar, destaques, ranking, alertas ou ações."""
        return cls(
            include_complementary=False,
            include_highlights=False,
            include_ranking_items=False,
            include_alerts=False,
            include_actions=False,
        )

    @classmethod
    def executive(cls) -> EmailParsingConfig:
        """Visão executiva — sem bloco complementar, mantém destaques e ranking."""
        return cls(
            include_complementary=False,
            include_highlights=True,
            include_ranking_items=True,
            include_alerts=True,
            include_actions=True,
        )


def get_parsing_config(settings: OrionSettings | None = None) -> EmailParsingConfig:
    """Resolve perfil de parsing a partir de settings ou retorna default."""
    if settings is None:
        return EmailParsingConfig.default()
    profile = getattr(settings, "email_parsing_profile", "default")
    if profile == "minimal":
        return EmailParsingConfig.minimal()
    if profile == "executive":
        return EmailParsingConfig.executive()
    return EmailParsingConfig.default()


def apply_parsing_policy(report: EmailReport, config: EmailParsingConfig) -> EmailReport:
    """Filtra seções, itens, alertas e ações conforme a política configurada."""
    sections = _filter_sections(report.sections, config)
    alerts = report.alerts if config.include_alerts else ()
    actions = report.actions if config.include_actions else ()
    return EmailReport(
        report_type=report.report_type,
        subject=report.subject,
        from_name=report.from_name,
        headline=report.headline,
        executive_summary=report.executive_summary,
        period=report.period,
        sections=sections,
        alerts=alerts,
        actions=actions,
    )


def _filter_sections(
    sections: tuple[EmailSection, ...],
    config: EmailParsingConfig,
) -> tuple[EmailSection, ...]:
    minimal = _is_minimal_profile(config)
    filtered: list[EmailSection] = []
    for section in sections:
        normalized_title = _normalize_title(section.title)
        if minimal and normalized_title != _SECTION_DIRECT_ANSWER:
            continue
        if not config.include_complementary and _is_complementary_section(normalized_title):
            continue
        if not config.include_highlights and normalized_title == _SECTION_HIGHLIGHTS:
            continue
        if not config.include_ranking_items and _is_ranking_section(normalized_title, section.kind):
            continue
        if not config.include_ranking_items:
            section = _strip_ranking_items(section)
        filtered.append(section)
    return tuple(filtered)


def _is_minimal_profile(config: EmailParsingConfig) -> bool:
    return (
        not config.include_complementary
        and not config.include_highlights
        and not config.include_ranking_items
        and not config.include_alerts
        and not config.include_actions
    )


def _is_complementary_section(normalized_title: str) -> bool:
    return normalized_title.startswith(_SECTION_COMPLEMENTARY)


def _is_ranking_section(normalized_title: str, kind: str) -> bool:
    if normalized_title == _SECTION_RANKING:
        return True
    return kind == "ranking" and normalized_title != _SECTION_DIRECT_ANSWER


def _normalize_title(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold())
    return folded.encode("ascii", "ignore").decode("ascii")


def _strip_ranking_items(section: EmailSection) -> EmailSection:
    return EmailSection(
        title=section.title,
        kind=section.kind,
        total=section.total,
        highlight=section.highlight,
        items=(),
        tables=section.tables,
        notes=section.notes,
    )
