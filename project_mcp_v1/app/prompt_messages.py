"""Fusão system+histórico e estimativa heurística de tokens (usado pelo orquestrador e orçamento)."""

from __future__ import annotations

import json
from typing import Any

from app.config import get_settings


def _strip_orch_internal_keys(msg: dict[str, Any]) -> dict[str, Any]:
    """Remove chaves internas do orquestrador (não enviar à API do modelo)."""
    return {
        k: v
        for k, v in msg.items()
        if not (isinstance(k, str) and k.startswith("_orch"))
    }


def _messages_with_skill(
    skill: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    public = [_strip_orch_internal_keys(m) for m in messages]
    if not skill:
        return list(public)
    out = list(public)
    had_system = any(m.get("role") == "system" for m in out)
    sk = skill.strip()
    for i, m in enumerate(out):
        if m.get("role") == "system":
            existing = (m.get("content") or "").strip()
            if not existing:
                merged = sk
            elif existing == sk or existing.startswith(sk + "\n\n"):
                # Evita duplicar skill já fundido (volta anterior / re-merge).
                merged = existing
            else:
                merged = f"{sk}\n\n{existing}".strip()
            out[i] = {**m, "content": merged}
    if not had_system:
        out.insert(0, {"role": "system", "content": sk})
    return out


def _estimate_tokens_from_text(text: str) -> int:
    if not text:
        return 0
    cpt = max(1, int(get_settings().orchestrator_chars_per_token_estimate))
    return max(1, (len(text) + cpt - 1) // cpt)


def _estimate_tokens_for_message(msg: dict[str, Any]) -> int:
    """Tokens aproximados de uma mensagem no formato chat (content + tool_calls)."""
    n = 4  # overhead de estrutura (role, campos)
    role = msg.get("role")
    if role is not None:
        n += _estimate_tokens_from_text(str(role))
    content = msg.get("content")
    if isinstance(content, str):
        n += _estimate_tokens_from_text(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                txt = part.get("text")
                if isinstance(txt, str):
                    n += _estimate_tokens_from_text(txt)
    tool_calls = msg.get("tool_calls")
    if tool_calls:
        n += _estimate_tokens_from_text(json.dumps(tool_calls, ensure_ascii=False))
    return n


def _estimate_prompt_tokens_messages_plus_skill(
    skill: str,
    messages: list[dict[str, Any]],
) -> int:
    """Estimativa do prompt enviado ao modelo (SKILL fundido no system + histórico)."""
    merged = _messages_with_skill(skill, messages)
    return sum(_estimate_tokens_for_message(m) for m in merged)


def _estimate_tokens_from_tool_dicts(tools: list[dict[str, Any]] | None) -> int:
    """Tokens aproximados de definições de ferramentas já serializáveis como dict (ex.: OpenAI-style)."""
    if not tools:
        return 0
    total = 128
    for t in tools:
        total += _estimate_tokens_from_text(json.dumps(t, ensure_ascii=False))
    return total


def estimate_full_prompt_tokens(
    skill: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
) -> int:
    """Skill fundido + mensagens + schema de tools (heurística)."""
    return _estimate_prompt_tokens_messages_plus_skill(
        skill, messages
    ) + _estimate_tokens_from_tool_dicts(tools)
