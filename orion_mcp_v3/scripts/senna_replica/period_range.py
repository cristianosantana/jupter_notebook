"""Expansão de ranges de período — cópia local (Senna isolado)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_MONTH_ALIASES = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
    "jan": 1,
    "fev": 2,
    "mar": 3,
    "abr": 4,
    "mai": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "set": 9,
    "out": 10,
    "nov": 11,
    "dez": 12,
}


def expand_period_range(start: str, end: str) -> tuple[str, ...]:
    if not _is_year_month(start) or not _is_year_month(end):
        return ()
    start_y, start_m = int(start[:4]), int(start[5:7])
    end_y, end_m = int(end[:4]), int(end[5:7])
    cursor = date(start_y, start_m, 1)
    stop = date(end_y, end_m, 1)
    if cursor > stop:
        cursor, stop = stop, cursor
    periods: list[str] = []
    while cursor <= stop:
        periods.append(f"{cursor.year:04d}-{cursor.month:02d}")
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return tuple(periods)


def periods_from_question(message: str) -> tuple[str, ...]:
    text = _normalize_text(message or "")
    if not text:
        return ()

    year_match = re.search(r"(20\d{2})", text)
    if year_match:
        year = year_match.group(1)
        if re.search(r"primeiro\s+semestre|1\s*[ºo°]?\s*semestre|\bh1\b", text):
            return expand_period_range(f"{year}-01", f"{year}-06")
        if re.search(r"segundo\s+semestre|2\s*[ºo°]?\s*semestre|\bh2\b", text):
            return expand_period_range(f"{year}-07", f"{year}-12")

    aliases = "|".join(re.escape(a) for a in sorted(_MONTH_ALIASES, key=len, reverse=True))
    matches: list[tuple[int, str]] = []
    years = tuple(dict.fromkeys(re.findall(r"\b(20\d{2})\b", text)))
    if len(years) == 1:
        for match in re.finditer(rf"\b({aliases})\b", text):
            month = _MONTH_ALIASES[match.group(1)]
            matches.append((match.start(), f"{years[0]}-{month:02d}"))
    for match in re.finditer(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b", text):
        matches.append((match.start(), f"{match.group(1)}-{int(match.group(2)):02d}"))

    ordered: list[str] = []
    for _, period in sorted(matches, key=lambda item: item[0]):
        if period not in ordered:
            ordered.append(period)
    if len(ordered) >= 2:
        return expand_period_range(ordered[0], ordered[-1])
    return tuple(ordered)


def _is_year_month(value: str | None) -> bool:
    return isinstance(value, str) and bool(_YEAR_MONTH_RE.match(value.strip()))


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()
