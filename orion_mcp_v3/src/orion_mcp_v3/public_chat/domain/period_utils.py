"""Utilitários de período para join de memórias."""

from __future__ import annotations

import re

_PERIOD_RE = re.compile(r"(\d{4})-(\d{2})")
_MONTH_NAMES = {
    "janeiro": "01",
    "fevereiro": "02",
    "marco": "03",
    "março": "03",
    "abril": "04",
    "maio": "05",
    "junho": "06",
    "julho": "07",
    "agosto": "08",
    "setembro": "09",
    "outubro": "10",
    "novembro": "11",
    "dezembro": "12",
}


def normalize_period_key(period: str | None) -> str | None:
    if not period:
        return None
    text = period.strip().lower()
    match = _PERIOD_RE.search(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    for name, month in _MONTH_NAMES.items():
        if name in text:
            year_match = re.search(r"(20\d{2})", text)
            year = year_match.group(1) if year_match else "2026"
            return f"{year}-{month}"
    return None


def period_in_context_key(context_key: str, period: str) -> bool:
    normalized = normalize_period_key(period)
    if not normalized:
        return True
    year, month = normalized.split("-")
    key = context_key.lower()
    if normalized in key:
        return True
    month_int = int(month)
    month_slug = f"{month_int:02d}"
    if f"_{month_slug}_" in key or f"-{month_int}-" in key:
        return True
    for name, num in _MONTH_NAMES.items():
        if num == month and name in key and year in key:
            return True
    return False
