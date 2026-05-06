"""Regressão textual da skill avaliador_critico (política esclarecimento vs handles)."""

from __future__ import annotations

from pathlib import Path


def test_avaliador_critico_skill_covers_business_clarification_vs_internal_handles():
    text = (Path(__file__).resolve().parent.parent / "app" / "skills" / "avaliador_critico.md").read_text(
        encoding="utf-8"
    )
    assert "Esclarecimento ao utilizador vs. dados internos" in text
    assert "session_dataset_id" in text
    assert "opções" in text.lower() or "opções" in text
    assert "APROVAR" in text
    assert "handle interno" in text.lower() or "handles internos" in text.lower()
