"""Leitura nativa de ``key_metrics`` — ``memory_curta`` como fonte analítica."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from orion_mcp_v3.public_chat.domain.direct_answer_parser import _parse_br_currency, format_currency

_CURRENCY_IN_TEXT_RE = re.compile(r"R\$\s*([\d.]+,\d{2})", re.IGNORECASE)
_PERCENT_RE = re.compile(r"([\d.,]+)\s*%")

_DEFAULT_ENTITY_FIELDS = ("tipo", "label", "metric", "concessionaria", "departamento", "servico", "produto")
_DEFAULT_VALUE_FIELDS = ("valor", "value", "faturamento", "valor_comissao", "percentual")


@dataclass(frozen=True, slots=True)
class KeyMetricsRow:
    label: str
    value: float
    raw_value: str
    percentual: str | None = None


@dataclass(frozen=True, slots=True)
class NormalizedKeyMetricsEntry:
    shape: str
    rows: tuple[KeyMetricsRow, ...] = ()
    scalar_value: float | None = None
    table_rows_sample: tuple[str, ...] = ()


def parse_metric_value(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    percent_match = _PERCENT_RE.search(text)
    if percent_match and "R$" not in text:
        return _parse_percent(percent_match.group(1))
    match = _CURRENCY_IN_TEXT_RE.search(text)
    if match:
        return _parse_br_currency(match.group(1))
    return _parse_br_currency(text)


def normalize_key_metrics_entry(key: str, raw: Any) -> NormalizedKeyMetricsEntry:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return NormalizedKeyMetricsEntry(shape="scalar", scalar_value=float(raw))
    if isinstance(raw, dict):
        if "table_rows_sample" in raw:
            sample = raw.get("table_rows_sample")
            rows = rows_from_table_sample(sample)
            return NormalizedKeyMetricsEntry(
                shape="table",
                rows=rows,
                table_rows_sample=tuple(str(item) for item in sample) if isinstance(sample, list) else (),
            )
        payload = raw.get("rows", raw.get("items"))
        if payload is not None:
            rows = rows_from_array(payload)
            return NormalizedKeyMetricsEntry(shape="array", rows=rows)
        if "value" in raw and isinstance(raw["value"], (int, float)):
            return NormalizedKeyMetricsEntry(shape="scalar", scalar_value=float(raw["value"]))
    if isinstance(raw, list):
        if raw and isinstance(raw[0], str):
            rows = rows_from_table_sample(raw)
            return NormalizedKeyMetricsEntry(
                shape="table",
                rows=rows,
                table_rows_sample=tuple(str(item) for item in raw),
            )
        return NormalizedKeyMetricsEntry(shape="array", rows=rows_from_array(raw))
    return NormalizedKeyMetricsEntry(shape="unknown")


def rows_from_key_metrics_entry(key: str, raw: Any) -> tuple[KeyMetricsRow, ...]:
    return normalize_key_metrics_entry(key, raw).rows


def sample_labels_from_entry(
    rows: tuple[KeyMetricsRow, ...],
    *,
    entity_field: str = "tipo",
) -> tuple[str, ...]:
    if rows:
        return tuple(dict.fromkeys(row.label for row in rows if row.label))
    _ = entity_field
    return ()


def rows_from_array(
    raw: Any,
    *,
    entity_fields: tuple[str, ...] = _DEFAULT_ENTITY_FIELDS,
    value_fields: tuple[str, ...] = _DEFAULT_VALUE_FIELDS,
) -> tuple[KeyMetricsRow, ...]:
    if not isinstance(raw, list):
        return ()
    rows: list[KeyMetricsRow] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if "note" in item and len(item) == 1:
            continue
        label = _first_str(item, entity_fields)
        value_raw = _first_value(item, value_fields)
        value = parse_metric_value(value_raw)
        if not label:
            continue
        if value is None and item.get("percentual"):
            value = parse_metric_value(item.get("percentual"))
        if value is None:
            continue
        percentual = _optional_str(item.get("percentual") or item.get("percent"))
        raw_value = value_raw if isinstance(value_raw, str) and "R$" in str(value_raw) else format_currency(value)
        if percentual and value_raw == item.get("percentual"):
            raw_value = percentual
        rows.append(
            KeyMetricsRow(
                label=label,
                value=value,
                raw_value=raw_value,
                percentual=percentual,
            )
        )
    return tuple(rows)


def rows_from_table_sample(raw: Any) -> tuple[KeyMetricsRow, ...]:
    if not isinstance(raw, list):
        return ()
    rows: list[KeyMetricsRow] = []
    for line in raw:
        if not isinstance(line, str) or not line.strip():
            continue
        parsed = _parse_table_line(line)
        if parsed is None:
            continue
        rows.append(parsed)
    return tuple(rows)


def lookup_entity(rows: tuple[KeyMetricsRow, ...], entity: str) -> KeyMetricsRow | None:
    needle = entity.lower()
    for row in rows:
        if needle in row.label.lower():
            return row
    return None


def aggregate_row(
    rows: tuple[KeyMetricsRow, ...],
    *,
    ascending: bool,
    exclude_zero: bool = True,
) -> KeyMetricsRow | None:
    candidates = [row for row in rows if not exclude_zero or row.value > 0]
    if not candidates:
        return None
    return min(candidates, key=lambda row: row.value) if ascending else max(candidates, key=lambda row: row.value)


def sum_row_values(rows: tuple[KeyMetricsRow, ...]) -> float | None:
    if not rows:
        return None
    return sum(row.value for row in rows)


def scalar_from_key_metrics(
    key_metrics: Mapping[str, Any],
    keys: tuple[str, ...],
) -> tuple[str, float] | None:
    for key in keys:
        raw = key_metrics.get(key)
        if raw is None:
            continue
        normalized = normalize_key_metrics_entry(key, raw)
        if normalized.shape == "scalar" and normalized.scalar_value is not None:
            return key, normalized.scalar_value
        value = parse_metric_value(raw)
        if value is not None:
            return key, value
        rows = rows_from_key_metrics_entry(key, raw)
        total = sum_row_values(rows)
        if total is not None:
            return key, total
    return None


def _parse_table_line(line: str) -> KeyMetricsRow | None:
    text = line.strip()
    if not text:
        return None
    currency_match = _CURRENCY_IN_TEXT_RE.search(text)
    if currency_match:
        value = _parse_br_currency(currency_match.group(1))
        label = text[: currency_match.start()].strip(" -:\t")
        if not label:
            label = text
        return KeyMetricsRow(label=label, value=value, raw_value=currency_match.group(0))
    return None


def _parse_percent(raw: str) -> float | None:
    text = raw.strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _first_str(item: Mapping[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        raw = item.get(field)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _first_value(item: Mapping[str, Any], fields: tuple[str, ...]) -> Any:
    for field in fields:
        if field in item:
            return item[field]
    return None


def _optional_str(raw: Any) -> str | None:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None

