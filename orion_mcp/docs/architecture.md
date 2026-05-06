# Arquitetura (gerado)

- **API**: `api/main.py`, rotas em `api/routes/`.
- **Core**: `core/orchestrator` (fluxo), `core/decision`, `core/state`, `core/tools`,
  `core/context`, `core/llm`, `core/formatter`, `core/memory`, `core/prompts`.
- **Infra**: `infra/db`, `infra/cache`, `infra/queue`, `infra/observability`.
- **MCP**: `mcp_adapter/server.py`.

Ver também [ARCHITECTURE.md](ARCHITECTURE.md) e [TRACEABILITY.md](TRACEABILITY.md).
