"""Parse e extração de ``content_blocks`` (espelho do App.tsx)."""

from __future__ import annotations

import json
import re
from typing import Any


def normalize_content_block_raw(raw: Any) -> Any:
    if not raw or not isinstance(raw, dict):
        return raw
    o = dict(raw)
    t = o.get("type")
    if isinstance(t, str):
        o["type"] = t.strip().lower()
    if o.get("type") == "table":
        if o.get("columns") is None and raw.get("Columns") is not None:
            o["columns"] = raw["Columns"]
        if o.get("rows") is None and raw.get("Rows") is not None:
            o["rows"] = raw["Rows"]
    if o.get("type") == "metric_grid" and o.get("items") is None and raw.get("Items") is not None:
        o["items"] = raw["Items"]
    if o.get("type") == "heading" and o.get("level") is not None:
        n = int(o["level"])
        if n in (1, 2, 3):
            o["level"] = n
    return o


def is_content_block(b: Any) -> bool:
    if not b or not isinstance(b, dict):
        return False
    t = b.get("type")
    if t == "paragraph":
        return isinstance(b.get("text"), str)
    if t == "heading":
        try:
            lv = b.get("level")
            n = 2 if lv is None else int(lv)
        except (TypeError, ValueError):
            return False
        return isinstance(b.get("text"), str) and n in (1, 2, 3)
    if t == "table":
        return isinstance(b.get("columns"), list) and isinstance(b.get("rows"), list)
    if t == "metric_grid":
        items = b.get("items")
        if not isinstance(items, list):
            return False
        for it in items:
            if not it or not isinstance(it, dict):
                return False
            if not isinstance(it.get("label"), str):
                return False
            if it.get("value") is None:
                return False
        return True
    return False


def parse_content_blocks(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    ver = raw.get("version")
    if ver not in (1, "1"):
        return None
    blocks_raw = raw.get("blocks")
    if not isinstance(blocks_raw, list):
        return None
    blocks: list[dict[str, Any]] = []
    for item in blocks_raw:
        if not isinstance(item, dict):
            continue
        norm = normalize_content_block_raw(item)
        if not isinstance(norm, dict):
            continue
        if is_content_block(norm):
            blocks.append(norm)
    if not blocks:
        return None
    return {"version": 1, "blocks": blocks}


def extract_reply_content_blocks(reply: str) -> tuple[str, dict[str, Any] | None]:
    if not reply or not reply.strip():
        return reply, None
    text = reply
    r = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)
    matches = list(r.finditer(text))
    for match in reversed(matches):
        raw_inner = (match.group(1) or "").strip()
        if not raw_inner.startswith("{"):
            continue
        try:
            data = json.loads(raw_inner)
        except json.JSONDecodeError:
            continue
        payload = parse_content_blocks(data)
        if not payload:
            continue
        full = match.group(0)
        start_idx = match.start()
        end_idx = start_idx + len(full)
        before = text[:start_idx].rstrip()
        after = text[end_idx:].lstrip()
        display = "\n\n".join(x for x in (before, after) if x).strip()
        return display, payload
    stripped = text.strip()
    if stripped.startswith("{") and '"blocks"' in stripped:
        try:
            data = json.loads(stripped)
            payload = parse_content_blocks(data)
            if payload:
                return "", payload
        except json.JSONDecodeError:
            pass
    return text, None
