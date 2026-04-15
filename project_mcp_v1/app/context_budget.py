"""Shrink do payload antes de ``model.chat`` quando a estimativa excede o tecto."""

from __future__ import annotations

import copy
from typing import Any

from app.config import Settings
from app.prompt_messages import estimate_full_prompt_tokens


def shrink_chat_messages_to_budget(
    skill_for_estimate: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    settings: Settings,
) -> list[dict[str, Any]]:
    limit = int(settings.orchestrator_prompt_hard_token_limit or 0)
    if limit <= 0:
        return messages
    out = copy.deepcopy(messages)
    cap_tool = max(2048, int(settings.tool_message_content_max_chars))
    rounds = 0
    while rounds < 48:
        rounds += 1
        est = estimate_full_prompt_tokens(skill_for_estimate, out, tools)
        if est <= limit:
            return out
        shrunk = False
        for m in out:
            if m.get("role") != "tool":
                continue
            c = m.get("content")
            if not isinstance(c, str) or len(c) <= 2000:
                continue
            new_len = max(2000, int(len(c) * 0.62))
            new_len = min(new_len, cap_tool)
            if new_len < len(c):
                m["content"] = c[:new_len] + "\n…[truncado_orçamento]"
                shrunk = True
                break
        if shrunk:
            continue
        for i, m in enumerate(out):
            if m.get("_orch_synthetic"):
                out.pop(i)
                shrunk = True
                break
        if shrunk:
            continue
        for i, m in enumerate(out):
            if m.get("role") == "system":
                continue
            if m.get("_orch_anchor"):
                continue
            out.pop(i)
            shrunk = True
            break
        if shrunk:
            continue
        for m in out:
            if m.get("role") == "system" and isinstance(m.get("content"), str):
                c = m["content"]
                if len(c) > 4000:
                    m["content"] = c[: int(len(c) * 0.85)] + "\n…[system_trunc_orçamento]"
                    shrunk = True
                    break
        if not shrunk:
            break
    return out
