"""Testes isolados do period_range Senna (sem public_chat)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))

from senna_replica.period_range import expand_period_range, periods_from_question


def test_senna_expand_range() -> None:
    assert expand_period_range("2026-02", "2026-04") == (
        "2026-02",
        "2026-03",
        "2026-04",
    )


def test_senna_periods_from_question() -> None:
    assert periods_from_question("de janeiro a março de 2026") == (
        "2026-01",
        "2026-02",
        "2026-03",
    )
