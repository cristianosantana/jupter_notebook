"""Dump opcional de pedidos/respostas LLM para ficheiro (activável por env)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from orion_mcp_v2.config.settings import Settings


def _serialize_openai_object(obj: Any) -> Any:
    try:
        dump = getattr(obj, "model_dump", None)
        if callable(dump):
            return dump(mode="json")
    except Exception:
        pass
    try:
        dump_json = getattr(obj, "model_dump_json", None)
        if callable(dump_json):
            return json.loads(dump_json())
    except Exception:
        pass
    return {"_type": type(obj).__name__, "_repr": repr(obj)[:8000]}


def _usage_summary_from_response_dict(serialized: dict[str, Any]) -> dict[str, Any]:
    """Extrai campos úteis para diagnóstico (ex.: reasoning_tokens vs content vazio em gpt-5)."""
    choices = serialized.get("choices") or []
    ch0 = choices[0] if choices else {}
    msg = (ch0.get("message") or {}) if isinstance(ch0.get("message"), dict) else {}
    usage = serialized.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    ctd = usage.get("completion_tokens_details") or {}
    if not isinstance(ctd, dict):
        ctd = {}
    return {
        "finish_reason": ch0.get("finish_reason"),
        "message_content_empty": not (msg.get("content") or "").strip(),
        "message_refusal_present": bool(msg.get("refusal")),
        "completion_tokens": usage.get("completion_tokens"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "reasoning_tokens": ctd.get("reasoning_tokens"),
        "audio_tokens": ctd.get("audio_tokens"),
    }


def write_llm_io_dump(
    settings: "Settings",
    *,
    model: str,
    max_tokens: int,
    completion_kw: dict[str, int],
    system_prompt: str,
    user_text: str,
    raw_response: Any | None,
    extracted_reply: str,
    mode: str,
    stream_chunks: list[str] | None = None,
) -> None:
    """Escreve um JSON por chamada em ``settings.llm_io_dump_dir`` se o dump estiver activo."""
    if not getattr(settings, "llm_io_dump_enabled", False):
        return
    dump_dir = Path(getattr(settings, "llm_io_dump_dir", "/tmp/orion_mcp_v2_llm_io"))
    ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    uid = uuid4().hex[:12]
    out_path = dump_dir / f"llm_io_{ts}_{uid}.json"

    serialized_resp = _serialize_openai_object(raw_response) if raw_response is not None else None
    usage_summary: dict[str, Any] | None = None
    if isinstance(serialized_resp, dict):
        usage_summary = _usage_summary_from_response_dict(serialized_resp)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "mode": mode,
        "model": model,
        "max_tokens_request": max_tokens,
        "completion_kwargs": completion_kw,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "system_prompt_chars": len(system_prompt),
        "user_text_chars": len(user_text),
        "extracted_reply": extracted_reply,
        "extracted_reply_chars": len(extracted_reply),
        "usage_summary": usage_summary,
        "response_raw": serialized_resp,
        "stream_chunks_count": len(stream_chunks or []),
    }
    sc = stream_chunks or []
    if sc:
        total_sc = sum(len(x) for x in sc)
        if total_sc <= 1_000_000 and len(sc) <= 10_000:
            payload["stream_chunk_deltas"] = sc
        else:
            payload["stream_chunk_deltas_omitted"] = True
            payload["stream_chunk_deltas_total_chars"] = total_sc
            payload["stream_chunk_deltas_count"] = len(sc)

    try:
        dump_dir.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
