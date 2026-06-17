from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_IMPORTS = (
    "orion_mcp_v3.broker",
    "RemissiveMemoryStore",
    "orion_mcp_v3.api.routes.chat",
    "orion_mcp_v3.memory.retrieval_pipeline",
    "orion_mcp_v3.prompts",
    "orion_mcp_v3.connection_hub",
    "orion_mcp_v3.infra.postgres",
    "orion_mcp_v3.config.settings",
)

PUBLIC_CHAT_ROOT = Path(__file__).resolve().parents[2]
ANALYTICAL_CHAT = Path("src/orion_mcp_v3/api/routes/chat.py")
GLOBAL_MIGRATIONS_DIR = Path("src/orion_mcp_v3/infra/postgres/migrations")
GLOBAL_PROMPTS_REGISTRY = Path("src/orion_mcp_v3/prompts/registry.yaml")


def _production_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if not path.is_file():
            continue
        if "tests" in path.relative_to(root).parts:
            continue
        files.append(path)
    return files


def test_guardrail_isolation() -> None:
    for path in _production_python_files(PUBLIC_CHAT_ROOT):
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_IMPORTS:
            assert token not in text, f"{path} imports forbidden token {token!r}"


def test_no_regression_analytical() -> None:
    text = ANALYTICAL_CHAT.read_text(encoding="utf-8")
    assert "public_chat" not in text


def test_global_prompt_registry_does_not_reference_public_chat() -> None:
    text = GLOBAL_PROMPTS_REGISTRY.read_text(encoding="utf-8")
    assert "public_chat" not in text


def test_global_migrations_do_not_include_public_chat_schema() -> None:
    if not GLOBAL_MIGRATIONS_DIR.is_dir():
        return
    for path in GLOBAL_MIGRATIONS_DIR.glob("*.sql"):
        text = path.read_text(encoding="utf-8")
        assert "public_chat_questions" not in text, path.name


def test_public_chat_modules_parse() -> None:
    for path in _production_python_files(PUBLIC_CHAT_ROOT):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
