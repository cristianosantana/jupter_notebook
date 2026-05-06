# Resumo - 2026-04-16 14:58

Foi criado o projeto **`orion_mcp/`** na raiz do workspace, com pacote instalável em `src/orion_mcp/`, alinhado ao plano: **estado em PostgreSQL (ou memória em dev)**, **DecisionEngine determinística**, **orquestrador fino**, **tools in-process + cache Redis ou memória**, **`ContextBuilder`**, **`LLMProvider` (OpenAI ou mock)**, **`Formatter` isolado**, **memória longa (pgvector + retrieve)**, **MCP via FastMCP** sem subprocess no `/chat`, **métricas Prometheus**, **OTEL opcional** (`ORION_OTEL_CONSOLE`), **Celery placeholder**, **docs/scripts + CI**, **compose Prometheus/Grafana**.

## Como correr

```bash
cd /home/cristiano/code/jupter_notebook/orion_mcp
pip install -e ".[dev]"
uvicorn orion_mcp.api.main:app --reload
```

- Chat: `POST /api/v1/chat` (corpo: `session_id`, `message`, `strategy`).
- Métricas: `GET /metrics`.
- MCP stdio: `python -m orion_mcp.mcp_adapter.server` ou `orion-mcp-server`.
- Migrações: `orion-migrate`.

## Testes e CI

- **17 testes** em `orion_mcp/tests/` (`pytest`).
- Workflows: [`.github/workflows/orion-mcp-ci.yml`](.github/workflows/orion-mcp-ci.yml) e [`.github/workflows/orion-mcp-docs.yml`](.github/workflows/orion-mcp-docs.yml).

## Ficheiros de referência

- Arquitetura e mandamentos: [`orion_mcp/ARCHITECTURE.md`](orion_mcp/ARCHITECTURE.md)  
- Rastreabilidade: [`orion_mcp/docs/TRACEABILITY.md`](orion_mcp/docs/TRACEABILITY.md)  
- Orquestração: [`orion_mcp/src/orion_mcp/core/orchestrator/orchestrator.py`](orion_mcp/src/orion_mcp/core/orchestrator/orchestrator.py)  
- API: [`orion_mcp/src/orion_mcp/api/main.py`](orion_mcp/src/orion_mcp/api/main.py)  
- Observabilidade local: [`orion_mcp/docker-compose.observability.yml`](orion_mcp/docker-compose.observability.yml)  

O ficheiro do **plano** não foi alterado, conforme pedido. Todos os to-dos associados foram marcados como **concluídos**.
