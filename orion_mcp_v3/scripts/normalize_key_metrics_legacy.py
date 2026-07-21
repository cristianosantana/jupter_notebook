#!/usr/bin/env python3
"""
Normalização ad-hoc de key_metrics divergentes (Camada E).

Uso preferível: re-rodar distill_supervised_memory.py nos períodos afetados.
Este script só entra quando as janelas originais não existem mais.

Reconhece formatos observados para dimensões matriciais:
  1. table_rows_sample canônico (já ok)
  2. string composta "Label: R$X | Label: R$Y"
  3. lista posicional sem nomes de campo
  4. repr Python de dict embutido: "ENTIDADE | {'campo': 'R$ ...'}"

Uso:
  python3 scripts/normalize_key_metrics_legacy.py --dry-run input.json
  python3 scripts/normalize_key_metrics_legacy.py --write input.json
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from distillery.field_parsers import format_composite_metric_value  # noqa: E402
from orion_mcp_v3.public_chat.domain.key_metrics_contract import (  # noqa: E402
    enrich_key_metrics,
)

_PYTHON_DICT_RE = re.compile(r"\{\s*'[^']+'\s*:")


def _try_parse_python_dict(text: str) -> dict[str, Any] | None:
    """Converte repr Python ``{'a': 'b'}`` em dict; None se não for o caso."""
    stripped = text.strip()
    if not (stripped.startswith("{") and _PYTHON_DICT_RE.search(stripped)):
        return None
    try:
        value = ast.literal_eval(stripped)
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def normalize_table_line(line: str) -> str:
    """
    Corrige linha ``ENTIDADE | {'campo': 'valor', ...}`` → serialização canônica.
    """
    if " | " not in line:
        nested = _try_parse_python_dict(line)
        if nested is not None:
            return format_composite_metric_value(
                {str(k): v for k, v in nested.items()}
            )
        return line

    entity, _, rest = line.partition(" | ")
    nested = _try_parse_python_dict(rest)
    if nested is None:
        return line
    formatted = format_composite_metric_value({str(k): v for k, v in nested.items()})
    return f"{entity.strip()} | {formatted}"


def normalize_key_metrics_blob(
    key_metrics: dict[str, Any],
    *,
    metric_kind: str | None = None,
    dimension: str | None = None,
    theme: str | None = None,
) -> dict[str, Any]:
    """Normaliza um blob key_metrics já persistido."""
    cleaned: dict[str, Any] = {}
    for key, raw in key_metrics.items():
        if isinstance(raw, dict) and "table_rows_sample" in raw:
            sample = raw.get("table_rows_sample")
            if isinstance(sample, list):
                fixed = [
                    normalize_table_line(item) if isinstance(item, str) else item
                    for item in sample
                ]
                cleaned[key] = {**raw, "table_rows_sample": fixed}
                continue
        if isinstance(raw, str) and " | " in raw and _PYTHON_DICT_RE.search(raw):
            cleaned[key] = normalize_table_line(raw)
            continue
        if isinstance(raw, dict) and any(isinstance(v, dict) for v in raw.values()):
            cleaned[key] = {
                k: (
                    format_composite_metric_value(v)
                    if isinstance(v, dict)
                    else v
                )
                for k, v in raw.items()
            }
            continue
        cleaned[key] = raw

    return enrich_key_metrics(
        cleaned,
        metric_kind=metric_kind,
        dimension=dimension,
        theme=theme,
    )


def _diagnose(key_metrics: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    blob = json.dumps(key_metrics, ensure_ascii=False)
    if "{'" in blob or '{\"' not in blob and "': " in blob and "{" in blob:
        if _PYTHON_DICT_RE.search(blob):
            issues.append("python_dict_repr")
    for key, raw in key_metrics.items():
        if isinstance(raw, dict):
            if any(isinstance(v, dict) for k, v in raw.items() if k != "_meta"):
                issues.append(f"{key}:nested_dict_values")
            sample = raw.get("table_rows_sample")
            if isinstance(sample, list):
                for line in sample:
                    if isinstance(line, str) and _PYTHON_DICT_RE.search(line):
                        issues.append(f"{key}:table_sample_python_repr")
                        break
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSON com key_metrics ou lista de entries")
    parser.add_argument("--write", action="store_true", help="Sobrescreve o arquivo de entrada")
    parser.add_argument("--dry-run", action="store_true", help="Só diagnostica / imprime resultado")
    parser.add_argument("--theme", default=None)
    parser.add_argument("--dimension", default=None)
    parser.add_argument("--metric-kind", default=None)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "key_metrics" in payload:
        entries = [payload]
    elif isinstance(payload, list):
        entries = payload
    else:
        entries = [{"key_metrics": payload}]

    out: list[dict[str, Any]] = []
    for entry in entries:
        km = entry.get("key_metrics") if isinstance(entry, dict) else None
        if not isinstance(km, dict):
            out.append(entry)
            continue
        issues = _diagnose(km)
        fixed = normalize_key_metrics_blob(
            km,
            metric_kind=args.metric_kind or entry.get("metric_kind"),
            dimension=args.dimension or entry.get("dimension"),
            theme=args.theme or entry.get("theme"),
        )
        print(f"issues={issues or ['none']} → keys={list(fixed.keys())}", file=sys.stderr)
        updated = dict(entry)
        updated["key_metrics"] = fixed
        out.append(updated)

    text = json.dumps(out if isinstance(payload, list) else out[0], ensure_ascii=False, indent=2)
    if args.write and not args.dry_run:
        args.input.write_text(text + "\n", encoding="utf-8")
        print(f"escrito: {args.input}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
