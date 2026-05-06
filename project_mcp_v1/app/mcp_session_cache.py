"""
Cache de tools MCP por sessão (metadata.mcp_tool_cache) e digest para o system.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.config import Settings, get_settings

ENTITY_GLOSSARY_TOOL = "get_entity_glossary_markdown"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_mcp_arguments(args: dict[str, Any] | None) -> dict[str, Any]:
    if not args:
        return {}
    out: dict[str, Any] = {}
    for k in sorted(args.keys()):
        v = args[k]
        if v is None:
            continue
        if isinstance(v, dict):
            nested = normalize_mcp_arguments(v)
            if nested:
                out[k] = nested
        elif isinstance(v, list):
            out[k] = [_normalize_list_item(x) for x in v]
        else:
            out[k] = v
    return out


def _normalize_list_item(x: Any) -> Any:
    if isinstance(x, dict):
        return normalize_mcp_arguments(x)
    if isinstance(x, list):
        return [_normalize_list_item(y) for y in x]
    return x


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def mcp_cache_key(tool_name: str, args: dict[str, Any] | None) -> str:
    norm = normalize_mcp_arguments(args or {})
    payload = f"{tool_name}\n{canonical_json(norm)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def find_cache_entry(
    metadata: dict[str, Any],
    cache_key: str,
) -> dict[str, Any] | None:
    block = metadata.get("mcp_tool_cache") or {}
    entries = block.get("entries") or []
    for e in entries:
        if e.get("cache_key") == cache_key:
            return e
    return None


def append_cache_entry(
    metadata: dict[str, Any],
    *,
    cache_key: str,
    tool_name: str,
    args: dict[str, Any],
    result_text: str,
    settings: Settings | None = None,
) -> None:
    st = settings or get_settings()
    cap = max(1024, int(st.mcp_cache_entry_max_chars))
    text = (
        result_text
        if len(result_text) <= cap
        else (result_text[:cap] + "\n\n[truncado mcp_cache_entry_max_chars]")
    )
    block = metadata.setdefault("mcp_tool_cache", {})
    lst = block.setdefault("entries", [])
    row_count: int | None = None
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            if data.get("row_count") is not None:
                try:
                    row_count = int(data["row_count"])
                except (TypeError, ValueError):
                    row_count = None
            if row_count is None and "rows" in data and isinstance(data["rows"], list):
                row_count = len(data["rows"])
            if row_count is None and "queries" in data and isinstance(data["queries"], list):
                row_count = len(data["queries"])
            if row_count is None and "rows_sample" in data and isinstance(
                data["rows_sample"], list
            ):
                row_count = len(data["rows_sample"])
    except (json.JSONDecodeError, TypeError):
        pass
    lst.append(
        {
            "cache_key": cache_key,
            "tool_name": tool_name,
            "args": args,
            "executed_at": _utc_iso(),
            "result_stored": "full" if len(result_text) <= cap else "truncated",
            "result_text": text,
            "row_count": row_count,
        }
    )


def _truncate(s: str, max_len: int) -> str:
    s = s.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _digest_one_entry(
    e: dict[str, Any],
    max_per: int,
) -> list[str]:
    tn = str(e.get("tool_name") or "?")
    args = e.get("args") or {}
    raw = str(e.get("result_text") or "")
    lines: list[str] = []
    args_s = canonical_json(args)
    if len(args_s) > 220:
        args_s = args_s[:220] + "…"
    rc = e.get("row_count")
    rc_bit = f" · linhas≈{rc}" if rc is not None else ""

    if tn == "run_analytics_query":
        cols_list: list[str] | None = None
        rc_meta: int | None = None
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                rc_meta = data.get("row_count")
                if isinstance(rc_meta, int):
                    pass
                elif rc_meta is not None:
                    try:
                        rc_meta = int(rc_meta)
                    except (TypeError, ValueError):
                        rc_meta = None
                c = data.get("columns")
                if isinstance(c, list):
                    cols_list = [str(x) for x in c]
                elif isinstance(data.get("rows"), list) and data["rows"]:
                    cols_list = list(data["rows"][0].keys()) if isinstance(data["rows"][0], dict) else None
                elif isinstance(data.get("rows_sample"), list) and data["rows_sample"]:
                    cols_list = (
                        list(data["rows_sample"][0].keys())
                        if isinstance(data["rows_sample"][0], dict)
                        else None
                    )
        except (json.JSONDecodeError, TypeError):
            pass
        lines.append(f"### {tn}{rc_bit}")
        lines.append(f"- args: `{args_s}`")
        if rc_meta is not None:
            lines.append(f"- **row_count:** {rc_meta}")
        if cols_list is not None:
            cols_short = cols_list[:24]
            extra = f" (+{len(cols_list) - 24} mais)" if len(cols_list) > 24 else ""
            lines.append(f"- **colunas:** {', '.join(cols_short)}{extra}")
        ck = e.get("cache_key")
        if isinstance(ck, str) and ck.strip():
            lines.append(f"- **cache:** reutiliza com os mesmos args normalizados · `cache_key`≈`{ck[:20]}…`")
        lines.append(
            "- **Totais / rankings exactos:** última mensagem `tool` com JSON completo ou "
            "`analytics_aggregate_session` + `session_dataset_id` (não uses só este digest)."
        )
        lines.append(
            "- **Histórico semântico:** com PostgreSQL + `session_id`, tool **`context_retrieve_similar`** "
            "(pré-filtro lexical ILIKE + embeddings em runtime; não substitui analytics)."
        )
    elif tn == "list_analytics_queries":
        lines.append(f"### {tn}{rc_bit}")
        lines.append(f"- args: `{args_s}`")
        lines.append(f"- prévia: {_truncate(raw, max_per)}")
    elif tn == ENTITY_GLOSSARY_TOOL:
        lines.append(f"### {tn}{rc_bit}")
        lines.append(f"- args: `{args_s}`")
        lines.append(f"- prévia (markdown truncado): {_truncate(raw, max_per)}")
    else:
        lines.append(f"### {tn}{rc_bit}")
        lines.append(f"- args: `{args_s}`")
        lines.append(f"- prévia: {_truncate(raw, max_per)}")
    return lines


def _digest_semantic_block(semantic_retrieval_markdown: str | None, max_chars: int) -> str:
    if not semantic_retrieval_markdown or not str(semantic_retrieval_markdown).strip():
        return ""
    body = (
        "## Contexto semântico recuperado (host)\n\n"
        "Bloco injectado automaticamente via `context_retrieve_similar` quando PostgreSQL + "
        "`session_id` estão activos. Não substitui métricas de analytics nem o JSON completo "
        "das tools.\n\n"
        + str(semantic_retrieval_markdown).strip()
    )
    if len(body) > max_chars:
        return body[:max_chars] + "\n\n[contexto semântico truncado]"
    return body


def _build_analytics_datasets_digest(metadata: dict[str, Any]) -> str:
    block = metadata.get("analytics_datasets")
    if not isinstance(block, dict):
        return ""
    by_id = block.get("by_id")
    order = block.get("order")
    if not isinstance(by_id, dict) or not by_id:
        return ""
    lines = [
        "## Datasets de analytics nesta sessão (handles)",
        "",
        "Agrega com **`analytics_aggregate_session`**; não peças estes ids ao utilizador.",
        "",
    ]
    ids = list(order) if isinstance(order, list) else list(by_id.keys())
    for dsid in ids[-12:]:
        info = by_id.get(dsid)
        if not isinstance(info, dict):
            continue
        qid = info.get("query_id", "?")
        rc = info.get("row_count", "?")
        cols = info.get("columns") or []
        cols_s = ", ".join(str(c) for c in cols[:12])
        if len(cols) > 12:
            cols_s += f" (+{len(cols) - 12})"
        samp = info.get("sample_only")
        lines.append(f"- **`{dsid}`** · query_id=`{qid}` · row_count≈{rc} · sample_only={samp}")
        if cols_s:
            lines.append(f"  - colunas: {cols_s}")
    lines.append("")
    return "\n".join(lines)


def build_mcp_cache_digest_section(
    metadata: dict[str, Any],
    settings: Settings | None = None,
    *,
    semantic_retrieval_markdown: str | None = None,
) -> str:
    st = settings or get_settings()
    max_section = max(500, int(st.mcp_cache_digest_max_chars))
    max_entries = max(1, int(st.mcp_cache_digest_max_entries))
    max_per = max(200, int(st.mcp_cache_digest_max_chars_per_entry))
    block = metadata.get("mcp_tool_cache") or {}
    entries: list[dict[str, Any]] = list(block.get("entries") or [])
    if not entries:
        ds_only = _build_analytics_datasets_digest(metadata).strip()
        sem = _digest_semantic_block(semantic_retrieval_markdown, max_section // 3).strip()
        chunks = [c for c in (sem, ds_only) if c]
        if not chunks:
            return ""
        out = "\n\n".join(chunks)
        if len(out) > max_section:
            out = out[:max_section] + "\n\n[digest truncado mcp_cache_digest_section_max_chars]"
        return out
    tail = entries[-max_entries:]
    parts: list[str] = [
        "## Ferramentas MCP já executadas nesta sessão (digest)",
        "",
        "Reutiliza resultados em cache quando repetires a mesma tool com os mesmos argumentos normalizados; consulta este digest antes de nova chamada MCP.",
        "Com PostgreSQL activo, **`context_retrieve_similar`** (ILIKE + embeddings) cobre histórico semântico; o host pode pré-injectar um bloco abaixo.",
        "",
    ]
    for e in tail:
        parts.extend(_digest_one_entry(e, max_per))
        parts.append("")
    out = "\n".join(parts).strip()
    sem = _digest_semantic_block(semantic_retrieval_markdown, max_section // 3).strip()
    if sem:
        out = f"{out}\n\n{sem}".strip() if out else sem
    ds = _build_analytics_datasets_digest(metadata).strip()
    if ds:
        out = f"{out}\n\n{ds}".strip() if out else ds
    if len(out) > max_section:
        out = out[:max_section] + "\n\n[digest truncado mcp_cache_digest_section_max_chars]"
    return out


def entries_fingerprint(entries: list[dict[str, Any]]) -> str:
    keys = sorted(str(e.get("cache_key", "")) for e in entries)
    return hashlib.sha256("\n".join(keys).encode("utf-8")).hexdigest()


def get_or_reuse_llm_digest_cache(
    metadata: dict[str, Any],
    entries: list[dict[str, Any]],
    new_digest_markdown: str,
    settings: Settings | None = None,
) -> str:
    st = settings or get_settings()
    if not st.mcp_cache_digest_llm_reuse_hash:
        return new_digest_markdown
    h = entries_fingerprint(entries)
    slot = metadata.setdefault("mcp_digest_llm_cache", {})
    if slot.get("entries_hash") == h and slot.get("digest_markdown"):
        return str(slot["digest_markdown"])
    slot["entries_hash"] = h
    slot["digest_markdown"] = new_digest_markdown
    slot["generated_at"] = _utc_iso()
    return new_digest_markdown
