"""JSONL de trace no processo MCP (sem dependência da app).

Cada linha vai para ``AGENT_TRACE_DIR / YYYYMMDD / <hora local> / {run_id}_server.jsonl``,
ex.: ``.../20260315/8/`` ou ``.../20260315/13/`` (hora 0–23 no fuso do sistema, sem zero à esquerda).

A hora e o campo ``ts`` usam o **relógio local** (``TZ`` / timezone do SO), não UTC.

Truncagem: variável de ambiente ``AGENT_TRACE_MAX_FIELD_CHARS`` (definida pela app no arranque).
Se ausente, usa 600_000. Se **0 ou negativo**, não trunca strings (análise completa).
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

_lock = threading.Lock()
_DEFAULT_MAX = 600_000


def _max_field_chars() -> int:
    raw = os.environ.get("AGENT_TRACE_MAX_FIELD_CHARS", "").strip()
    if not raw:
        return _DEFAULT_MAX
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_MAX


def _now_local() -> datetime:
    """UTC converted to local wall time (respects system timezone)."""
    return datetime.now(timezone.utc).astimezone()


def _date_hour_dirs_local() -> tuple[str, str]:
    now = _now_local()
    day = now.strftime("%Y%m%d")
    hour = str(now.hour)
    return day, hour


def _truncate(s: str) -> str:
    m = _max_field_chars()
    if m <= 0:
        return s
    if len(s) <= m:
        return s
    return s[:m] + f"\n… [truncado {len(s)}→{m}]"


def _sanitize(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        return _truncate(v)
    if isinstance(v, dict):
        return {str(k): _sanitize(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_sanitize(x) for x in v]
    if hasattr(v, "model_dump"):
        try:
            return _sanitize(v.model_dump(mode="json"))
        except Exception:
            return _truncate(repr(v))
    return _truncate(str(v))


def trace_record(event: str, *, run_id: str | None = None, **fields: Any) -> None:
    base = os.environ.get("AGENT_TRACE_DIR", "").strip()
    if not base:
        return
    rid = run_id or "no_run_id"
    day, hour = _date_hour_dirs_local()
    log_dir = os.path.join(base, day, hour)
    path = os.path.join(log_dir, f"{rid}_server.jsonl")
    row: dict[str, Any] = {
        "ts": _now_local().isoformat(),
        "run_id": rid,
        "event": event,
    }
    for k, v in fields.items():
        row[k] = _sanitize(v)
    line = json.dumps(row, ensure_ascii=False, default=str)
    os.makedirs(log_dir, exist_ok=True)
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def meta_run_id(meta: Any) -> str | None:
    if meta is None:
        return None
    rid = getattr(meta, "agent_trace_run_id", None)
    if rid:
        return str(rid)
    try:
        d = meta.model_dump(mode="json") if hasattr(meta, "model_dump") else {}
    except Exception:
        d = {}
    if isinstance(d, dict) and d.get("agent_trace_run_id"):
        return str(d["agent_trace_run_id"])
    extra = getattr(meta, "model_extra", None) or {}
    if isinstance(extra, dict) and extra.get("agent_trace_run_id"):
        return str(extra["agent_trace_run_id"])
    return None
