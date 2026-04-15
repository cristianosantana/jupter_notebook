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
    max_tools: int | None = None,
) -> str:
    chunks: list[str] = []
    seen: set[str] = set()
    ordered = list(names)
    if include_route_to_specialist and ROUTE_TO_SPECIALIST_TOOL_NAME not in ordered:
        ordered = [ROUTE_TO_SPECIALIST_TOOL_NAME] + ordered
    if max_tools is not None and max_tools > 0:
        if include_route_to_specialist and ordered and ordered[0] == ROUTE_TO_SPECIALIST_TOOL_NAME:
            ordered = [ordered[0]] + ordered[1 : 1 + max(0, max_tools - 1)]
        else:
            ordered = ordered[:max_tools]
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
        # Evita duplicar no system quando o orquestrador injecta o resumo no payload compacto.
        if not st.orchestrator_history_compact_enabled:
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


def build_system_package(
    *,
    agent: str,
    skill_body: str,
    entity_glossary_markdown: str,
    mcp_digest_markdown: str,
    session_metadata: dict[str, Any],
    tools_openai_payload: list[dict[str, Any]] | None,
    mcp_tools: list[Tool] | None,
    settings: Settings | None = None,
) -> tuple[str, str]:
    """
    Parte o system em ``system_core`` (políticas + agente + skill) e ``context_block``
    (instruções longas de tools + glossário + digest + memória), para montagem opcional
    em mensagens separadas (ver ``ORCHESTRATOR_SYSTEM_LAYER_SPLIT_ENABLED``).
    """
    st = settings or get_settings()
    fragments_core: list[str] = []

    for rel in ("shared.md", "writing.md", "context-policy.md"):
        block = _read_if_exists(rel)
        if block:
            fragments_core.append(block)

    agent_md = _read_if_exists(f"agents/{agent}.md")
    if agent_md:
        fragments_core.append(agent_md)

    skill = (skill_body or "").strip()
    if skill:
        fragments_core.append(skill)

    max_t = max(0, int(st.orchestrator_tool_prompt_md_max_tools or 0))
    mt = max_t if max_t > 0 else None
    if agent == "maestro":
        names = _tool_names_from_payload(tools_openai_payload)
        tp = load_tool_prompts_md(names, include_route_to_specialist=True, max_tools=mt)
    else:
        names = _tool_names_from_mcp(mcp_tools)
        tp = load_tool_prompts_md(names, include_route_to_specialist=False, max_tools=mt)

    fragments_ctx: list[str] = []
    if tp:
        fragments_ctx.append(tp)

    gloss = (entity_glossary_markdown or "").strip()
    if gloss:
        fragments_ctx.append(gloss)

    digest = (mcp_digest_markdown or "").strip()
    if digest:
        fragments_ctx.append(digest)

    mem = build_memory_blocks(session_metadata, st)
    if mem:
        fragments_ctx.append(mem)

    core = "\n\n".join(f for f in fragments_core if f).strip()
    ctx = "\n\n".join(f for f in fragments_ctx if f).strip()
    return core, ctx


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
    core, ctx = build_system_package(
        agent=agent,
        skill_body=skill_body,
        entity_glossary_markdown=entity_glossary_markdown,
        mcp_digest_markdown=mcp_digest_markdown,
        session_metadata=session_metadata,
        tools_openai_payload=tools_openai_payload,
        mcp_tools=mcp_tools,
        settings=settings,
    )
    return "\n\n".join(p for p in (core, ctx) if p).strip()
