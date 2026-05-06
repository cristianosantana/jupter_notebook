"""
Registo de datasets de analytics por sessão (spill em disco + metadata).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.config import Settings, get_settings

_logger = logging.getLogger(__name__)

DATASET_FILE_VERSION = 1


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_key(session_id: UUID | None) -> str:
    if session_id is not None:
        return str(session_id)
    return "anonymous"


def _datasets_root(metadata: dict[str, Any]) -> dict[str, Any]:
    cur = metadata.get("analytics_datasets")
    if not isinstance(cur, dict):
        metadata["analytics_datasets"] = {
            "by_id": {},
            "order": [],
            "cache_key_to_dataset_id": {},
        }
        cur = metadata["analytics_datasets"]
    cur.setdefault("by_id", {})
    cur.setdefault("order", [])
    cur.setdefault("cache_key_to_dataset_id", {})
    return cur


def get_dataset_id_for_cache_key(metadata: dict[str, Any], cache_key: str) -> str | None:
    root = metadata.get("analytics_datasets")
    if not isinstance(root, dict):
        return None
    m = root.get("cache_key_to_dataset_id")
    if not isinstance(m, dict):
        return None
    did = m.get(cache_key)
    return str(did) if did else None


def increment_aggregate_calls(metadata: dict[str, Any], settings: Settings | None = None) -> bool:
    """Incrementa contador; devolve False se exceder o limite."""
    st = settings or get_settings()
    cap = max(1, int(st.analytics_aggregate_rate_limit_per_session))
    n = int(metadata.get("analytics_aggregate_calls") or 0)
    if n >= cap:
        return False
    metadata["analytics_aggregate_calls"] = n + 1
    return True


def load_dataset_for_aggregate(
    metadata: dict[str, Any],
    session_dataset_id: str,
    settings: Settings | None = None,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any]]:
    """
    Carrega linhas do spill. Devolve (None, {"error": ...}) em falha.
    """
    st = settings or get_settings()
    max_rows = max(100, int(st.analytics_aggregate_max_rows))
    root = metadata.get("analytics_datasets")
    if not isinstance(root, dict):
        return None, {"error": "analytics_datasets_ausente"}
    by_id = root.get("by_id")
    if not isinstance(by_id, dict):
        return None, {"error": "by_id_invalido"}
    info = by_id.get(session_dataset_id)
    if not isinstance(info, dict):
        return None, {"error": "session_dataset_id_desconhecido"}
    rel = info.get("relative_path")
    if not rel or not isinstance(rel, str):
        return None, {"error": "dataset_sem_ficheiro"}
    base = st.resolve_analytics_dataset_spill_dir()
    path = (base / rel).resolve()
    try:
        base_r = base.resolve()
        if not str(path).startswith(str(base_r)):
            return None, {"error": "path_invalido"}
    except OSError:
        return None, {"error": "path_invalido"}
    if not path.is_file():
        return None, {"error": "ficheiro_dataset_inexistente"}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        _logger.warning("analytics dataset read failed: %s", e)
        return None, {"error": "leitura_json_falhou"}
    if not isinstance(data, dict):
        return None, {"error": "formato_dataset_invalido"}
    rows = data.get("rows")
    if not isinstance(rows, list):
        return None, {"error": "rows_ausente"}
    if len(rows) > max_rows:
        return None, {"error": f"demasiadas_linhas_max_{max_rows}"}
    out: list[dict[str, Any]] = []
    for r in rows:
        if isinstance(r, dict):
            out.append(dict(r))
    meta = {
        "sample_only": bool(data.get("sample_only")),
        "query_id": str(data.get("query_id") or info.get("query_id") or ""),
        "columns": data.get("columns") if isinstance(data.get("columns"), list) else info.get("columns"),
    }
    return out, meta


def register_run_analytics_result(
    metadata: dict[str, Any],
    *,
    full_result_text: str,
    args: dict[str, Any],
    cache_key: str,
    session_id: UUID | None,
    settings: Settings | None = None,
) -> str | None:
    """
    Regista dataset completo (texto MCP ainda não truncado pelo cache).
    Devolve session_dataset_id ou None.
    """
    st = settings or get_settings()
    if not st.analytics_session_datasets_enabled:
        return None
    if "[truncado mcp_cache_entry_max_chars]" in full_result_text:
        return None
    try:
        data = json.loads(full_result_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("error"):
        return None

    query_id = str(data.get("query_id") or args.get("query_id") or "")
    rows = data.get("rows")
    rows_sample = data.get("rows_sample")
    sample_only = False
    tabular: list[dict[str, Any]] | None = None
    if isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows):
        tabular = [dict(r) for r in rows]
    elif isinstance(rows_sample, list) and rows_sample and all(
        isinstance(r, dict) for r in rows_sample
    ):
        tabular = [dict(r) for r in rows_sample]
        sample_only = True
    else:
        return None

    rc = data.get("row_count")
    try:
        row_count = int(rc) if rc is not None else len(tabular)
    except (TypeError, ValueError):
        row_count = len(tabular)

    cols = data.get("columns")
    if isinstance(cols, list):
        columns = [str(c) for c in cols]
    elif tabular:
        columns = list(tabular[0].keys())
    else:
        columns = []

    root = _datasets_root(metadata)
    by_id: dict[str, Any] = root["by_id"]
    order: list[str] = root["order"]
    ck_map: dict[str, str] = root["cache_key_to_dataset_id"]

    existing = ck_map.get(cache_key)
    if existing and existing in by_id:
        dataset_id = existing
    else:
        dataset_id = uuid.uuid4().hex[:12]

    spill_dir = st.resolve_analytics_dataset_spill_dir()
    spill_dir.mkdir(parents=True, exist_ok=True)
    sk = _session_key(session_id)
    rel_name = f"{sk}_{dataset_id}.json"
    path = spill_dir / rel_name

    payload = {
        "version": DATASET_FILE_VERSION,
        "query_id": query_id,
        "columns": columns,
        "rows": tabular,
        "sample_only": sample_only,
        "row_count": row_count,
        "args": {
            k: args.get(k)
            for k in ("date_from", "date_to", "summarize", "limit", "offset", "query_id")
            if k in args
        },
        "written_at": _utc_iso(),
    }
    try:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    except OSError as e:
        _logger.error("analytics dataset spill failed: %s", e)
        return None

    info = {
        "session_dataset_id": dataset_id,
        "query_id": query_id,
        "row_count": row_count,
        "columns": columns,
        "cache_key": cache_key,
        "storage": "spill",
        "relative_path": rel_name,
        "sample_only": sample_only,
        "created_at": _utc_iso(),
    }
    by_id[dataset_id] = info
    ck_map[cache_key] = dataset_id
    if dataset_id not in order:
        order.append(dataset_id)
    max_keep = max(4, int(st.analytics_datasets_max_registered))
    while len(order) > max_keep:
        old = order.pop(0)
        old_info = by_id.pop(old, None)
        if old_info and isinstance(old_info, dict):
            old_ck = old_info.get("cache_key")
            if old_ck and ck_map.get(old_ck) == old:
                del ck_map[old_ck]
            rel = old_info.get("relative_path")
            if isinstance(rel, str):
                try:
                    p = (spill_dir / rel).resolve()
                    if str(p).startswith(str(spill_dir.resolve())) and p.is_file():
                        p.unlink()
                except OSError:
                    pass

    _logger.info(
        "dataset_registered id=%s query_id=%s rows=%s sample_only=%s",
        dataset_id,
        query_id,
        row_count,
        sample_only,
    )
    return dataset_id


def inject_dataset_handles_into_json_text(
    text: str,
    *,
    session_dataset_id: str,
    sample_only: bool,
) -> str:
    """Acrescenta session_dataset_id ao objecto JSON devolvido pela tool."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text
    if not isinstance(data, dict):
        return text
    data["session_dataset_id"] = session_dataset_id
    data["dataset_handling_note"] = (
        "Usa a tool host analytics_aggregate_session com este session_dataset_id para "
        "agregações (Top N, somas, médias). O digest não contém todas as linhas."
    )
    data["dataset_sample_only"] = sample_only
    return json.dumps(data, ensure_ascii=False, default=str)
