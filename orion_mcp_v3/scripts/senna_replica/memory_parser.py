"""Converte memory.json (ranked_list / matriz via ``_meta``) → observados para o .pl."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PERIOD_RE = re.compile(r"periodo[_-](\d{4}-\d{2})", re.IGNORECASE)
_SAMPLE_COL_RE = re.compile(
    r"(?P<col>[A-Za-z0-9_ ]+)\s*:\s*(?P<val>R\$\s*[\d.]+,\d{2})",
    re.IGNORECASE,
)
_MATRIX_SCHEMAS = frozenset({"table", "matrix"})


def _parse_metric_value(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    match = re.search(r"R\$\s*([\d.]+,\d{2})", text, flags=re.IGNORECASE)
    if match:
        return float(match.group(1).replace(".", "").replace(",", "."))
    match = re.search(r"([\d.]+,\d{2})", text)
    if match:
        return float(match.group(1).replace(".", "").replace(",", "."))
    cleaned = text.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(cleaned.split()[0])
    except (ValueError, IndexError):
        return None


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip()


def _entity_slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _normalize_text(value)).strip("_")


def _label_from_column_slug(slug: str, column_labels: dict[str, str] | None = None) -> str:
    if column_labels:
        for key, label in column_labels.items():
            if _entity_slug(key) == slug:
                return label
    # venda_normal → "Venda Normal"
    return " ".join(part.capitalize() for part in slug.split("_") if part)


@dataclass(frozen=True, slots=True)
class Observado:
    index_key: str
    label: str
    period: str
    value: float


@dataclass(frozen=True, slots=True)
class MemoryParseResult:
    observados: tuple[Observado, ...]
    truncated: bool
    missing_periods: tuple[str, ...]
    source_context_keys: tuple[str, ...]


def period_from_context_key(context_key: str) -> str | None:
    match = _PERIOD_RE.search(context_key or "")
    return match.group(1) if match else None


def _meta_columns(meta: dict[str, Any]) -> tuple[str, ...]:
    raw = meta.get("columns") or meta.get("measure_fields") or ()
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(str(item) for item in raw if item)


def _meta_column_labels(meta: dict[str, Any]) -> dict[str, str]:
    raw = meta.get("column_labels")
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if k and v}


def _is_matrix_meta(meta: dict[str, Any]) -> bool:
    schema = str(meta.get("schema") or "").strip().lower()
    if schema in _MATRIX_SCHEMAS:
        return True
    return bool(_meta_columns(meta))


def _row_entity_field(meta: dict[str, Any]) -> str | None:
    """Campo da linha na matriz: ``subdimension`` (escopo) tem prioridade."""
    for key in ("subdimension", "entity_field"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return None


def _rows_from_entry(entry: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(entry, dict):
        return [], {}
    meta = entry.get("_meta") if isinstance(entry.get("_meta"), dict) else {}
    rows = entry.get("rows") or entry.get("items") or []
    parsed: list[dict[str, Any]] = []
    if isinstance(rows, list):
        parsed = [r for r in rows if isinstance(r, dict)]
    if parsed:
        return parsed, meta

    sample = entry.get("table_rows_sample")
    if isinstance(sample, list) and sample:
        return _rows_from_table_sample(sample, meta=meta), meta
    return [], meta


def _rows_from_table_sample(
    sample: list[Any],
    *,
    meta: dict[str, Any],
) -> list[dict[str, Any]]:
    """Converte ``table_rows_sample`` em dicts usando ``_meta.columns`` + subdimension."""
    entity_key = _row_entity_field(meta) or "entity"
    columns = {_entity_slug(c): c for c in _meta_columns(meta)}
    out: list[dict[str, Any]] = []
    for item in sample:
        if not isinstance(item, str) or not item.strip() or item.strip() == "…":
            continue
        text = item.strip()
        row: dict[str, Any] = {}
        # Escopo = texto antes do primeiro "|"
        if "|" in text:
            scope, rest = text.split("|", 1)
            row[entity_key] = scope.strip()
            text = rest
        else:
            # fallback: tudo antes do primeiro "campo:"
            first = _SAMPLE_COL_RE.search(text)
            if first:
                row[entity_key] = text[: first.start()].strip(" -:\t|")
                text = text[first.start() :]
        for match in _SAMPLE_COL_RE.finditer(text):
            col_slug = _entity_slug(match.group("col"))
            col_name = columns.get(col_slug, match.group("col").strip())
            row[col_name] = match.group("val").strip()
        if len(row) > 1:
            out.append(row)
    return out


def _resolve_entry(
    key_metrics: dict[str, Any],
    index_key: str,
) -> tuple[str, Any] | None:
    """Resolve entrada em key_metrics: exact → substring → tokens fortes."""
    if index_key in key_metrics:
        return index_key, key_metrics[index_key]
    needle = _entity_slug(index_key)
    keys = list(key_metrics.keys())
    for key in keys:
        slug = _entity_slug(key)
        if needle and (needle in slug or slug in needle):
            return key, key_metrics[key]
    tokens = [t for t in needle.split("_") if t not in {"por", "de", "e", "a", "o"} and len(t) > 2]
    if not tokens:
        return None
    scored: list[tuple[int, str]] = []
    for key in keys:
        slug = _entity_slug(key)
        score = sum(1 for t in tokens if t in slug)
        if "tipo" in tokens and "tipo" not in slug:
            continue
        if score >= max(2, (len(tokens) + 1) // 2):
            scored.append((score, key))
    if scored:
        scored.sort(key=lambda item: (-item[0], len(item[1])))
        best = scored[0][1]
        return best, key_metrics[best]
    return None


def _row_matches_scope(
    row: dict[str, Any],
    scope_filters: tuple[tuple[str, str], ...],
    *,
    row_entity_field: str | None = None,
) -> bool:
    """Aplica filtros só quando a dimensão existe na row.

    Campo ausente → ignora o filtro (não zera observados).
    ``row_entity_field`` (subdimension) só entra se o nome bater com a dimensão.
    """
    if not scope_filters:
        return True
    row_keys = {_entity_slug(k): k for k in row}
    for dimension, value in scope_filters:
        dim = _entity_slug(dimension)
        needle = _normalize_text(value)
        col = row_keys.get(dim)
        if col is None and row_entity_field and _entity_slug(row_entity_field) == dim:
            col = row_keys.get(_entity_slug(row_entity_field)) or (
                row_entity_field if row_entity_field in row else None
            )
        if col is None:
            continue
        if _normalize_text(str(row[col])) != needle:
            return False
    return True


def _observados_from_matrix_row(
    *,
    index_key: str,
    period: str,
    row: dict[str, Any],
    meta: dict[str, Any],
    operand_labels: tuple[str, ...],
) -> list[Observado]:
    """Expande colunas de ``_meta.columns`` (ou operand_labels ∩ colunas da row)."""
    out: list[Observado] = []
    row_cols = {_entity_slug(k): k for k in row}
    meta_cols = [_entity_slug(c) for c in _meta_columns(meta)]
    column_labels = _meta_column_labels(meta)
    # total_* só entra se operand_labels pedir explicitamente
    skip_totals = {"total", "total_comissao"}

    targets: list[tuple[str, str]] = []
    if operand_labels:
        for label in operand_labels:
            slug = _entity_slug(label)
            col = row_cols.get(slug)
            if col is None:
                continue
            if meta_cols and slug not in meta_cols:
                continue
            targets.append((label, col))
    else:
        entity_slug = _entity_slug(_row_entity_field(meta) or "")
        slugs = meta_cols or [
            s for s in row_cols if s not in {entity_slug, "label", "entity"}
        ]
        for slug in slugs:
            if slug in skip_totals:
                continue
            col = row_cols.get(slug)
            if col is None:
                continue
            targets.append((_label_from_column_slug(slug, column_labels), col))

    for label, col in targets:
        value = _parse_metric_value(row.get(col))
        if value is None:
            continue
        out.append(Observado(index_key=index_key, label=label, period=period, value=value))
    return out


def _label_and_value(
    row: dict[str, Any],
    *,
    entity_field: str | None,
    value_field: str | None,
) -> tuple[str | None, float | None]:
    label: str | None = None
    if entity_field and row.get(entity_field) is not None:
        label = str(row[entity_field]).strip()
    if not label:
        for key in ("parcelas", "label", "tipo", "concessionaria", "entity"):
            if row.get(key) is not None:
                label = str(row[key]).strip()
                break
    raw_val: Any = None
    if value_field and value_field in row:
        raw_val = row[value_field]
    if raw_val is None:
        for key in ("valor", "value", "faturamento", "valor_comissao"):
            if key in row:
                raw_val = row[key]
                break
    value = _parse_metric_value(raw_val)
    return label, value


def parse_memory_json(
    path: Path | str,
    *,
    index_key: str,
    periods: tuple[str, ...] | list[str],
    scope_filters: tuple[tuple[str, str], ...] = (),
    operand_labels: tuple[str, ...] = (),
) -> MemoryParseResult:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict) and "hits" in raw:
        hits = raw["hits"]
    elif isinstance(raw, list):
        hits = raw
    else:
        raise ValueError(f"memory.json inválido: esperado list ou {{hits: [...]}} em {path}")

    wanted = set(periods)
    observados: list[Observado] = []
    truncated = False
    found_periods: set[str] = set()
    context_keys: list[str] = []
    emit_key = index_key

    for hit in hits:
        if not isinstance(hit, dict):
            continue
        context_key = str(hit.get("context_key") or "")
        period = period_from_context_key(context_key) or str(hit.get("period") or "")
        if wanted and period not in wanted:
            continue

        key_metrics = hit.get("key_metrics") or {}
        if not isinstance(key_metrics, dict):
            continue
        resolved = _resolve_entry(key_metrics, index_key)
        if resolved is None:
            continue
        _resolved_name, entry = resolved

        rows, meta = _rows_from_entry(entry)

        rows_raw = entry.get("rows") if isinstance(entry, dict) else None
        if (
            isinstance(rows_raw, list)
            and rows_raw
            and all(item == "…" for item in rows_raw)
            and not rows
        ):
            continue

        ranked_entity = str(meta.get("entity_field") or "") or None
        value_field = str(meta.get("value_field") or "") or None
        row_entity = _row_entity_field(meta)
        matrix_mode = _is_matrix_meta(meta)

        emitted_before = len(observados)
        for row in rows:
            if not _row_matches_scope(
                row,
                scope_filters,
                row_entity_field=row_entity,
            ):
                continue
            if matrix_mode:
                observados.extend(
                    _observados_from_matrix_row(
                        index_key=emit_key,
                        period=period,
                        row=row,
                        meta=meta,
                        operand_labels=operand_labels,
                    )
                )
                continue
            label, value = _label_and_value(
                row,
                entity_field=ranked_entity,
                value_field=value_field,
            )
            if not label or value is None:
                continue
            if operand_labels and not any(
                _normalize_text(label) == _normalize_text(op) for op in operand_labels
            ):
                continue
            observados.append(
                Observado(
                    index_key=emit_key,
                    label=label,
                    period=period,
                    value=value,
                )
            )

        if len(observados) == emitted_before:
            continue

        if meta.get("truncated_head_tail") is True:
            truncated = True
        context_keys.append(context_key)
        if period:
            found_periods.add(period)

    missing = tuple(sorted(wanted - found_periods)) if wanted else ()
    aggregated: dict[tuple[str, str, str], float] = {}
    for obs in observados:
        key = (obs.index_key, obs.label, obs.period)
        aggregated[key] = aggregated.get(key, 0.0) + obs.value
    merged = tuple(
        Observado(index_key=ik, label=label, period=period, value=value)
        for (ik, label, period), value in sorted(
            aggregated.items(),
            key=lambda item: (item[0][2], item[0][1]),
        )
    )
    return MemoryParseResult(
        observados=merged,
        truncated=truncated,
        missing_periods=missing,
        source_context_keys=tuple(dict.fromkeys(context_keys)),
    )
