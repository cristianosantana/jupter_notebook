"""Fusão de prompts (build_effective_system_text)."""

from pathlib import Path

from app.config import Settings

from app.prompt_assembly import (
    build_effective_system_text,
    build_system_package,
    load_tool_prompts_md,
)


def test_fusion_order_contains_shared_before_skill():
    meta = {"mcp_tool_cache": {"entries": []}}
    text = build_effective_system_text(
        agent="maestro",
        skill_body="SKILL_BODY_MARKER",
        entity_glossary_markdown="",
        mcp_digest_markdown="",
        session_metadata=meta,
        tools_openai_payload=[{"type": "function", "function": {"name": "route_to_specialist"}}],
        mcp_tools=None,
    )
    assert "Objetivo primário" in text
    assert "SKILL_BODY_MARKER" in text
    pos_shared = text.index("Objetivo primário")
    pos_skill = text.index("SKILL_BODY_MARKER")
    assert pos_shared < pos_skill


def test_tool_prompt_route_to_specialist_loaded():
    md = load_tool_prompts_md([], include_route_to_specialist=True)
    assert "route_to_specialist" in md
    assert "Objetivo primário" in md


def test_skills_dir_exists():
    p = Path(__file__).resolve().parent.parent / "app" / "skills"
    assert (p / "maestro.md").is_file()


def test_build_system_package_splits_skill_from_tool_md():
    meta = {"mcp_tool_cache": {"entries": []}}
    st = Settings.model_construct(orchestrator_tool_prompt_md_max_tools=0)
    core, ctx = build_system_package(
        agent="maestro",
        skill_body="ONLY_SKILL",
        entity_glossary_markdown="",
        mcp_digest_markdown="DIG",
        session_metadata=meta,
        tools_openai_payload=[{"type": "function", "function": {"name": "route_to_specialist"}}],
        mcp_tools=None,
        settings=st,
    )
    assert "ONLY_SKILL" in core
    assert "ONLY_SKILL" not in ctx
    assert "DIG" in ctx
    assert "Instruções" in ctx or "route_to_specialist" in ctx
