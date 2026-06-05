"""Renderização HTML segura para e-mails executivos."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

from orion_mcp_v3.api.email.factory import build_report_from_text
from orion_mcp_v3.api.email.models import EmailMetricItem, EmailReport, EmailSection

@dataclass(slots=True)
class _LegacySection:
    title: str
    kind: str
    paragraphs: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    subsections: list[tuple[str, list[str], list[str]]] = field(default_factory=list)


_NUMBERED_ITEM_RX = re.compile(r"^\s*\d+\.\s+(?P<text>.+?)\s*$")
_BULLET_ITEM_RX = re.compile(r"^\s*[-*]\s+(?P<text>.+?)\s*$")
_DIRECT_ANSWER_INLINE_RX = re.compile(r"(?i)(Resposta direta composta:?)\s+(.+)")
_INLINE_HEADING_RX = re.compile(r"\s+(##\s+)")
_INLINE_NUMBERED_ITEM_RX = re.compile(r"\s+(\d+\.\s+)")
_INLINE_DIRECT_ANSWER_RX = re.compile(r"\s+(Resposta direta:\s+)")


def render_response_email_html(
    *,
    subject: str,
    body: str,
    from_name: str = "Orion",
    report: EmailReport | None = None,
) -> str:
    """Converte a resposta textual do chat em HTML seguro e visualmente seccionado."""

    email_report = report or build_report_from_text(subject=subject, body=body, from_name=from_name)
    escaped_subject = html.escape(subject or email_report.subject or "Resposta Orion")
    escaped_from = html.escape(from_name or email_report.from_name or "Orion")
    if report is None and (not email_report.sections or _uses_legacy_direct_answer(body)):
        content = "\n".join(_render_legacy_section(section) for section in _parse_legacy_sections(body))
    else:
        content = _render_report(email_report, fallback_body=body)

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_subject}</title>
  <style>
    body {{ margin: 0; padding: 0; background: #eef3f9; color: #172033; font-family: Arial, Helvetica, sans-serif; }}
    .wrapper {{ width: 100%; background: #eef3f9; padding: 28px 0; }}
    .container {{ max-width: 820px; margin: 0 auto; background: #ffffff; border-radius: 20px; overflow: hidden; border: 1px solid #dfe7f2; }}
    .header {{ padding: 30px 34px; background: #172033; color: #ffffff; }}
    .eyebrow {{ margin: 0 0 8px; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: #aebbd0; }}
    .header h1 {{ margin: 0; font-size: 25px; line-height: 1.3; }}
    .content {{ padding: 28px 32px 34px; }}
    .hero-card {{ margin: 0 0 22px; padding: 22px; border-radius: 16px; background: #f7fbff; border: 1px solid #d8e7fb; }}
    .hero-card p {{ margin: 0; color: #354258; font-size: 14px; line-height: 1.6; }}
    .hero-headline {{ display: block; margin: 4px 0 6px; color: #172033; font-size: 20px; line-height: 1.35; }}
    .executive-summary-card {{ margin: 0 0 22px; padding: 18px 20px; border-radius: 16px; background: #fffdf5; border: 1px solid #efe3bd; }}
    .executive-summary-card h2 {{ margin: 0 0 10px; color: #172033; font-size: 17px; }}
    .executive-summary-card p {{ margin: 0; color: #354258; font-size: 14px; line-height: 1.6; }}
    .report-section {{ margin: 0 0 18px; padding: 20px; border: 1px solid #e3eaf4; border-radius: 16px; background: #ffffff; }}
    .section-header {{ margin-bottom: 14px; }}
    .section-kicker {{ display: block; margin-bottom: 6px; color: #6b768a; font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }}
    .report-section h2 {{ margin: 0; color: #172033; font-size: 18px; line-height: 1.3; }}
    .section-total {{ display: inline-block; margin-top: 10px; padding: 8px 12px; border-radius: 999px; background: #eef6ff; color: #183b66; font-size: 14px; font-weight: 700; }}
    .highlight-card {{ margin: 12px 0; padding: 12px 14px; border-radius: 12px; background: #f7fff9; border: 1px solid #d7f0df; color: #25324a; font-size: 14px; line-height: 1.5; }}
    .badge {{ display: inline-block; margin-right: 8px; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; }}
    .badge-highlight {{ background: #dff7e7; color: #1d6a3a; }}
    .badge-note {{ background: #eef2fb; color: #40516f; }}
    .metric-list {{ list-style: none; margin: 12px 0 0; padding: 0; }}
    .metric-row {{ display: table; width: 100%; border-top: 1px solid #eef2f7; padding: 9px 0; color: #354258; font-size: 14px; }}
    .metric-label {{ display: table-cell; font-weight: 700; color: #25324a; }}
    .metric-value {{ display: table-cell; text-align: right; white-space: nowrap; color: #172033; }}
    .metric-detail {{ display: table-cell; text-align: right; width: 82px; color: #6b768a; }}
    .note-list {{ margin: 12px 0 0; padding-left: 0; list-style: none; }}
    .note-list li {{ margin: 0 0 8px; color: #526078; font-size: 13px; line-height: 1.45; }}
    .alert-card {{ margin: 18px 0; padding: 16px; border-radius: 14px; background: #fff8f1; border: 1px solid #f3dcc1; color: #5a3515; }}
    .action-card {{ margin: 18px 0 0; padding: 16px; border-radius: 14px; background: #f8f6ff; border: 1px solid #ddd6fb; color: #31245f; }}
    .alert-card h2, .action-card h2 {{ margin: 0 0 10px; font-size: 16px; }}
    .alert-card ul, .action-card ul {{ margin: 0; padding-left: 20px; }}
    .alert-card li, .action-card li {{ margin: 0 0 8px; font-size: 14px; line-height: 1.5; }}
    .footer {{ padding: 18px 32px 28px; font-size: 12px; color: #6b768a; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="container">
      <div class="header">
        <p class="eyebrow">{escaped_from}</p>
        <h1>{escaped_subject}</h1>
      </div>
      <div class="content">
        {content}
      </div>
      <div class="footer">E-mail gerado automaticamente pelo Orion.</div>
    </div>
  </div>
</body>
</html>"""


def _render_report(report: EmailReport, *, fallback_body: str) -> str:
    if report.report_type == "ranking":
        return _render_typed_report(report, fallback_body=fallback_body)
    if report.report_type == "comparacao":
        return _render_typed_report(report, fallback_body=fallback_body)
    if report.report_type == "analise_unica":
        return _render_typed_report(report, fallback_body=fallback_body)
    if report.report_type == "conversacional":
        return _render_typed_report(report, fallback_body=fallback_body)
    return _render_typed_report(report, fallback_body=fallback_body)


def _render_typed_report(report: EmailReport, *, fallback_body: str) -> str:
    parts: list[str] = []
    if report.headline or report.period:
        parts.append(_render_hero(report))
    if report.executive_summary:
        parts.append(_render_executive_summary(report.executive_summary))
    for section in report.sections:
        parts.append(_render_section(section))
    if report.alerts:
        parts.append(_render_message_card("Alertas e conciliações", report.alerts, "alert-card"))
    if report.actions:
        parts.append(_render_message_card("Conclusão acionável", report.actions, "action-card"))
    if not parts:
        parts.append(_render_fallback(fallback_body))
    return "\n".join(parts)


def _render_hero(report: EmailReport) -> str:
    lines = ['<section class="hero-card">']
    if report.period:
        lines.append(f"<p>Período: <strong>{html.escape(report.period)}</strong></p>")
    if report.headline:
        lines.append(f'<strong class="hero-headline">{html.escape(report.headline)}</strong>')
    lines.append("</section>")
    return "\n".join(lines)


def _render_executive_summary(summary: str) -> str:
    return (
        '<section class="executive-summary-card">'
        "<h2>Resumo executivo</h2>"
        f"<p>{html.escape(summary)}</p>"
        "</section>"
    )


def _render_section(section: EmailSection) -> str:
    parts = [f'<section class="report-section section-{html.escape(section.kind)}">']
    parts.append('<div class="section-header">')
    parts.append(f'<span class="section-kicker">{html.escape(_section_kicker(section.kind))}</span>')
    parts.append(f"<h2>{html.escape(section.title)}</h2>")
    if section.total:
        parts.append(f'<span class="section-total">Total: {html.escape(section.total)}</span>')
    parts.append("</div>")
    if section.highlight:
        parts.append(
            '<div class="highlight-card">'
            '<span class="badge badge-highlight">Destaque</span>'
            f"{_format_inline_metric(section.highlight)}"
            "</div>"
        )
    if section.items:
        parts.append(_render_metric_list(section.items))
    if section.notes:
        parts.append(_render_notes(section.notes))
    parts.append("</section>")
    return "\n".join(parts)


def _render_metric_list(items: tuple[EmailMetricItem, ...]) -> str:
    rows = ['<ul class="metric-list">']
    for item in items:
        rows.append(
            '<li class="metric-row">'
            f'<span class="metric-label">{html.escape(item.label)}</span>'
            f'<span class="metric-value">{html.escape(item.value or "")}</span>'
            f'<span class="metric-detail">{html.escape(item.detail or "")}</span>'
            "</li>"
        )
    rows.append("</ul>")
    return "\n".join(rows)


def _render_notes(notes: tuple[str, ...]) -> str:
    rows = ['<ul class="note-list">']
    for note in notes:
        rows.append(f'<li><span class="badge badge-note">Nota</span>{html.escape(note)}</li>')
    rows.append("</ul>")
    return "\n".join(rows)


def _render_message_card(title: str, items: tuple[str, ...], class_name: str) -> str:
    lis = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f'<section class="{class_name}"><h2>{html.escape(title)}</h2><ul>{lis}</ul></section>'


def _render_fallback(body: str) -> str:
    paragraphs = "\n".join(f"<p>{html.escape(line)}</p>" for line in (body or "").splitlines() if line.strip())
    return f'<section class="report-section section-default"><h2>Resumo</h2>{paragraphs}</section>'


def _format_inline_metric(text: str) -> str:
    label, sep, rest = text.partition("—")
    if not sep:
        label, sep, rest = text.partition(":")
    if not sep:
        return html.escape(text)
    return f"<strong>{html.escape(label.strip())}</strong> {html.escape(sep)} {html.escape(rest.strip())}"


def _section_kicker(kind: str) -> str:
    return {
        "payment": "Financeiro",
        "revenue": "Faturamento",
        "commission": "Comissões",
        "production": "Produção",
        "fees": "Taxas",
        "ranking": "Ranking",
        "comparison": "Comparação",
        "single-analysis": "Análise",
        "conversational": "Mensagem",
    }.get(kind, "Relatório")


def _uses_legacy_direct_answer(body: str) -> bool:
    return "Resposta direta composta" in (body or "")


def _parse_legacy_sections(body: str) -> list[_LegacySection]:
    sections: list[_LegacySection] = []
    current: _LegacySection | None = None
    current_subtitle: str | None = None
    current_sub_paragraphs: list[str] = []
    current_sub_items: list[str] = []

    def flush_subsection() -> None:
        nonlocal current_subtitle, current_sub_paragraphs, current_sub_items
        if current is not None and current_subtitle is not None:
            current.subsections.append((current_subtitle, current_sub_paragraphs, current_sub_items))
        current_subtitle = None
        current_sub_paragraphs = []
        current_sub_items = []

    def start_section(title: str, kind: str) -> None:
        nonlocal current, current_subtitle
        flush_subsection()
        current = _LegacySection(title=title, kind=kind)
        sections.append(current)
        current_subtitle = None

    for raw_line in _normalize_legacy_body_lines(body):
        line = raw_line.strip()
        if not line:
            continue
        known = _legacy_known_section(line)
        if known is not None:
            title, kind = known
            start_section(title, kind)
            continue
        if line.startswith("## "):
            if current is None or current.kind != "direct-answer":
                start_section("Resposta direta composta", "direct-answer")
            flush_subsection()
            current_subtitle = line[3:].strip()
            continue
        if current is None:
            start_section("Resumo", "overview")
        item = _extract_legacy_list_item(line)
        if current_subtitle is not None:
            if item is not None:
                current_sub_items.append(item)
            else:
                current_sub_paragraphs.append(line)
        elif item is not None:
            current.items.append(item)
        else:
            current.paragraphs.append(line)

    flush_subsection()
    return sections or [_LegacySection(title="Resposta Orion", kind="overview", paragraphs=[body or ""])]


def _normalize_legacy_body_lines(body: str) -> list[str]:
    lines: list[str] = []
    for raw_line in (body or "").splitlines():
        line = raw_line.strip()
        if not line:
            lines.append(line)
            continue
        direct = _DIRECT_ANSWER_INLINE_RX.fullmatch(line)
        if direct:
            lines.append(direct.group(1))
            line = direct.group(2)
        line = _INLINE_HEADING_RX.sub(r"\n\1", line)
        line = _INLINE_DIRECT_ANSWER_RX.sub(r"\n\1", line)
        line = _INLINE_NUMBERED_ITEM_RX.sub(r"\n\1", line)
        lines.extend(line.splitlines())
    return lines


def _legacy_known_section(line: str) -> tuple[str, str] | None:
    normalized = line.rstrip(":").casefold()
    if normalized.startswith("visão geral"):
        return line, "overview"
    if normalized == "destaques":
        return line, "highlights"
    if normalized == "alertas":
        return line, "alerts"
    if normalized == "conclusão acionável":
        return line, "actions"
    if normalized.startswith("resposta direta composta"):
        return "Resposta direta composta", "direct-answer"
    return None


def _extract_legacy_list_item(line: str) -> str | None:
    bullet = _BULLET_ITEM_RX.match(line)
    if bullet:
        return bullet.group("text")
    numbered = _NUMBERED_ITEM_RX.match(line)
    if numbered:
        return numbered.group("text")
    return None


def _render_legacy_section(section: _LegacySection) -> str:
    class_name = f"section section-{section.kind}"
    parts = [f'<section class="{class_name}">', f"<h2>{html.escape(section.title)}</h2>"]
    parts.extend(f"<p>{html.escape(paragraph)}</p>" for paragraph in section.paragraphs)
    if section.items:
        parts.append(_render_legacy_items(section.items))
    for subtitle, paragraphs, items in section.subsections:
        parts.append(f"<h3>{html.escape(subtitle)}</h3>")
        parts.extend(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)
        if items:
            parts.append(_render_legacy_items(items))
    parts.append("</section>")
    return "\n".join(parts)


def _render_legacy_items(items: list[str]) -> str:
    lis = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul>{lis}</ul>"
