"""Modelos semânticos seguros para montagem de e-mails."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

_INLINE_VALUE_RX = re.compile(r"^(?P<label>.+?)\s+(?P<value>R\$\s*[\d.,]+)(?:\s*(?P<detail>\([^)]*\)))?\.?$")


@dataclass(frozen=True, slots=True)
class EmailMetricItem:
    label: str
    value: str | None = None
    detail: str | None = None

    @classmethod
    def from_text(cls, text: str) -> "EmailMetricItem":
        label, value, detail = _split_metric_text(text)
        return cls(label=label, value=value, detail=detail)


@dataclass(frozen=True, slots=True)
class EmailSection:
    title: str
    kind: str = "default"
    total: str | None = None
    highlight: str | None = None
    items: tuple[EmailMetricItem, ...] = ()
    notes: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EmailSection":
        items = tuple(_coerce_item(item) for item in _list(raw.get("items")))
        highlight = _text(raw.get("highlight")) or _join_highlight(raw)
        notes = _list(raw.get("notes")) + _list(raw.get("risks"))
        return cls(
            title=_text(raw.get("title")) or "Seção",
            kind=_text(raw.get("kind")) or _text(raw.get("category")) or "default",
            total=_text(raw.get("total")),
            highlight=highlight,
            items=items,
            notes=tuple(filter(None, (_text(item) for item in notes))),
        )


@dataclass(frozen=True, slots=True)
class EmailReport:
    report_type: str = "generic"
    subject: str = ""
    from_name: str = "Orion"
    headline: str | None = None
    executive_summary: str | None = None
    period: str | None = None
    sections: tuple[EmailSection, ...] = ()
    alerts: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "EmailReport":
        report_type = _text(raw.get("type")) or _text(raw.get("report_type")) or "generic"
        sections = tuple(EmailSection.from_mapping(item) for item in _list(raw.get("sections")) if isinstance(item, Mapping))
        if not sections:
            sections = _sections_from_typed_payload(report_type, raw)
        return cls(
            report_type=report_type,
            subject=_text(raw.get("subject")) or "",
            from_name=_text(raw.get("from_name")) or "Orion",
            headline=_text(raw.get("headline")) or _typed_headline(raw),
            executive_summary=_text(raw.get("executive_summary")),
            period=_text(raw.get("period")),
            sections=sections,
            alerts=tuple(filter(None, (_text(item) for item in _list(raw.get("alerts"))))),
            actions=tuple(filter(None, (_text(item) for item in _list(raw.get("actions"))))),
        )

    def with_defaults(self, *, subject: str, from_name: str) -> "EmailReport":
        return EmailReport(
            report_type=self.report_type,
            subject=self.subject or subject,
            from_name=self.from_name or from_name,
            headline=self.headline,
            executive_summary=self.executive_summary,
            period=self.period,
            sections=self.sections,
            alerts=self.alerts,
            actions=self.actions,
        )


def _coerce_item(raw: Any) -> EmailMetricItem:
    if isinstance(raw, Mapping):
        return EmailMetricItem(
            label=_text(raw.get("label")) or _text(raw.get("name")) or "Item",
            value=_text(raw.get("value")),
            detail=_text(raw.get("detail")) or _text(raw.get("percentage")) or _text(raw.get("pct")),
        )
    return EmailMetricItem.from_text(_text(raw) or "")


def _sections_from_typed_payload(report_type: str, raw: Mapping[str, Any]) -> tuple[EmailSection, ...]:
    items = tuple(_coerce_item(item) for item in _list(raw.get("items")))
    notes = tuple(filter(None, (_text(item) for item in _list(raw.get("notes")))))
    if report_type == "ranking" and items:
        metric = _text(raw.get("metric")) or "Ranking"
        dimension = _text(raw.get("dimension"))
        title = "Ranking"
        return (
            EmailSection(
                title=title,
                kind="ranking",
                total=_text(raw.get("headline_value")),
                highlight=items[0].label if items else None,
                items=items,
                notes=tuple(filter(None, (metric, dimension, *notes))),
            ),
        )
    if report_type == "comparacao":
        comparison_items = tuple(_coerce_item(item) for item in _list(raw.get("comparisons")) or _list(raw.get("items")))
        return (
            EmailSection(
                title="Comparação",
                kind="comparison",
                total=_text(raw.get("headline_value")),
                items=comparison_items,
                notes=notes,
            ),
        )
    if report_type == "analise_unica":
        return (
            EmailSection(
                title=_text(raw.get("headline_label")) or "Análise",
                kind="single-analysis",
                total=_text(raw.get("headline_value")),
                items=items,
                notes=notes,
            ),
        )
    return ()


def _typed_headline(raw: Mapping[str, Any]) -> str | None:
    label = _text(raw.get("headline_label"))
    value = _text(raw.get("headline_value"))
    if label and value:
        return f"{label}: {value}"
    return value or label


def _join_highlight(raw: Mapping[str, Any]) -> str | None:
    label = _text(raw.get("highlight_label"))
    value = _text(raw.get("highlight_value"))
    pct = _text(raw.get("highlight_pct"))
    if label and value and pct:
        return f"{label}: {value} ({pct})"
    if label and value:
        return f"{label}: {value}"
    return label or value


def _split_metric_text(text: str) -> tuple[str, str | None, str | None]:
    raw = text.strip()
    if not raw:
        return "", None, None
    label, sep, rest = raw.partition(":")
    if not sep:
        label, sep, rest = raw.partition("—")
    if not sep:
        inline = _INLINE_VALUE_RX.match(raw)
        if inline:
            return (
                inline.group("label").strip(),
                inline.group("value").strip(),
                (inline.group("detail") or "").strip() or None,
            )
        return raw, None, None
    rest = rest.strip()
    detail = None
    if "(" in rest and rest.endswith(")"):
        value, _, suffix = rest.rpartition("(")
        rest = value.strip()
        detail = f"({suffix.strip()}"
    return label.strip(), rest or None, detail


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
