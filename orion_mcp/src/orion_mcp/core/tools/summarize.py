from __future__ import annotations

import json
from typing import Any


def summarize_tool_result(result: dict[str, Any], *, max_chars: int = 2000) -> str:
    """Deterministic summary for cache + context (no LLM)."""
    text = json.dumps(result, ensure_ascii=False, sort_keys=True)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "…[truncado]"
