from __future__ import annotations

from pathlib import Path


MAIN_PY = Path("src/orion_mcp_v3/api/main.py")
CHAT_PY = Path("src/orion_mcp_v3/api/routes/chat.py")
PUBLIC_CHAT_ROOT = Path(__file__).resolve().parents[2]


def test_main_imports_only_integration() -> None:
    text = MAIN_PY.read_text(encoding="utf-8")
    assert "public_chat.integration.fastapi" in text
    assert "public_chat.application" not in text
    assert "public_chat.api" not in text


def test_no_regression_analytical() -> None:
    text = CHAT_PY.read_text(encoding="utf-8")
    assert "public_chat" not in text


def test_integration_module_exists() -> None:
    path = PUBLIC_CHAT_ROOT / "integration" / "fastapi.py"
    assert path.is_file()
