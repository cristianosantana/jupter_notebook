"""
Fusão ordenada do texto de system: shared → writing → context-policy → agents → SKILL → tools → glossário → digest → memory.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mcp.types import Tool  # pyright: ignore[reportMissingImports]

from app.config import Settings, get_settings
from app.routing_tools import ROUTE_TO_SPECIALIST_TOOL_NAME

_logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _read_if_exists(rel: str) -> str:
    path = PROMPTS_DIR / rel
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as e:
        _logger.warning("prompt read failed %s: %s", path, e)
        return ""


def _tool_names_from_payload(tools: list[dict[str, Any]] | None) -> list[str]:
    if not tools:
        return []
    names: list[str] = []
    for t in tools:
        fn = t.get("function") if isinstance(t.get("function"), dict) else None
        if fn and fn.get("name"):
            names.append(str(fn["name"]))
        elif t.get("name"):
            names.append(str(t["name"]))
    return names


def _tool_names_from_mcp(tools: list[Tool] | None) -> list[str]:
    if not tools:
        return []
    return [t.name for t in tools if getattr(t, "name", None)]


def load_tool_prompts_md(
    names: list[str],
    *,
    include_route_to_specialist: bool = False,
) -> str:
    chunks: list[str] = []
    seen: set[str] = set()
    ordered = list(names)
    if include_route_to_specialist and ROUTE_TO_SPECIALIST_TOOL_NAME not in ordered:
        ordered = [ROUTE_TO_SPECIALIST_TOOL_NAME] + ordered
    for name in ordered:
        if name in seen:
            continue
        seen.add(name)
        body = _read_if_exists(f"tools/{name}.md")
        if body:
            chunks.append(f"### Instruções: `{name}`\n\n{body}")
    if not chunks:
        return ""
    return "## Instruções por ferramenta\n\n" + "\n\n".join(chunks)


def build_memory_blocks(metadata: dict[str, Any], settings: Settings | None = None) -> str:
    st = settings or get_settings()
    if not st.memory_prompts_enabled:
        return ""
    parts: list[str] = []
    if st.memory_conversation_summary_enabled:
        s = metadata.get("conversation_summary")
        if isinstance(s, str) and s.strip():
            parts.append("## Resumo da conversa\n\n" + s.strip())
    if st.memory_session_notes_enabled:
        n = metadata.get("session_notes")
        if n is not None:
            parts.append("## Notas de sessão\n\n```json\n" + str(n) + "\n```")
    if st.memory_extraction_enabled:
        ex = metadata.get("extracted_memory")
        if ex is not None:
            parts.append("## Memória extraída\n\n```json\n" + str(ex) + "\n```")
    return "\n\n".join(parts).strip()


def build_effective_system_text(
    *,
    agent: str,
    skill_body: str,
    entity_glossary_markdown: str,
    mcp_digest_markdown: str,
    session_metadata: dict[str, Any],
    tools_openai_payload: list[dict[str, Any]] | None,
    mcp_tools: list[Tool] | None,
    settings: Settings | None = None,
) -> str:
    st = settings or get_settings()
    fragments: list[str] = []

    for rel in ("shared.md", "writing.md", "context-policy.md"):
        block = _read_if_exists(rel)
        if block:
            fragments.append(block)

    agent_md = _read_if_exists(f"agents/{agent}.md")
    if agent_md:
        fragments.append(agent_md)

    skill = (skill_body or "").strip()
    if skill:
        fragments.append(skill)

    if agent == "maestro":
        names = _tool_names_from_payload(tools_openai_payload)
        tp = load_tool_prompts_md(names, include_route_to_specialist=True)
    else:
        names = _tool_names_from_mcp(mcp_tools)
        tp = load_tool_prompts_md(names, include_route_to_specialist=False)
    if tp:
        fragments.append(tp)

    gloss = (entity_glossary_markdown or "").strip()
    if gloss:
        fragments.append(gloss)

    digest = (mcp_digest_markdown or "").strip()
    if digest:
        fragments.append(digest)

    mem = build_memory_blocks(session_metadata, st)
    if mem:
        fragments.append(mem)

    return "\n\n".join(f for f in fragments if f).strip()
