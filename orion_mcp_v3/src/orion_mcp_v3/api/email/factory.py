"""Factory que transforma texto narrativo em relatório de e-mail estruturado."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from orion_mcp_v3.api.email.classifier import EmailMessageType, classify_message
from orion_mcp_v3.api.email.models import EmailMetricItem, EmailReport, EmailSection, EmailTable
from orion_mcp_v3.prompts import get_prompt_registry
from orion_mcp_v3.protocols.llm import ChatMessage, LLMProvider, NullLLMProvider

_LOG = logging.getLogger("orion.api.email")

_SECTION_TOTAL_RX = re.compile(r"^(?P<title>.+?)\s+—\s+Total(?:\s*\(.+?\))?:\s*(?P<total>R\$\s*[\d.,]+)", re.I)
_HEADLINE_RX = re.compile(r"^direct_answer_set\.headline:\s*(?P<headline>.+)$", re.I)
_HIGHLIGHT_RX = re.compile(r"^Destaque:\s*(?P<highlight>.+)$", re.I)
_NOTE_RX = re.compile(r"^(Detalhe|Top\s+\d+|Observação)\b(?P<note>.*)$", re.I)
_PERIOD_RX = re.compile(r"(\d{4}-\d{2}-\d{2}\s+a\s+\d{4}-\d{2}-\d{2})")
_HEADING_RX = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_NUMBERED_RX = re.compile(r"^\d+\.\s+(?P<text>.+?)\s*$")
_SYNTHESIS_HEADING_RX = re.compile(r"\b(s[ií]ntese|resumo executivo)\b", re.I)
_SCHEMA_BY_TYPE: dict[str, dict[str, Any]] = {
    "fechamento_gerencial": {
        "type": "fechamento_gerencial",
        "period": "string|null",
        "headline_value": "string|null",
        "headline_label": "string|null",
        "sections": [
            {
                "title": "string",
                "category": "payment|revenue|commission|production|fees|default",
                "total": "string|null",
                "highlight_label": "string|null",
                "highlight_value": "string|null",
                "highlight_pct": "string|null",
                "items": [{"label": "string", "value": "string|null", "pct": "string|null"}],
                "notes": ["string"],
                "risks": ["string"],
            }
        ],
        "alerts": ["string"],
        "actions": ["string"],
    },
    "ranking": {
        "type": "ranking",
        "period": "string|null",
        "metric": "string|null",
        "dimension": "string|null",
        "headline_value": "string|null",
        "items": [{"rank": "number|null", "label": "string", "value": "string|null", "pct": "string|null"}],
        "notes": ["string"],
    },
    "comparacao": {
        "type": "comparacao",
        "period": "string|null",
        "headline_label": "string|null",
        "headline_value": "string|null",
        "comparisons": [{"label": "string", "value": "string|null", "detail": "string|null"}],
        "alerts": ["string"],
        "actions": ["string"],
    },
    "analise_unica": {
        "type": "analise_unica",
        "period": "string|null",
        "headline_label": "string|null",
        "headline_value": "string|null",
        "items": [{"label": "string", "value": "string|null", "detail": "string|null"}],
        "notes": ["string"],
        "actions": ["string"],
    },
    "conversacional": {
        "type": "conversacional",
        "message": "string",
    },
}
_NARRATIVE_SCHEMA: dict[str, Any] = {
    "headline": "string|null",
    "executive_summary": "string|null, prefer the explicit 'Síntese curta de composição' when present",
    "alerts": ["strings explicitly mentioned as alerts or attention points"],
    "actions": ["strings explicitly mentioned as concrete recommendations"],
}


class EmailMessageFactory:
    """Monta um `EmailReport` validado a partir do texto da resposta."""

    def __init__(self, provider: LLMProvider | None = None, *, max_tokens: int = 1200) -> None:
        self._provider = provider or NullLLMProvider()
        self._max_tokens = max_tokens

    async def build_report(
        self,
        *,
        subject: str,
        body: str,
        from_name: str = "Orion",
        structured_evidence: str | None = None,
    ) -> EmailReport:
        source = structured_evidence or body
        message_type = classify_message(source)
        if structured_evidence:
            data_report = build_report_from_text(
                subject=subject,
                body=structured_evidence,
                from_name=from_name,
                report_type=message_type,
            )
            narrative_report = await self._try_narrative_report(subject=subject, body=body, from_name=from_name)
            narrative_fallback = _narrative_report_from_text(subject=subject, body=body, from_name=from_name)
            if narrative_report is None:
                narrative_report = narrative_fallback
            else:
                narrative_report = _merge_narrative_reports(
                    narrative_report,
                    narrative_fallback,
                    prefer_fallback_summary=_has_explicit_synthesis(body),
                )
            return _merge_data_with_narrative(data_report, narrative_report)
        if message_type == "conversacional":
            return _simple_report(subject=subject, body=body, from_name=from_name, report_type=message_type)
        fallback = build_report_from_text(subject=subject, body=source, from_name=from_name, report_type=message_type)
        if not isinstance(self._provider, NullLLMProvider):
            report = await self._try_llm_report(subject=subject, body=source, from_name=from_name, message_type=message_type)
            if report is not None and (report.sections or report.alerts or report.actions or report.headline):
                return _merge_with_fallback(report.with_defaults(subject=subject, from_name=from_name), fallback)
        return fallback

    async def _try_llm_report(
        self,
        *,
        subject: str,
        body: str,
        from_name: str,
        message_type: EmailMessageType,
    ) -> EmailReport | None:
        prompt = _build_prompt(subject=subject, body=body, from_name=from_name, message_type=message_type)
        try:
            response = await self._provider.chat(
                [
                    ChatMessage(role="system", content=_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=prompt),
                ],
                max_tokens=self._max_tokens,
                temperature=0,
            )
        except Exception:
            _LOG.exception("email message factory provider failed")
            return None
        payload = _parse_json_object(response.text)
        if payload is None:
            return None
        return EmailReport.from_mapping(payload)

    async def _try_narrative_report(self, *, subject: str, body: str, from_name: str) -> EmailReport | None:
        if isinstance(self._provider, NullLLMProvider):
            return None
        prompt = _build_narrative_prompt(subject=subject, body=body, from_name=from_name)
        try:
            response = await self._provider.chat(
                [
                    ChatMessage(role="system", content=_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=prompt),
                ],
                max_tokens=self._max_tokens,
                temperature=0,
            )
        except Exception:
            _LOG.exception("email narrative extractor provider failed")
            return None
        payload = _parse_json_object(response.text)
        if payload is None:
            return None
        return EmailReport.from_mapping(payload)


def build_report_from_text(
    *,
    subject: str,
    body: str,
    from_name: str = "Orion",
    report_type: str = "generic",
) -> EmailReport:
    headline: str | None = None
    period: str | None = None
    sections: list[EmailSection] = []
    alerts: list[str] = []
    actions: list[str] = []
    current: _SectionDraft | None = None
    collection_mode: str | None = None

    def flush() -> None:
        nonlocal current
        if current is not None:
            sections.append(current.to_section())
        current = None

    for raw_line in _normalized_lines(body):
        raw = _strip_numbered_prefix(raw_line)
        headline_match = _HEADLINE_RX.match(raw)
        if headline_match:
            headline = headline_match.group("headline").strip()
            period = _extract_period(headline) or period
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
            current = _SectionDraft(title=title, kind=_section_kind(title))
            continue

        if raw.casefold().startswith(("template:", "linhas disponíveis:", "linhas disponiveis:")):
            continue

        total_match = _SECTION_TOTAL_RX.match(raw)
        if total_match:
            flush()
            collection_mode = None
            current = _SectionDraft(
                title=total_match.group("title").strip(),
                kind=_section_kind(total_match.group("title")),
                total=total_match.group("total").strip(),
            )
            continue

        highlight_match = _HIGHLIGHT_RX.match(raw)
        if highlight_match and current is not None:
            current.highlight = highlight_match.group("highlight").strip()
            continue

        note_match = _NOTE_RX.match(raw)
        if note_match and current is not None:
            inline_items = _inline_detail_items(raw)
            if inline_items:
                current.items.extend(inline_items)
                current.notes.append(raw.split(":", 1)[0].strip() + ":")
            else:
                current.notes.append(raw)
            continue

        if _is_alert(raw):
            flush()
            collection_mode = "alerts"
            alerts.append(raw)
            continue

        if _is_action(raw):
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

        if current is not None and _looks_like_metric(raw):
            current.items.append(EmailMetricItem.from_text(raw))
            continue

        if current is not None and _looks_like_pipe_table_line(raw):
            current.add_table_line(raw)

    flush()
    if headline is None:
        headline = _first_meaningful_line(body)
    return EmailReport(
        report_type=report_type,
        subject=subject,
        from_name=from_name,
        headline=headline,
        period=period,
        sections=tuple(sections),
        alerts=tuple(alerts),
        actions=tuple(actions),
    )


class _SectionDraft:
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


def _build_prompt(*, subject: str, body: str, from_name: str, message_type: EmailMessageType) -> str:
    payload = {
        "subject": subject,
        "from_name": from_name,
        "message_type": message_type,
        "body": body,
        "required_json_shape": _SCHEMA_BY_TYPE[message_type],
    }
    return json.dumps(payload, ensure_ascii=False)


def _build_narrative_prompt(*, subject: str, body: str, from_name: str) -> str:
    payload = {
        "subject": subject,
        "from_name": from_name,
        "body": body,
        "required_json_shape": _NARRATIVE_SCHEMA,
    }
    return json.dumps(payload, ensure_ascii=False)


def _simple_report(*, subject: str, body: str, from_name: str, report_type: str) -> EmailReport:
    text = _first_meaningful_line(body) or body or ""
    return EmailReport(
        report_type=report_type,
        subject=subject,
        from_name=from_name,
        headline=subject or None,
        sections=(
            EmailSection(
                title="Mensagem",
                kind="conversational",
                items=(EmailMetricItem(label=text),) if text else (),
            ),
        ),
    )


def _narrative_report_from_text(*, subject: str, body: str, from_name: str) -> EmailReport:
    lines = _normalized_lines(body)
    summary_lines: list[str] = []
    explicit_synthesis_lines: list[str] = []
    alerts: list[str] = []
    actions: list[str] = []
    mode: str | None = None
    for line in lines:
        normalized = line.casefold()
        extracted_summary = _extract_inline_synthesis(line)
        if extracted_summary:
            explicit_synthesis_lines = [extracted_summary]
            mode = None
            continue
        if _is_synthesis_heading(line):
            mode = "synthesis"
            continue
        if "alerta" in normalized or "atenção" in normalized or "atencao" in normalized:
            mode = "alerts"
        elif "conclus" in normalized or "recomenda" in normalized or _is_action(line):
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


def _has_explicit_synthesis(body: str) -> bool:
    return any(_is_synthesis_heading(line) for line in _normalized_lines(body))


def _is_synthesis_heading(line: str) -> bool:
    return bool(_SYNTHESIS_HEADING_RX.search(line))


def _extract_inline_synthesis(line: str) -> str | None:
    for separator in (":", " — "):
        before, sep, after = line.partition(separator)
        if sep and after.strip() and _is_synthesis_heading(before):
            return after.strip()
    return None


def _merge_narrative_reports(
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
        alerts=_merge_texts(report.alerts, fallback.alerts),
        actions=_merge_texts(report.actions, fallback.actions),
    )


def _merge_data_with_narrative(data_report: EmailReport, narrative_report: EmailReport) -> EmailReport:
    return EmailReport(
        report_type=data_report.report_type,
        subject=narrative_report.subject or data_report.subject,
        from_name=narrative_report.from_name or data_report.from_name,
        headline=narrative_report.headline or data_report.headline,
        executive_summary=narrative_report.executive_summary,
        period=narrative_report.period or data_report.period,
        sections=data_report.sections,
        alerts=_merge_texts(narrative_report.alerts, data_report.alerts),
        actions=_merge_texts(narrative_report.actions, data_report.actions),
    )


def _merge_texts(primary: tuple[str, ...], secondary: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    seen: set[str] = set()
    for item in (*primary, *secondary):
        key = item.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(item)
    return tuple(merged)


def _merge_with_fallback(report: EmailReport, fallback: EmailReport) -> EmailReport:
    if _fallback_is_authoritative(fallback):
        return _authoritative_fallback_report(report, fallback)
    fallback_by_title = {_normalize_title(section.title): section for section in fallback.sections}
    merged_sections: list[EmailSection] = []
    seen: set[str] = set()
    for section in report.sections:
        key = _normalize_title(section.title)
        merged_sections.append(_merge_section(section, fallback_by_title.get(key)))
        seen.add(key)
    for section in fallback.sections:
        key = _normalize_title(section.title)
        if key not in seen:
            merged_sections.append(section)
    return EmailReport(
        report_type=_preferred_report_type(report, fallback),
        subject=report.subject or fallback.subject,
        from_name=report.from_name or fallback.from_name,
        headline=report.headline or fallback.headline,
        executive_summary=report.executive_summary or fallback.executive_summary,
        period=report.period or fallback.period,
        sections=tuple(merged_sections),
        alerts=report.alerts or fallback.alerts,
        actions=report.actions or fallback.actions,
    )


def _fallback_is_authoritative(fallback: EmailReport) -> bool:
    titles = {_normalize_title(section.title) for section in fallback.sections}
    fechamento_sections = {
        "faturamento por tipo de pagamento",
        "faturamento por tipo de venda",
        "produção por serviço",
        "producao por servico",
        "parcelamento de cartão",
        "parcelamento de cartao",
        "taxas de cartão de crédito",
        "taxas de cartao de credito",
    }
    return len(titles.intersection(fechamento_sections)) >= 3


def _authoritative_fallback_report(report: EmailReport, fallback: EmailReport) -> EmailReport:
    report_by_title = {_normalize_title(section.title): section for section in report.sections}
    sections: list[EmailSection] = []
    for fallback_section in fallback.sections:
        report_section = report_by_title.get(_normalize_title(fallback_section.title))
        sections.append(_fallback_section_with_llm_metadata(fallback_section, report_section))
    return EmailReport(
        report_type=_preferred_report_type(report, fallback),
        subject=report.subject or fallback.subject,
        from_name=report.from_name or fallback.from_name,
        headline=report.headline or fallback.headline,
        executive_summary=report.executive_summary or fallback.executive_summary,
        period=report.period or fallback.period,
        sections=tuple(sections),
        alerts=fallback.alerts or report.alerts,
        actions=fallback.actions or report.actions,
    )


def _preferred_report_type(report: EmailReport, fallback: EmailReport) -> str:
    if report.report_type and report.report_type != "generic":
        return report.report_type
    return fallback.report_type or report.report_type


def _fallback_section_with_llm_metadata(fallback: EmailSection, report: EmailSection | None) -> EmailSection:
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


def _merge_section(section: EmailSection, fallback: EmailSection | None) -> EmailSection:
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
    items = fallback.items if _should_prefer_fallback_items(section, fallback) else section.items
    return EmailSection(
        title=section.title or fallback.title,
        kind=section.kind or fallback.kind,
        total=section.total or fallback.total,
        highlight=section.highlight or fallback.highlight,
        items=items,
        tables=section.tables or fallback.tables,
        notes=section.notes or fallback.notes,
    )


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.casefold()).strip()


def _should_prefer_fallback_items(section: EmailSection, fallback: EmailSection) -> bool:
    if not fallback.items:
        return False
    if len(fallback.items) > len(section.items):
        return True
    return any(_looks_like_cross_section_item(item.label) for item in section.items)


def _looks_like_cross_section_item(label: str) -> bool:
    normalized = label.casefold()
    if "— total" in normalized or " - total" in normalized:
        return True
    return normalized.startswith(
        (
            "faturamento por ",
            "faturamento e comissão",
            "faturamento e comissao",
            "produção por ",
            "producao por ",
            "parcelamento de ",
            "taxas de ",
        )
    )


def _parse_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


def _normalized_lines(body: str) -> list[str]:
    lines: list[str] = []
    for raw in (body or "").splitlines():
        line = raw.strip()
        if line.startswith("- "):
            line = line[2:].strip()
        if line:
            lines.append(line)
    return lines


def _strip_numbered_prefix(line: str) -> str:
    match = _NUMBERED_RX.match(line)
    return match.group("text").strip() if match else line


def _section_kind(title: str) -> str:
    normalized = title.casefold()
    if "pagamento" in normalized or "parcelamento" in normalized:
        return "payment"
    if "comiss" in normalized or "concession" in normalized:
        return "commission"
    if "produção" in normalized or "producao" in normalized:
        return "production"
    if "taxas" in normalized:
        return "fees"
    if "faturamento" in normalized:
        return "revenue"
    return "default"


def _looks_like_metric(line: str) -> bool:
    return (":" in line or "—" in line) and "R$" in line


def _looks_like_pipe_table_line(line: str) -> bool:
    return "|" in line and len([cell for cell in line.split("|") if cell.strip()]) >= 2


def _inline_detail_items(line: str) -> list[EmailMetricItem]:
    prefix, separator, rest = line.partition(":")
    if not separator or "R$" not in rest:
        return []
    items: list[EmailMetricItem] = []
    for chunk in rest.split(";"):
        item = chunk.strip()
        if item.endswith("."):
            item = item[:-1].rstrip()
        if _looks_like_metric(item):
            items.append(EmailMetricItem.from_text(item))
    return items


def _is_alert(line: str) -> bool:
    normalized = line.casefold()
    return normalized.startswith(("registros com valor zero", "discrepância", "discrepancia"))


def _is_action(line: str) -> bool:
    normalized = line.casefold()
    return normalized.startswith(("priorizar", "negociar", "corrigir", "conciliar", "revisar"))


def _extract_period(text: str) -> str | None:
    match = _PERIOD_RX.search(text)
    return match.group(1) if match else None


def _first_meaningful_line(body: str) -> str | None:
    for line in _normalized_lines(body):
        if line:
            return line
    return None


try:
    _SYSTEM_PROMPT = get_prompt_registry().get_text("email_message_factory.system")
except KeyError:
    _SYSTEM_PROMPT = (
        "You structure a Portuguese executive email report. Return only valid JSON. "
        "Never generate HTML, never invent numbers, and preserve values exactly."
    )
