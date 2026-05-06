"""NDJSON opcional: contexto do orquestrador antes da chamada ao LLM.

Variáveis:
  ORION_V2_AGENT_DEBUG_NDJSON_ENABLED — ``true`` para activar.
  ORION_V2_AGENT_DEBUG_LOG_PATH — ficheiro NDJSON (default: ``/tmp/orion_mcp_v2_agent_debug.ndjson``).
  Também activa se ``ORION_V2_LLM_IO_DUMP_ENABLED=true`` (mesmo critério que antes).

Em Docker, use o path default ou monte um volume no ``ORION_V2_AGENT_DEBUG_LOG_PATH``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _enabled() -> bool:
    def _truthy(name: str) -> bool:
        v = os.environ.get(name, "").strip().lower()
        return v in ("1", "true", "yes", "on")

    return _truthy("ORION_V2_AGENT_DEBUG_NDJSON_ENABLED") or _truthy("ORION_V2_LLM_IO_DUMP_ENABLED")


def _path() -> Path:
    raw = (os.environ.get("ORION_V2_AGENT_DEBUG_LOG_PATH") or "").strip()
    if raw:
        return Path(raw)
    return Path("/tmp/orion_mcp_v2_agent_debug.ndjson")


def agent_debug_ndjson(
    *,
    location: str,
    message: str,
    hypothesis_id: str,
    data: dict[str, Any],
) -> None:
    if not _enabled():
        return
    line = {
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    path = _path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass
