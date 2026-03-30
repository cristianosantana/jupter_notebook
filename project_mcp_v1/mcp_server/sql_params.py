"""Substituição segura de placeholders nos SQL whitelisted."""

from __future__ import annotations

import re
from datetime import date

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_iso_date(value: str) -> str:
    s = value.strip()
    if not _DATE_RE.fullmatch(s):
        raise ValueError(f"Data inválida (use YYYY-MM-DD): {value!r}")
    date.fromisoformat(s)
    return s


def inject_date_range(sql: str, date_from: str, date_to: str) -> str:
    d0 = validate_iso_date(date_from)
    d1 = validate_iso_date(date_to)
    if d0 > d1:
        raise ValueError("date_from não pode ser posterior a date_to.")
    out = sql.replace("__MCP_DATE_FROM__", f"'{d0}'")
    out = out.replace("__MCP_DATE_TO__", f"'{d1}'")
    if "__MCP_DATE" in out:
        raise ValueError("SQL ainda contém placeholders __MCP_DATE_* não substituídos.")
    return out


def apply_placeholders(
    sql: str,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    needs_from = "__MCP_DATE_FROM__" in sql
    needs_to = "__MCP_DATE_TO__" in sql
    if needs_from or needs_to:
        if not date_from or not date_to:
            raise ValueError(
                "Esta consulta exige date_from e date_to (formato YYYY-MM-DD)."
            )
        return inject_date_range(sql, date_from, date_to)
    return sql
