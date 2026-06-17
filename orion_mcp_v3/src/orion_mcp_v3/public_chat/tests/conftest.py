"""Pytest: carrega env do módulo public_chat e do projeto."""

from __future__ import annotations

from pathlib import Path

_MODULE_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _MODULE_ROOT.parents[1]

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment, misc]

if load_dotenv is not None:
    load_dotenv(_MODULE_ROOT / ".env")
    load_dotenv(_PROJECT_ROOT / ".env")
