"""Formatação de células de tabela (espelho de tableCellFormat.ts)."""

from __future__ import annotations

import re
from typing import Any, Literal

TableCellKind = Literal[
    "empty", "boolean", "integer", "float", "percent", "currency", "date", "datetime", "text"
]

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]")
_BR_SLASH = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")


def strip_spaces(s: str) -> str:
    return re.sub(r"\s", "", s)


def parse_locale_number_string(raw: str) -> float | None:
    t = strip_spaces(raw.strip())
    if not t or not re.match(r"^-?[\d.,]+$", t):
        return None
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    if "," in t and "." in t:
        last_c, last_d = t.rfind(","), t.rfind(".")
        if last_c > last_d:
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        parts = t.split(",")
        if len(parts) == 2 and len(parts[1]) <= 2:
            t = f"{parts[0]}.{parts[1]}"
        else:
            t = t.replace(",", "")
    elif "." in t:
        parts = t.split(".")
        if len(parts) == 2 and len(parts[1]) <= 2:
            t = f"{parts[0]}.{parts[1]}"
        else:
            t = "".join(parts)
    try:
        n = float(f"-{t}" if neg else t)
    except ValueError:
        return None
    return n if n == n else None  # noqa: PLR0124 — NaN check


def _looks_numeric_only(s: str) -> bool:
    t = strip_spaces(s.strip())
    t = re.sub(r"^\s*R\$\s*", "", t, flags=re.I)
    t = re.sub(r"%$", "", t)
    return bool(re.match(r"^-?[\d.,]+$", t))


def _br_group_int(abs_int: int) -> str:
    s = str(abs_int)
    parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:])
        s = s[:-3]
    if s:
        parts.insert(0, s)
    return ".".join(parts)


def _format_number_auto(n: float) -> str:
    if abs(n - round(n)) < 1e-9:
        ni = int(round(n))
        sign = "-" if ni < 0 else ""
        return sign + _br_group_int(abs(ni))
    sign = "-" if n < 0 else ""
    a = abs(n)
    frac = f"{a:.8f}".rstrip("0").rstrip(".")
    if "." in frac:
        ip, fp = frac.split(".", 1)
        ip_i = int(ip) if ip else 0
        return sign + _br_group_int(ip_i) + "," + fp
    return sign + _br_group_int(int(a))


def _fmt_iso_date(s: str) -> str | None:
    if not _ISO_DATE.match(s):
        return None
    from datetime import datetime

    try:
        d = datetime.fromisoformat(f"{s}T12:00:00")
        return d.strftime("%d %b %Y")
    except ValueError:
        return None


def _fmt_iso_dt(s: str) -> str | None:
    t = s.strip()
    if not _ISO_DT.match(t):
        return None
    from datetime import datetime

    try:
        d = datetime.fromisoformat(t.replace("Z", "+00:00"))
        return d.strftime("%d %b %Y, %H:%M")
    except ValueError:
        return None


def _fmt_br_slash(s: str) -> str | None:
    m = _BR_SLASH.match(s.strip())
    if not m:
        return None
    from datetime import datetime

    try:
        d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return d.strftime("%d %b %Y")
    except ValueError:
        return None


def infer_table_cell_kind(raw: Any) -> TableCellKind:
    if raw is None:
        return "empty"
    if isinstance(raw, bool):
        return "boolean"
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and (raw != raw or raw in (float("inf"), float("-inf"))):
            return "empty"
        return "integer" if isinstance(raw, int) or abs(raw - round(raw)) < 1e-9 else "float"
    if not isinstance(raw, str):
        return "text"
    s = raw.strip()
    if not s:
        return "empty"
    if _ISO_DT.match(s):
        return "datetime"
    if _ISO_DATE.match(s):
        return "date"
    if _BR_SLASH.match(s):
        return "date"
    pct = strip_spaces(s)
    if pct.endswith("%"):
        if parse_locale_number_string(pct[:-1]) is not None:
            return "percent"
    if re.match(r"^R\$\s*", s, re.I):
        return "currency"
    if _looks_numeric_only(s):
        n = parse_locale_number_string(s)
        if n is None:
            return "text"
        return "integer" if abs(n - round(n)) < 1e-9 else "float"
    return "text"


def format_table_cell(raw: Any) -> str:
    if raw is None:
        return "—"
    if isinstance(raw, bool):
        return "sim" if raw else "não"
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and (raw != raw or raw in (float("inf"), float("-inf"))):
            return "—"
        return _format_number_auto(float(raw))
    if not isinstance(raw, str):
        return str(raw)
    s = raw.strip()
    if not s:
        return "—"
    for fn in (_fmt_iso_dt, _fmt_iso_date, _fmt_br_slash):
        out = fn(s)
        if out:
            return out
    pct = strip_spaces(s)
    if pct.endswith("%"):
        n = parse_locale_number_string(pct[:-1])
        if n is not None:
            return f"{_format_number_auto(n).replace('.', ',')}\u00a0%"
    if re.match(r"^R\$\s*", s, re.I):
        n = parse_locale_number_string(re.sub(r"^R\$\s*", "", s, flags=re.I))
        if n is not None:
            return f"R$ {_format_number_auto(n)}"
    if _looks_numeric_only(s):
        n = parse_locale_number_string(s)
        if n is not None:
            return _format_number_auto(n)
    return s


def table_cell_tooltip(raw: Any) -> str | None:
    if raw is None or isinstance(raw, (bool, int, float)):
        return None
    raw_str = str(raw).strip()
    if not raw_str:
        return None
    formatted = format_table_cell(raw)
    if formatted == raw_str or formatted == "—":
        return None
    return raw_str


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
