"""Grava pedidos LLM em ficheiros JSON sob `logs/` (ou directório configurável)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_chat_completion_messages(
    *, system_prompt: str | None, user_text: str
) -> list[dict[str, str]]:
    """Replica a lista `messages` enviada pelo `OpenAILLMProvider` ao chat completions."""
    messages: list[dict[str, str]] = []
    sys = (system_prompt or "").strip()
    if sys:
        messages.append({"role": "system", "content": sys})
    messages.append({"role": "user", "content": user_text})
    return messages


def write_llm_debug_json(
    log_dir: str,
    *,
    kind: str,
    transport: str,
    session_id: str,
    halted: bool,
    openai_request: dict[str, Any],
    extra: dict[str, Any] | None = None,
) -> str:
    """
    Cria `log_dir` se necessário e grava um ficheiro único por invocação.
    Devolve o caminho absoluto do ficheiro criado.
    """
    base = Path(log_dir).expanduser()
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
    uid = uuid.uuid4().hex[:12]
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in kind)[:48]
    path = base / f"{safe}_{ts}_{uid}.json"
    doc: dict[str, Any] = {
        "schema": "orion_llm_debug/v1",
        "kind": kind,
        "transport": transport,
        "session_id": session_id,
        "halted": halted,
        "openai_request": openai_request,
    }
    if extra:
        doc["extra"] = extra
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path.resolve())
