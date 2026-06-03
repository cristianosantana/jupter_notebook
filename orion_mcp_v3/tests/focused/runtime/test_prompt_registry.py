from __future__ import annotations

from pathlib import Path

from orion_mcp_v3.prompts import get_prompt_registry


def test_prompt_registry_loads_required_prompt_ids() -> None:
    registry = get_prompt_registry()

    for prompt_id in (
        "narrator.base",
        "analytical_intent.system",
        "answer_presentation.system",
        "query_template_selector.system",
        "analytical_system.fragments",
        "analytical_context_builder.system",
    ):
        assert registry.get(prompt_id).id == prompt_id


def test_prompt_registry_reads_system_and_fragments() -> None:
    registry = get_prompt_registry()

    assert "analytical intent interpreter" in registry.get_text("analytical_intent.system")
    assert "narrador final do Orion" in registry.get_text("narrator.base")
    assert "NÃO" in registry.get_text("narrator.base")
    assert (
        "Resposta direta"
        in registry.get_fragment("narrator.base", "direct_answer_literal")
    )
    assert "O QUE NUNCA FAZER" in registry.get_fragment(
        "analytical_system.fragments",
        "anti_hallucination",
    )


def test_all_registry_entries_have_metadata() -> None:
    registry = get_prompt_registry()

    for spec in registry.all():
        assert spec.id
        assert spec.version >= 1
        assert spec.purpose
        assert spec.system or spec.fragments


def test_runtime_prompt_modules_do_not_define_hardcoded_system_prompts() -> None:
    project_root = Path(__file__).resolve().parents[3]
    migrated_files = (
        project_root / "src/orion_mcp_v3/runtime/narrator.py",
        project_root / "src/orion_mcp_v3/runtime/analytical_intent_interpreter.py",
        project_root / "src/orion_mcp_v3/runtime/answer_presentation_interpreter.py",
        project_root / "src/orion_mcp_v3/runtime/analytical_system_prompt.py",
        project_root / "src/orion_mcp_v3/runtime/context_builder.py",
        project_root / "src/orion_mcp_v3/broker/query_template_selector.py",
    )

    forbidden_literals = (
        '"""You are',
        '"""Você é',
        '"You are an analytics narrator."',
        "_IDENTITY = \"\"\"",
    )
    for path in migrated_files:
        text = path.read_text(encoding="utf-8")
        for literal in forbidden_literals:
            assert literal not in text
