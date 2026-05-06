from pathlib import Path

from orion_mcp_v2.config.settings import Settings
from orion_mcp_v2.skill.reference_lookups_loader import (
    append_reference_lookups_to_system,
    format_reference_lookups_block,
)


def test_format_reference_lookups_non_empty():
    s = Settings(reference_lookups_enabled=True, reference_lookups_max_chars=100_000)
    block = format_reference_lookups_block(s)
    assert "concessionaria_id" in block
    assert "AUDI CARBEL" in block


def test_append_prepends_nothing_when_disabled():
    s = Settings(reference_lookups_enabled=False)
    assert append_reference_lookups_to_system("Somente isto", s) == "Somente isto"


def test_truncation_message_when_cap_small():
    s = Settings(reference_lookups_enabled=True, reference_lookups_max_chars=200)
    block = format_reference_lookups_block(s)
    assert "truncado" in block.lower() or len(block) <= 400


def test_override_file(tmp_path: Path):
    p = tmp_path / "mini.md"
    p.write_text("# X\nhello lookups\n", encoding="utf-8")
    s = Settings(
        reference_lookups_enabled=True,
        reference_lookups_max_chars=10_000,
        reference_lookups_file=p,
    )
    assert "hello lookups" in format_reference_lookups_block(s)
