"""Parser determinístico de secções em validated_answer."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedRow:
    label: str
    value: float
    raw_value: str


@dataclass(frozen=True, slots=True)
class ParsedSection:
    title: str
    rows: tuple[ParsedRow, ...]
    total: float | None = None


_CURRENCY_RE = re.compile(
    r"R\$\s*([\d.]+,\d{2})",
    re.IGNORECASE,
)
_SECTION_HEADER_RE = re.compile(
    r"^(.+?)\s*[—–-]\s*Total:\s*R\$\s*([\d.]+,\d{2})",
    re.IGNORECASE | re.MULTILINE,
)
_ROW_RE = re.compile(
    r"^(.+?)\s+R\$\s*([\d.]+,\d{2})\s*$",
    re.MULTILINE,
)


def parse_validated_answer(text: str) -> tuple[ParsedSection, ...]:
    normalized = (text or "").strip()
    if not normalized:
        return ()

    sections: list[ParsedSection] = []
    headers = list(_SECTION_HEADER_RE.finditer(normalized))
    if not headers:
        rows = _parse_rows(normalized)
        if rows:
            sections.append(ParsedSection(title="documento", rows=tuple(rows)))
        return tuple(sections)

    for index, match in enumerate(headers):
        title = match.group(1).strip()
        total = _parse_br_currency(match.group(2))
        start = match.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(normalized)
        block = normalized[start:end]
        rows = _parse_rows(block)
        sections.append(ParsedSection(title=title, rows=tuple(rows), total=total))
    return tuple(sections)


def find_section_by_needle(sections: tuple[ParsedSection, ...], *needles: str) -> ParsedSection | None:
    lowered = [needle.lower() for needle in needles]
    for section in sections:
        title = section.title.lower()
        if any(needle in title for needle in lowered):
            return section
    return None


def ranking_row(
    section: ParsedSection,
    *,
    ascending: bool,
    exclude_zero: bool = True,
) -> ParsedRow | None:
    candidates = [
        row for row in section.rows
        if not exclude_zero or row.value > 0
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: row.value) if ascending else max(candidates, key=lambda row: row.value)


def lookup_row_by_entity(section: ParsedSection, entity: str) -> ParsedRow | None:
    needle = entity.lower()
    for row in section.rows:
        if needle in row.label.lower():
            return row
    return None


def _parse_rows(block: str) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    for match in _ROW_RE.finditer(block):
        label = match.group(1).strip()
        raw_value = match.group(2)
        value = _parse_br_currency(raw_value)
        if value is None:
            continue
        rows.append(ParsedRow(label=label, value=value, raw_value=f"R$ {raw_value}"))
    return rows


def _parse_br_currency(raw: str) -> float | None:
    try:
        normalized = raw.replace(".", "").replace(",", ".")
        return float(normalized)
    except (TypeError, ValueError):
        return None


def format_currency(value: float) -> str:
    integer, decimals = divmod(round(value * 100), 100)
    integer_str = f"{integer:,}".replace(",", ".")
    return f"R$ {integer_str},{decimals:02d}"
