"""Converte memory.json (ranked_list completo) → observados para o .pl."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PERIOD_RE = re.compile(r"periodo[_-](\d{4}-\d{2})", re.IGNORECASE)


def _ensure_src_on_path() -> None:
    here = Path(__file__).resolve()
    # scripts/senna_replica → repo root → src
    repo_root = here.parents[2]
    src = repo_root / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _parse_metric_value(raw: Any) -> float | None:
    _ensure_src_on_path()
    try:
        from orion_mcp_v3.public_chat.domain.key_metrics_reader import parse_metric_value

        parsed = parse_metric_value(raw)
        if parsed is not None:
            return parsed
    except Exception:
        pass

    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    # "R$ 33.828,00 (10,95%)" → pega o primeiro valor monetário
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


def _rows_from_entry(entry: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(entry, dict):
        return [], {}
    meta = entry.get("_meta") if isinstance(entry.get("_meta"), dict) else {}
    rows = entry.get("rows") or entry.get("items") or []
    if not isinstance(rows, list):
        return [], meta
    return [r for r in rows if isinstance(r, dict)], meta


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
        entry = key_metrics.get(index_key)
        if entry is None:
            continue

        rows, meta = _rows_from_entry(entry)
        if meta.get("truncated_head_tail") is True:
            truncated = True

        rows_raw = entry.get("rows")
        # Log do pipeline redige rows como lista de "…" (sem dicts).
        if (
            isinstance(rows_raw, list)
            and rows_raw
            and all(item == "…" for item in rows_raw)
        ):
            continue

        entity_field = str(meta.get("entity_field") or "") or None
        value_field = str(meta.get("value_field") or "") or None

        context_keys.append(context_key)
        if period:
            found_periods.add(period)

        for row in rows:
            label, value = _label_and_value(
                row, entity_field=entity_field, value_field=value_field
            )
            if not label or value is None:
                continue
            observados.append(
                Observado(
                    index_key=index_key,
                    label=label,
                    period=period,
                    value=value,
                )
            )

    missing = tuple(sorted(wanted - found_periods)) if wanted else ()
    return MemoryParseResult(
        observados=tuple(observados),
        truncated=truncated,
        missing_periods=missing,
        source_context_keys=tuple(dict.fromkeys(context_keys)),
    )
