"""Parsing determinístico de evidência estruturada e narrativa em relatórios de e-mail."""

from __future__ import annotations

import re
import unicodedata

from orion_mcp_v3.api.email.models import EmailMetricItem, EmailReport, EmailSection, EmailTable
from orion_mcp_v3.api.email.parsing_config import EmailParsingConfig, apply_parsing_policy

_SECTION_TOTAL_RX = re.compile(r"^(?P<title>.+?)\s+—\s+Total(?:\s*\(.+?\))?:\s*(?P<total>R\$\s*[\d.,]+)", re.I)
_HEADLINE_RX = re.compile(r"^direct_answer_set\.headline:\s*(?P<headline>.+)$", re.I)
_HIGHLIGHT_RX = re.compile(r"^Destaque:\s*(?P<highlight>.+)$", re.I)
_DIRECT_ANSWER_RX = re.compile(r"^Resposta direta:\s*(?P<detail>.*)$", re.I)
_NOTE_RX = re.compile(r"^(Detalhe|Top\s+\d+|Observação)\b(?P<note>.*)$", re.I)
_PERIOD_RX = re.compile(r"(\d{4}-\d{2}-\d{2}\s+a\s+\d{4}-\d{2}-\d{2})")
_HEADING_RX = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_NUMBERED_RX = re.compile(r"^\d+\.\s+(?P<text>.+?)\s*$")
_SYNTHESIS_HEADING_RX = re.compile(r"\b(s[ií]ntese|resumo executivo)\b", re.I)
_COMPLEMENTARY_SECTION_RX = re.compile(r"^Resumo estatístico complementar\b", re.I)
_RANKING_HEADER_RX = re.compile(r"^Ranking por\b", re.I)
_DESTAQUES_SECTION_RX = re.compile(r"^Destaques?\s*:?\s*$", re.I)
_DOMINANTE_RX = re.compile(r"^Dominante:\s*(?P<text>.+)$", re.I)
_CONCENTRACAO_RX = re.compile(r"^Concentra[cç][aã]o:\s*(?P<text>.+)$", re.I)
_OMITTED_CATEGORIES_RX = re.compile(r"^\.\.\.\s*\(\+\s*\d+", re.I)
_INLINE_VALUE_RX = re.compile(r"^(?P<label>.+?)\s+(?P<value>R\$\s*[\d.,]+)(?:\s*(?P<detail>\([^)]*\)))?\.?$")
_INLINE_NUMBERED_ITEM_RX = re.compile(r"\s+(\d+\.\s+)")
_INLINE_COMPLEMENTARY_RX = re.compile(r"\s+(Resumo estatístico complementar\b)", re.I)


def normalize(text: str) -> str:
    """Casefold + remoção de acentos para comparações estáveis."""
    folded = unicodedata.normalize("NFKD", text.casefold())
    return folded.encode("ascii", "ignore").decode("ascii")


class SectionDraft:
    def __init__(self, *, title: str, kind: str, total: str | None = None) -> None:
        self.title = title
        self.kind = kind
        self.total = total
        self.highlight: str | None = None
        self.items: list[EmailMetricItem] = []
        self.table_headers: tuple[str, ...] = ()
        self.table_rows: list[tuple[str, ...]] = []
        self.notes: list[str] = []

    def add_table_line(self, line: str) -> None:
        cells = tuple(cell.strip() for cell in line.split("|"))
        if len(cells) < 2 or not any(cells):
            return
        if not self.table_headers:
            self.table_headers = cells
            return
        if len(cells) == len(self.table_headers):
            self.table_rows.append(cells)

    def to_section(self) -> EmailSection:
        tables = ()
        if self.table_headers and self.table_rows:
            tables = (EmailTable(headers=self.table_headers, rows=tuple(self.table_rows)),)
        return EmailSection(
            title=self.title,
            kind=self.kind,
            total=self.total,
            highlight=self.highlight,
            items=tuple(self.items),
            tables=tables,
            notes=tuple(self.notes),
        )


def build_report_from_text(
    *,
    subject: str,
    body: str,
    from_name: str = "Orion",
    report_type: str = "generic",
    config: EmailParsingConfig | None = None,
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

    for raw_line in normalized_lines(body):
        raw = strip_numbered_prefix(raw_line)
        headline_match = _HEADLINE_RX.match(raw)
        if headline_match:
            headline = headline_match.group("headline").strip()
            period = extract_period(headline) or period
            continue

        direct_answer_match = _DIRECT_ANSWER_RX.match(raw)
        if direct_answer_match:
            flush()
            collection_mode = None
            current = SectionDraft(title="Resposta direta", kind="ranking")
            detail = direct_answer_match.group("detail").strip()
            if detail:
                current.notes.append(detail)
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

        if _COMPLEMENTARY_SECTION_RX.match(raw):
            flush()
            collection_mode = None
            current = SectionDraft(title="Resumo estatístico complementar", kind="ranking")
            continue

        if _DESTAQUES_SECTION_RX.match(raw):
            flush()
            collection_mode = None
            current = SectionDraft(title="Destaques", kind="default")
            continue

        if _RANKING_HEADER_RX.match(raw):
            if current is None:
                current = SectionDraft(title="Ranking", kind="ranking")
            current.notes.append(raw)
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

        if raw.casefold().startswith(("template:", "linhas disponíveis:", "linhas disponiveis:")):
            continue

        total_match = _SECTION_TOTAL_RX.match(raw)
        if total_match:
            flush()
            collection_mode = None
            current = SectionDraft(
                title=total_match.group("title").strip(),
                kind=section_kind(total_match.group("title")),
                total=total_match.group("total").strip(),
            )
            continue

        highlight_match = _HIGHLIGHT_RX.match(raw)
        if highlight_match:
            if current is None or current.title == "Resposta direta":
                flush()
                current = SectionDraft(title="Destaques", kind="default")
            current.highlight = highlight_match.group("highlight").strip()
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
    if config is not None:
        return apply_parsing_policy(report, config)
    return report


def narrative_report_from_text(*, subject: str, body: str, from_name: str) -> EmailReport:
    lines = normalized_lines(body)
    summary_lines: list[str] = []
    explicit_synthesis_lines: list[str] = []
    alerts: list[str] = []
    actions: list[str] = []
    mode: str | None = None
    for line in lines:
        normalized = line.casefold()
        extracted_summary = extract_inline_synthesis(line)
        if extracted_summary:
            explicit_synthesis_lines = [extracted_summary]
            mode = None
            continue
        if is_synthesis_heading(line):
            mode = "synthesis"
            continue
        if "alerta" in normalized or "atenção" in normalized or "atencao" in normalized:
            mode = "alerts"
        elif "conclus" in normalized or "recomenda" in normalized or is_action(line):
            mode = "actions"
        if mode == "synthesis":
            explicit_synthesis_lines.append(line)
            if len(explicit_synthesis_lines) >= 3:
                mode = None
        elif mode == "alerts":
            alerts.append(line)
        elif mode == "actions":
            actions.append(line)
        elif len(summary_lines) < 3:
            summary_lines.append(line)
    executive_summary = " ".join(explicit_synthesis_lines) or (" ".join(summary_lines) or None)
    return EmailReport(
        subject=subject,
        from_name=from_name,
        headline=summary_lines[0] if summary_lines else None,
        executive_summary=executive_summary,
        alerts=tuple(alerts),
        actions=tuple(actions),
    )


def has_explicit_synthesis(body: str) -> bool:
    return any(is_synthesis_heading(line) for line in normalized_lines(body))


def is_synthesis_heading(line: str) -> bool:
    return bool(_SYNTHESIS_HEADING_RX.search(line))


def extract_inline_synthesis(line: str) -> str | None:
    for separator in (":", " — "):
        before, sep, after = line.partition(separator)
        if sep and after.strip() and is_synthesis_heading(before):
            return after.strip()
    return None


def expand_compacted_evidence(body: str) -> str:
    """Quebra blocos inline comuns na evidência analítica em linhas separadas."""
    expanded: list[str] = []
    for raw_line in (body or "").splitlines():
        line = raw_line.strip()
        if not line:
            expanded.append("")
            continue
        line = _INLINE_COMPLEMENTARY_RX.sub(r"\n\1", line)
        line = _INLINE_NUMBERED_ITEM_RX.sub(r"\n\1", line)
        expanded.extend(line.splitlines())
    return "\n".join(expanded)


def normalized_lines(body: str) -> list[str]:
    lines: list[str] = []
    for raw in expand_compacted_evidence(body).splitlines():
        line = raw.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if line:
            lines.append(line)
    return lines


def strip_numbered_prefix(line: str) -> str:
    match = _NUMBERED_RX.match(line)
    return match.group("text").strip() if match else line


def section_kind(title: str) -> str:
    normalized = normalize(title)
    if "pagamento" in normalized or "parcelamento" in normalized:
        return "payment"
    if "comiss" in normalized or "concession" in normalized:
        return "commission"
    if "producao" in normalized:
        return "production"
    if "taxas" in normalized:
        return "fees"
    if "faturamento" in normalized:
        return "revenue"
    return "default"


def parse_metric_item(line: str) -> EmailMetricItem:
    return EmailMetricItem.from_text(line)


def looks_like_metric(line: str) -> bool:
    stripped = line.strip()
    if (":" in stripped or "—" in stripped) and "R$" in stripped:
        return True
    return bool(_INLINE_VALUE_RX.match(stripped))


def looks_like_pipe_table_line(line: str) -> bool:
    return "|" in line and len([cell for cell in line.split("|") if cell.strip()]) >= 2


def inline_detail_items(line: str) -> list[EmailMetricItem]:
    prefix, separator, rest = line.partition(":")
    if not separator or "R$" not in rest:
        return []
    items: list[EmailMetricItem] = []
    for chunk in rest.split(";"):
        item = chunk.strip()
        if item.endswith("."):
            item = item[:-1].rstrip()
        if looks_like_metric(item):
            items.append(EmailMetricItem.from_text(item))
    return items


def is_alert(line: str) -> bool:
    normalized = line.casefold()
    return normalized.startswith(("registros com valor zero", "discrepância", "discrepancia"))


def is_action(line: str) -> bool:
    normalized = line.casefold()
    return normalized.startswith(("priorizar", "negociar", "corrigir", "conciliar", "revisar"))


def extract_period(text: str) -> str | None:
    match = _PERIOD_RX.search(text)
    return match.group(1) if match else None


def first_meaningful_line(body: str) -> str | None:
    for line in normalized_lines(body):
        if line:
            return line
    return None
