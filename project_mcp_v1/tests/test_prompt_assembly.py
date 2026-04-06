"""Fusão de prompts (build_effective_system_text)."""

from pathlib import Path

from app.prompt_assembly import build_effective_system_text, load_tool_prompts_md


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
