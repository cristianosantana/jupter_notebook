"""Trace estruturado do pipeline do Chat Público (início ao fim do turno)."""

from __future__ import annotations

import contextvars
import json
import logging
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from orion_mcp_v3.public_chat.config.settings import PublicChatSettings

_LOG = logging.getLogger("orion.public_chat.pipeline")

_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "public_chat_trace_id",
    default=None,
)

_JSONL_HANDLER: logging.Handler | None = None
_JSONL_PATH: Path | None = None
_JSONL_PENDING_PATH: Path | None = None

_MAX_STR = 400


def configure_public_chat_file_logging(settings: PublicChatSettings) -> Path | None:
    """
    Grava eventos em JSONL (uma linha = um JSON) em
    ``<pipeline_log_dir>/public_chat_pipeline_<UTC>.jsonl``.

    Com trace activo, o logger **não propaga** para o terminal (``propagate=False``).
    """
    global _JSONL_HANDLER, _JSONL_PATH, _JSONL_PENDING_PATH

    shutdown_public_chat_file_logging()

    if not settings.pipeline_trace:
        return None
    raw = (settings.pipeline_log_dir or "").strip()
    if not raw:
        return None

    base = Path(raw)
    if not base.is_absolute():
        base = Path.cwd() / base
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = base / f"public_chat_pipeline_{stamp}.jsonl"

    _LOG.setLevel(logging.INFO)
    _LOG.propagate = False
    _JSONL_HANDLER = None
    _JSONL_PATH = None
    _JSONL_PENDING_PATH = path.resolve()
    return _JSONL_PENDING_PATH


def current_log_file_path() -> Path | None:
    return _JSONL_PATH or _JSONL_PENDING_PATH


def _ensure_file_handler() -> None:
    global _JSONL_HANDLER, _JSONL_PATH, _JSONL_PENDING_PATH

    if _JSONL_HANDLER is not None or _JSONL_PENDING_PATH is None:
        return
    handler = logging.FileHandler(_JSONL_PENDING_PATH, mode="a", encoding="utf-8")
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOG.addHandler(handler)
    _JSONL_HANDLER = handler
    _JSONL_PATH = _JSONL_PENDING_PATH


def shutdown_public_chat_file_logging() -> None:
    global _JSONL_HANDLER, _JSONL_PATH, _JSONL_PENDING_PATH

    _JSONL_PENDING_PATH = None
    _LOG.propagate = True
    if _JSONL_HANDLER is None:
        _JSONL_PATH = None
        return
    try:
        _LOG.removeHandler(_JSONL_HANDLER)
    except ValueError:
        pass
    try:
        _JSONL_HANDLER.flush()
        _JSONL_HANDLER.close()
    except Exception:
        pass
    _JSONL_HANDLER = None
    _JSONL_PATH = None


def begin_turn_trace() -> str:
    """Inicia correlação de um turno (tipicamente no handler HTTP)."""
    trace_id = str(uuid4())
    _trace_id.set(trace_id)
    return trace_id


def current_turn_trace() -> str | None:
    return _trace_id.get()


def _truncate(value: str, *, max_len: int = _MAX_STR) -> str:
    text = value.replace("\n", " ").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _json_safe(obj: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "…"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return _truncate(obj)
    if isinstance(obj, Mapping):
        return {str(k): _json_safe(v, depth + 1) for k, v in list(obj.items())[:50]}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(item, depth + 1) for item in obj[:50]]
    return _truncate(str(obj), max_len=200)


def log_public_chat_event(
    *,
    etapa: str,
    fase: str,
    dados: Mapping[str, Any] | None = None,
    trace_id: str | None = None,
) -> None:
    """Emite um evento JSON numa linha. ``fase`` ∈ {pre, post, error}."""
    if _JSONL_PENDING_PATH is None and _JSONL_HANDLER is None:
        return

    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "canal": "public_chat_pipeline",
        "etapa": etapa,
        "fase": fase,
        "timestamp_utc": now.isoformat(),
        "timestamp_ms": int(time.time() * 1000),
    }
    resolved_trace = trace_id or current_turn_trace()
    if resolved_trace:
        payload["trace_id"] = resolved_trace
    if dados:
        payload["dados"] = _json_safe(dict(dados))
    _ensure_file_handler()
    _LOG.info("%s", json.dumps(payload, ensure_ascii=False, default=str))


def preview_message(message: str) -> dict[str, Any]:
    return {"message_preview": _truncate(message), "message_chars": len(message)}
