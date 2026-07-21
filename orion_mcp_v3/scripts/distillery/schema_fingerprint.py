"""Fingerprint estrutural de key_metrics — detecta drift entre destilações."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)


def _default_fingerprints_path() -> Path:
    return Path(
        os.environ.get(
            "ORION_KEY_METRICS_SCHEMA_FINGERPRINTS",
            str(Path(__file__).resolve().parent / ".schema_fingerprints.json"),
        )
    )


def fingerprint_key_metrics(key_metrics: Mapping[str, Any]) -> str:
    """
    Forma estrutural estável: schema + campos de linha (não os valores).

    Ex.: ``comissao_...:table:rows:concessionaria,financiamento,venda_normal``
    """
    parts: list[str] = []
    for key in sorted(key_metrics.keys()):
        if key.startswith("_") and key != "_meta":
            continue
        raw = key_metrics[key]
        parts.append(f"{key}:{_shape_token(raw)}")
    if not parts and "_meta" in key_metrics:
        parts.append(f"root:{_shape_token(dict(key_metrics))}")
    return "|".join(parts) if parts else "empty"


def _shape_token(raw: Any) -> str:
    if isinstance(raw, dict):
        if "_meta" in raw or "rows" in raw or "table_rows_sample" in raw:
            meta = raw.get("_meta") if isinstance(raw.get("_meta"), dict) else {}
            schema = str(meta.get("schema") or ("table" if "table_rows_sample" in raw else "ranked_list"))
            if isinstance(raw.get("rows"), list) and raw["rows"]:
                cols = _column_set(raw["rows"])
                return f"{schema}:rows:{cols}"
            if isinstance(raw.get("table_rows_sample"), list):
                return f"{schema}:table_rows_sample"
            return f"{schema}:empty"
        # mapa plano: tipo do primeiro valor
        values = [v for k, v in raw.items() if not str(k).startswith("_")]
        if not values:
            return "flat:empty"
        sample = values[0]
        if isinstance(sample, dict):
            return f"flat:dict:{_column_set([sample])}"
        if isinstance(sample, str):
            return "flat:str"
        return f"flat:{type(sample).__name__}"
    if isinstance(raw, list):
        if not raw:
            return "list:empty"
        if isinstance(raw[0], dict):
            return f"list:dict:{_column_set(raw)}"
        return f"list:{type(raw[0]).__name__}"
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return "scalar"
    if isinstance(raw, str):
        return "str"
    return type(raw).__name__


def _column_set(rows: list[Any]) -> str:
    cols: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            cols.update(str(k) for k in row.keys() if not str(k).startswith("_"))
    return ",".join(sorted(cols))


class SchemaFingerprintStore:
    """Persiste o último fingerprint por (theme, dimension) e alerta em drift."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else _default_fingerprints_path()
        self._cache: dict[str, str] | None = None

    def check_and_update(
        self,
        *,
        theme: str,
        dimension: str | None,
        key_metrics: Mapping[str, Any],
    ) -> str:
        fp = fingerprint_key_metrics(key_metrics)
        key = f"{theme.strip().lower()}::{(dimension or '').strip().lower()}"
        previous = self._data().get(key)
        if previous and previous != fp:
            logger.warning(
                "schema drift em key_metrics: theme=%s dimension=%s prev=%s new=%s",
                theme,
                dimension,
                previous,
                fp,
            )
        self._data()[key] = fp
        self._persist()
        return fp

    def _data(self) -> dict[str, str]:
        if self._cache is None:
            self._cache = self._load()
        return self._cache

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("nao foi possivel ler fingerprints %s: %s", self.path, exc)
            return {}
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items()}

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("nao foi possivel gravar fingerprints %s: %s", self.path, exc)


_STORE: SchemaFingerprintStore | None = None


def default_fingerprint_store() -> SchemaFingerprintStore:
    global _STORE
    if _STORE is None:
        _STORE = SchemaFingerprintStore()
    return _STORE
