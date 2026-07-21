"""Leitura nativa de ``key_metrics`` — ``memory_curta`` como fonte analítica."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping

from orion_mcp_v3.public_chat.domain.direct_answer_parser import _parse_br_currency, format_currency

_CURRENCY_IN_TEXT_RE = re.compile(r"R\$\s*([\d.]+,\d{2})", re.IGNORECASE)
_PERCENT_RE = re.compile(r"([\d.,]+)\s*%")
_MATRIX_DEFAULT_COLUMNS = ("venda normal", "financiamento", "total comissao")

_DEFAULT_ENTITY_FIELDS = ("tipo", "label", "metric", "concessionaria", "departamento", "servico", "produto", "parcelas")
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
            meta = raw.get("_meta") if isinstance(raw.get("_meta"), dict) else None
            rows = rows_from_table_sample(sample, meta=meta)
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


def rows_from_table_sample(raw: Any, *, meta: Mapping[str, Any] | None = None) -> tuple[KeyMetricsRow, ...]:
    if not isinstance(raw, list):
        return ()
    subdimension = None
    if meta is not None:
        raw_sub = meta.get("subdimension")
        if isinstance(raw_sub, str) and raw_sub.strip():
            subdimension = raw_sub.strip()
    rows: list[KeyMetricsRow] = []
    for line in raw:
        if not isinstance(line, str) or not line.strip():
            continue
        currency_count = len(list(_CURRENCY_IN_TEXT_RE.finditer(line)))
        if currency_count > 1:
            parsed_rows = _parse_matrix_table_line(line, subdimension=subdimension)
            rows.extend(parsed_rows)
            continue
        parsed = _parse_table_line(line)
        if parsed is not None:
            rows.append(parsed)
    return tuple(rows)


def entity_slug(value: str) -> str:
    """Normaliza rótulo de entidade para chave de coluna (ex: ``Venda Normal`` → ``venda_normal``)."""
    normalized = _normalize_text(value)
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")


def lookup_entity(rows: tuple[KeyMetricsRow, ...], entity: str) -> KeyMetricsRow | None:
    needle = entity.lower().strip()
    slug = entity_slug(entity)
    for row in rows:
        label_lower = row.label.lower()
        if needle and needle in label_lower:
            return row
        # Schema estruturado: chaves tipadas usam underscore (venda_normal);
        # o requirement ainda traz o rótulo humano ("Venda Normal").
        if slug and slug in _label_slugs(row.label):
            return row
    return None


def _label_slugs(label: str) -> frozenset[str]:
    """Slugs dos segmentos de um label (escopo | coluna, etc.)."""
    parts = re.split(r"[|:/]+", label)
    slugs = {entity_slug(part) for part in parts if part.strip()}
    # Também o label inteiro (ex: "Venda Normal - GWM BAMAQ" sem pipes).
    whole = entity_slug(label)
    if whole:
        slugs.add(whole)
    return frozenset(s for s in slugs if s)


def lookup_entity_group(rows: tuple[KeyMetricsRow, ...], entity: str) -> KeyMetricsRow | None:
    group_token = _group_lookup_token(entity)
    if group_token is None:
        return None
    matches = [row for row in rows if group_token in _normalize_text(row.label)]
    if not matches:
        return None
    total = sum(row.value for row in matches)
    return KeyMetricsRow(label=entity.lower(), value=total, raw_value=format_currency(total))


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
        if value is None:
            return None
        label = text[: currency_match.start()].strip(" -:\t")
        if not label:
            label = text
        return KeyMetricsRow(label=label, value=value, raw_value=currency_match.group(0))
    return None


def _parse_matrix_table_line(
    line: str,
    *,
    subdimension: str | None = None,
) -> tuple[KeyMetricsRow, ...]:
    text = line.strip()
    if not text:
        return ()
    matches = list(_CURRENCY_IN_TEXT_RE.finditer(text))
    if not matches:
        single = _parse_table_line(text)
        return (single,) if single is not None else ()

    scope_entity = _matrix_scope_entity(text, matches[0].start())
    rows: list[KeyMetricsRow] = []
    for index, match in enumerate(matches):
        value = _parse_br_currency(match.group(1))
        if value is None:
            continue
        column_label = _matrix_column_label(text, match, index=index, matches=matches)
        if scope_entity and column_label:
            label = f"{scope_entity} | {column_label}"
        elif scope_entity:
            label = scope_entity
        elif column_label:
            label = column_label
        else:
            label = text[: match.start()].strip(" -:\t|") or text
        rows.append(
            KeyMetricsRow(
                label=label,
                value=value,
                raw_value=match.group(0),
            )
        )
    return tuple(rows)


def _matrix_scope_entity(text: str, first_currency_start: int) -> str:
    prefix = text[:first_currency_start]
    if "|" in prefix:
        return prefix.split("|", 1)[0].strip()
    if " - " in prefix:
        parts = prefix.rsplit(" - ", 1)
        if len(parts) == 2:
            return parts[1].strip(" :-\t")
    return prefix.strip(" -:\t|")


def _matrix_column_label(
    text: str,
    match: re.Match[str],
    *,
    index: int,
    matches: list[re.Match[str]],
) -> str:
    start = matches[index - 1].end() if index > 0 else 0
    segment = text[start : match.start()]
    if "|" in segment:
        segment = segment.split("|")[-1]
    label = segment.strip(" -:\t")
    if label:
        return label.rstrip(":")
    if index < len(_MATRIX_DEFAULT_COLUMNS):
        return _MATRIX_DEFAULT_COLUMNS[index]
    return f"coluna_{index + 1}"


def _parse_percent(raw: str) -> float | None:
    text = raw.strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _group_lookup_token(entity: str) -> str | None:
    normalized = _normalize_text(entity)
    if normalized in {"cortesia", "cortesias"}:
        return "cortesia"
    return None


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()


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

