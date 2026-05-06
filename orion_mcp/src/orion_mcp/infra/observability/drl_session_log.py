"""Append-only NDJSON por sessão para depuração manual da pipeline DRL."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MAX_PAYLOAD_JSON_CHARS = 48_000


def _default_log_dir() -> Path:
    raw = (os.environ.get("ORION_LLM_DEBUG_LOG_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path(__file__).resolve().parents[4] / "logs"


def safe_session_id(session_id: str | None) -> str:
    s = (session_id or "").strip() or "anonymous"
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in s)[:64]


def append_drl_step(
    step: str,
    payload: dict[str, Any],
    *,
    session_id: str | None = None,
    log_dir: str | Path | None = None,
) -> Path | None:
    """
    Acrescenta uma linha JSON ao ficheiro ``drl_session_<sid>.ndjson`` sob o directório de logs.
    Falhas de I/O são silenciosas (não quebram a tool).
    """
    try:
        base = Path(log_dir).expanduser() if log_dir else _default_log_dir()
        base.mkdir(parents=True, exist_ok=True)
        sid = safe_session_id(session_id)
        path = base / f"drl_session_{sid}.ndjson"
        raw_json = json.dumps(payload, ensure_ascii=False, default=str)
        if len(raw_json) > _MAX_PAYLOAD_JSON_CHARS:
            record: dict[str, Any] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "step": step,
                "session_id": session_id or None,
                "payload_note": f"payload truncado no log; original ~{len(raw_json)} chars",
                "payload_head": raw_json[:4000],
            }
        else:
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "step": step,
                "session_id": session_id or None,
                "payload": payload,
            }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return path
    except OSError:
        return None
