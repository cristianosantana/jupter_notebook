from orion_mcp_v2.config.settings import Settings
from orion_mcp_v2.core.context.builder_aggregate_section import format_skill_aggregate_section


def test_section_none_when_no_aggregate():
    assert format_skill_aggregate_section({"summary": {}}) is None


def test_section_renders_aggregate():
    text = format_skill_aggregate_section(
        {"skill_aggregate": {"top_pairs": [{"x": 1}], "totals": {}}},
        settings=Settings(),
    )
    assert text is not None
    assert "Agregados específicos" in text
    assert "top_pairs" in text
