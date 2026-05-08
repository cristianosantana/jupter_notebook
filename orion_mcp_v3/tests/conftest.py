"""Pytest: carrega ``orion_mcp_v3/.env`` para todos os testes encontrarem variáveis."""

from __future__ import annotations

from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment, misc]

if load_dotenv is not None:
    load_dotenv(_ENV_FILE)
