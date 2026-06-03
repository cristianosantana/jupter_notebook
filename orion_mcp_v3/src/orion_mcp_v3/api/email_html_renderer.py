"""Renderização HTML segura para e-mails de respostas do chat."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field


@dataclass(slots=True)
class _Section:
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


def render_response_email_html(*, subject: str, body: str, from_name: str = "Orion") -> str:
    """Converte a resposta textual do chat em um HTML de relatório executivo.

    O renderizador é deliberadamente simples: preserva o texto como fonte da
    verdade e escapa todo conteúdo antes de compor o HTML.
    """
    sections = _parse_sections(body)
    escaped_subject = html.escape(subject or "Resposta Orion")
    escaped_from = html.escape(from_name or "Orion")
    section_html = "\n".join(_render_section(section) for section in sections)

    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_subject}</title>
  <style>
    body {{ margin: 0; padding: 0; background: #f4f7fb; color: #172033; font-family: Arial, Helvetica, sans-serif; }}
    .wrapper {{ width: 100%; background: #f4f7fb; padding: 28px 0; }}
    .container {{ max-width: 760px; margin: 0 auto; background: #ffffff; border-radius: 18px; overflow: hidden; border: 1px solid #e5ebf3; }}
    .header {{ padding: 28px 32px; background: #172033; color: #ffffff; }}
    .eyebrow {{ margin: 0 0 8px; font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: #aebbd0; }}
    .header h1 {{ margin: 0; font-size: 24px; line-height: 1.3; }}
    .content {{ padding: 28px 32px 34px; }}
    .section {{ margin: 0 0 22px; padding: 20px; border: 1px solid #e8edf5; border-radius: 14px; background: #ffffff; }}
    .section h2 {{ margin: 0 0 12px; font-size: 18px; color: #172033; }}
    .section h3 {{ margin: 18px 0 8px; font-size: 15px; color: #25324a; }}
    .section p {{ margin: 0 0 10px; font-size: 14px; line-height: 1.6; color: #354258; }}
    .section ul, .section ol {{ margin: 8px 0 0; padding-left: 22px; }}
    .section li {{ margin: 0 0 8px; font-size: 14px; line-height: 1.55; color: #354258; }}
    .section-overview {{ background: #f8fbff; border-color: #d8e7fb; }}
    .section-highlights {{ background: #f7fff9; border-color: #d7f0df; }}
    .section-alerts {{ background: #fff8f1; border-color: #f3dcc1; }}
    .section-actions {{ background: #f8f6ff; border-color: #ddd6fb; }}
    .section-direct-answer {{ background: #fbfcff; }}
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
        {section_html}
      </div>
      <div class="footer">E-mail gerado automaticamente pelo Orion.</div>
    </div>
  </div>
</body>
</html>"""


def _parse_sections(body: str) -> list[_Section]:
    sections: list[_Section] = []
    current: _Section | None = None
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
        current = _Section(title=title, kind=kind)
        sections.append(current)
        current_subtitle = None

    for raw_line in _normalize_body_lines(body):
        line = raw_line.strip()
        if not line:
            continue

        known = _known_section(line)
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

        item = _extract_list_item(line)
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
    return sections or [_Section(title="Resposta Orion", kind="overview", paragraphs=[body or ""])]


def _normalize_body_lines(body: str) -> list[str]:
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


def _known_section(line: str) -> tuple[str, str] | None:
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


def _extract_list_item(line: str) -> str | None:
    bullet = _BULLET_ITEM_RX.match(line)
    if bullet:
        return bullet.group("text")
    numbered = _NUMBERED_ITEM_RX.match(line)
    if numbered:
        return numbered.group("text")
    return None


def _render_section(section: _Section) -> str:
    class_name = f"section section-{section.kind}"
    parts = [f'<section class="{class_name}">', f"<h2>{html.escape(section.title)}</h2>"]
    parts.extend(f"<p>{html.escape(paragraph)}</p>" for paragraph in section.paragraphs)
    if section.items:
        parts.append(_render_items(section.items))
    for subtitle, paragraphs, items in section.subsections:
        parts.append(f"<h3>{html.escape(subtitle)}</h3>")
        parts.extend(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)
        if items:
            parts.append(_render_items(items))
    parts.append("</section>")
    return "\n".join(parts)


def _render_items(items: list[str]) -> str:
    lis = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul>{lis}</ul>"
