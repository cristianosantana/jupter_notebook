#!/usr/bin/env python3
"""Gera ficheiros em docs/ a partir da árvore de código (single source parcial)."""

from __future__ import annotations

import textwrap
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    docs = root / "docs"
    docs.mkdir(exist_ok=True)
    pkg = root / "src" / "orion_mcp"

    modules = sorted(p.relative_to(pkg).as_posix() for p in pkg.rglob("*.py") if p.name != "__init__.py")

    (docs / "modules.md").write_text(
        "# Módulos Orion\n\n"
        + "\n".join(f"- `{m}`" for m in modules[:200])
        + "\n",
        encoding="utf-8",
    )

    (docs / "architecture.md").write_text(
        textwrap.dedent(
            """
            # Arquitetura (gerado)

            - **API**: `api/main.py`, rotas em `api/routes/`.
            - **Core**: `core/orchestrator` (fluxo), `core/decision`, `core/state`, `core/tools`,
              `core/context`, `core/llm`, `core/formatter`, `core/memory`, `core/prompts`.
            - **Infra**: `infra/db`, `infra/cache`, `infra/queue`, `infra/observability`.
            - **MCP**: `mcp_adapter/server.py`.

            Ver também [ARCHITECTURE.md](../ARCHITECTURE.md) e [TRACEABILITY.md](TRACEABILITY.md).
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    (docs / "api.md").write_text(
        textwrap.dedent(
            """
            # API

            - `POST /api/v1/chat` — ver OpenAPI em `/openapi.json`.
            - `GET /health`
            - `GET /metrics` (Prometheus)

            Alias opcional: `POST /api/chat` quando `ORION_API_ENABLE_LEGACY_CHAT_ALIAS=true`.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    print("docs gerados em", docs)


if __name__ == "__main__":
    main()
