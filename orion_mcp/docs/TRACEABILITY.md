# Matriz de rastreabilidade (resumo)

Este ficheiro liga requisitos de alto nível a módulos e testes no repositório. A versão completa detalhada está no plano de implementação aprovado (não versionado aqui).

| Área | Módulos principais | Testes |
|------|--------------------|--------|
| Princípios state-driven | `core/decision`, `core/orchestrator`, `core/state` | `tests/test_decision_engine.py`, `tests/test_tool_cache.py` |
| Contexto construído | `core/context/context_builder.py` | `tests/test_context_builder.py` |
| Tools + cache | `core/tools`, `infra/cache/tool_cache.py` | `tests/test_tool_cache.py` |
| Formatter isolado | `core/formatter/formatter.py` | `tests/test_formatter.py` |
| Skills YAML | `core/prompts/skill_model.py` | `tests/test_skill_yaml.py` |
| API + OpenAPI | `api/main.py`, `api/routes/chat.py` (`POST /api/v1/chat`, `POST /api/v1/chat/stream` SSE) | `tests/test_api_chat.py`, `tests/test_api_chat_stream.py` |
| LLM layer (2.6) | `core/llm/model_config.py`, `core/llm/provider.py` (`generate_stream` + `generate`), `core/orchestrator/orchestrator.py` | `tests/test_llm_model_config.py`, `tests/test_llm_streaming.py` |
| Performance / degradação (3) | `core/config/settings.py` (`llm_prompt_token_budget`, `llm_max_prompt_tokens`, `context_max_tokens`, `llm_completion_max_tokens`, `openai_http_timeout_seconds`), `core/context/context_builder.py`, `core/orchestrator/action_executor.py`, `core/orchestrator/orchestrator.py` (`payload['perf']`, `state.flags['perf']`) | `tests/test_perf_sec3.py`, `tests/test_context_builder.py`, `tests/test_settings_unified_limits.py` |
| Persistência | `infra/db/state_repository.py`, `infra/db/migrations/*.sql` | (integração manual / CI com Postgres opcional) |
| Memória longa (2.2) | `core/memory/long.py`, `core/memory/embed_pipeline.py`, `core/memory/index_queue.py`, `infra/queue/celery_app.py`, migrações `002`, `003` (HNSW se dim≤2000), `004` (marcada sem SQL se dim>2000; pgvector limita ANN a 2000 dim) | `tests/test_memory_embed.py` |
| MCP adapter (gRPC) | `mcp_adapter/server/main.py`, `mcp_adapter/client/grpc_client.py`, `mcp_adapter/proto/orion_mcp_tools.proto`, `mcp_adapter/query_sql/*.sql`, `mcp_adapter/query_sql_meta.py`, `mcp_adapter/sql_catalog.py`, `mcp_adapter/sql_placeholders.py`, `mcp_adapter/sql_select.py`, `mcp_adapter/queries/analytics_sql.py` | `tests/test_mcp_grpc_contract.py`, `tests/test_query_sql_meta_orion.py`, `tests/test_sql_catalog_registry.py`, `scripts/check_query_sql_meta.py`, `python -m orion_mcp.mcp_adapter.server` |
| MCP stdio (legado) | `mcp_adapter/stdio_server.py` | `orion-mcp-server-stdio` |
| Observabilidade | `infra/observability/*`, `/metrics` | manual / compose Prometheus |

Atualizar esta tabela quando novos requisitos forem implementados.
