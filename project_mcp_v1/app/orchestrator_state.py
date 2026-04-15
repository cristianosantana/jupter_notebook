"""Estado persistido em ``metadata['orchestrator_state']`` — resultados de tools por chave estável (mcp_cache_key)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import Settings, get_settings
from app.mcp_session_cache import mcp_cache_key

_logger = logging.getLogger(__name__)

ORCHESTRATOR_STATE_KEY = "orchestrator_state"
STATE_VERSION = 1


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_orchestrator_state_block(metadata: dict[str, Any]) -> dict[str, Any]:
    """Garante bloco mutável ``orchestrator_state`` com ``tool_results``."""
    block = metadata.get(ORCHESTRATOR_STATE_KEY)
    if not isinstance(block, dict):
        block = {"v": STATE_VERSION, "tool_results": {}}
        metadata[ORCHESTRATOR_STATE_KEY] = block
    block.setdefault("v", STATE_VERSION)
    tr = block.get("tool_results")
    if not isinstance(tr, dict):
        block["tool_results"] = {}
    return block


def ephemeral_tool_results() -> dict[str, Any]:
    """Estado in-memory por turno quando não há ``session_metadata``."""
    return {"v": STATE_VERSION, "tool_results": {}}


def find_tool_result_text(
    store: dict[str, Any] | None,
    tool_name: str,
    args: dict[str, Any],
) -> tuple[str, bool] | None:
    """Devolve ``(texto, is_error)`` se existir entrada para tool+args."""
    if not store or not isinstance(store, dict):
        return None
    tr = store.get("tool_results")
    if not isinstance(tr, dict):
        return None
    key = mcp_cache_key(tool_name, args)
    ent = tr.get(key)
    if not isinstance(ent, dict):
        return None
    text = ent.get("content")
    if not isinstance(text, str) or not text:
        return None
    return (text, bool(ent.get("is_error")))


def put_tool_result(
    store: dict[str, Any],
    tool_name: str,
    args: dict[str, Any],
    content: str,
    *,
    is_error: bool,
    settings: Settings | None = None,
) -> None:
    st = settings or get_settings()
    cap = max(1024, int(getattr(st, "mcp_cache_entry_max_chars", 65536)))
    text = content if len(content) <= cap else content[:cap] + "\n…[truncado]"
    tr = store.setdefault("tool_results", {})
    if not isinstance(tr, dict):
        store["tool_results"] = {}
        tr = store["tool_results"]
    key = mcp_cache_key(tool_name, args)
    tr[key] = {
        "tool_name": tool_name,
        "is_error": is_error,
        "content": text,
        "stored_at": _utc_iso(),
    }
    _logger.debug(
        "orchestrator_state stored tool=%s key_prefix=%s",
        tool_name,
        key[:16],
    )


def tool_excluded_from_state_store(tool_name: str) -> bool:
    from app.routing_tools import ROUTE_TO_SPECIALIST_TOOL_NAME

    return tool_name == ROUTE_TO_SPECIALIST_TOOL_NAME


def build_tool_registry_context_markdown(store: dict[str, Any], *, max_lines: int = 24) -> str:
    """
    Resumo legível dos resultados já guardados no estado (para o LLM).
    Não inclui o corpo completo de cada tool — só nomes e prefixo de chave.
    """
    if not store or not isinstance(store, dict):
        return ""
    tr = store.get("tool_results")
    if not isinstance(tr, dict) or not tr:
        return ""
    lines: list[str] = ["### Ferramentas já executadas nesta sessão (estado do host)", ""]
    n = 0
    for _key, ent in tr.items():
        if not isinstance(ent, dict):
            continue
        tn = str(ent.get("tool_name") or "?")
        err = bool(ent.get("is_error"))
        prev = ent.get("content")
        snippet = ""
        if isinstance(prev, str) and prev.strip():
            one = prev.strip().replace("\n", " ")[:160]
            snippet = f" — pré-visualização: {one}"
        lines.append(f"- **{tn}**{' (erro)' if err else ''}{snippet}")
        n += 1
        if n >= max_lines:
            lines.append(f"- … (+{len(tr) - max_lines} entradas)")
            break
    lines.append("")
    lines.append("Reutiliza estes resultados; não peças a mesma ferramenta com os mesmos argumentos.")
    return "\n".join(lines)
