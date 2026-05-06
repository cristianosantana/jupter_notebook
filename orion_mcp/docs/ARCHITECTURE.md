# Orion MCP — arquitetura e invariantes

## Mandamentos operacionais (10)

1. Um único fluxo de orquestração por pedido (sem “modos” paralelos de execução).
2. O estado persistido (`conversation_state`) é a fonte da verdade do turno.
3. O contexto enviado ao LLM é sempre construído pelo `ContextBuilder`, nunca um histórico acumulado.
4. O LLM não decide o fluxo: a `DecisionEngine` é determinística e baseada em `(state, input, strategy)`.
5. Ferramentas são determinísticas, sem LLM interno, e com resultados cacheáveis (Redis + resumo).
6. Configuração tipada (`Settings` Pydantic) validada no arranque da API.
7. Contrato HTTP versionado (`/api/v1/chat` e `/api/v1/chat/stream`) e OpenAPI gerado automaticamente.
8. Módulos pequenos (`orchestrator/`, `decision/`, `tools/`, …) testáveis isoladamente.
9. Em produção, falha explícita se dependências obrigatórias (ex.: Postgres) não estiverem disponíveis.
10. Observabilidade mínima: métricas Prometheus, logs estruturados e hooks OTEL.

## Secção 2.6 — camada LLM (streaming)

- **Mapa de modelos** (`Settings` + `core/llm/model_config.py`): `resolve_chat_model_id(settings, strategy)` para chat (`fast` / `deep` → `ORION_LLM_MODEL_*`); `resolve_embedding_model_id(settings)` para embeddings. Não fixar IDs de modelo fora destes resolvers (salvo testes isolados).
- **`LLMProvider`**: `generate_stream` é o contrato base (stream de deltas de texto); `generate` agrega o stream para chamadas one-shot (ex.: JSON de insights). Com `ORION_LLM_SYSTEM_PROMPT` definido e não vazio, o pedido ao OpenAI inclui mensagem **`system`** + **`user`** (o mock prefixa `[system]` para testes).
- **Perfil heurístico de tarefa** (`core/state/intent_heuristic.py`): após `update_state`, o orquestrador chama `apply_task_heuristic_profile` e grava `state.entities["task_profile"]` (dict estável: `risk_posture`, `data_status`, `summary_for_llm`, …). O `ContextBuilder` inclui a secção «Perfil da tarefa (heurística)» e coloca **pergunta + perfil antes** de «Dados resumidos», de modo que a pergunta actual não é omitida por orçamento de tokens. Ver [`docs/heurística_de_tomada_de_decisão.md`](heurística_de_tomada_de_decisão.md) para o enquadramento conceptual.
- **Orquestrador**: no turno `GENERATE_RESPONSE`, o texto é obtido consumindo `generate_stream` até EOF; `FORMAT_RESPONSE` não chama LLM; `RequestBudget.record_llm()` conta **uma** vez por stream completo (ou por `generate` one-shot nos insights). Com `ORION_LLM_HALT_BEFORE_CHAT=true`, o LLM não é invocado: grava-se um JSON por pedido em `ORION_LLM_DEBUG_LOG_DIR` (por defeito `logs/`) com `messages` + parâmetros equivalentes ao pedido OpenAI e `extra` (snapshot de `data_cache`, métricas de tool, truncagens). Com `ORION_ORCHESTRATOR_CHAT_TRACE=true`, o mesmo tipo de snapshot é também emitido em log INFO (`orion_mcp.orchestration`) após `_prepare_turn` e no halt. Em Docker (`WORKDIR /app`), o defeito é `/app/logs`; o compose monta `orion_mcp/logs` → `/app/logs` para ver os ficheiros no host.
- **HTTP**: `POST /api/v1/chat` mantém resposta JSON; o fluxo principal com streaming ao cliente é `POST /api/v1/chat/stream` (`text/event-stream`, eventos `data: {json}` com `type: token|done`). Com `ORION_API_ENABLE_LEGACY_CHAT_ALIAS=true`, existe também `POST /api/chat/stream`.

## Secção 3 — performance e fallback parcial

- **Orçamentos**: `max_llm_calls_per_request`, `max_tool_calls_per_request`, `RequestBudget` + `BudgetExceeded` (inalterado).
- **Teto de prompt LLM**: `ORION_LLM_PROMPT_TOKEN_BUDGET` (`Settings.llm_prompt_token_budget`) quando definido; caso contrário `min(context_max_tokens, llm_max_prompt_tokens)` via `effective_llm_prompt_token_cap` / `build_context` / `cap_llm_prompt` (sufixos incluídos). Opcional **`ORION_LLM_CONTEXT_MAX_CHARS`**: por pedido HTTP ao chat, `len(system)+len(user)` não excede o valor (`apply_llm_context_max_chars`). Resumo de tool: caracteres derivados ou `ORION_TOOL_LLM_SUMMARY_MAX_CHARS` / `ORION_LLM_TOOL_CONTEXT_CHARS`. Geração chat vs contexto: `llm_completion_max_tokens` (não misturar com o teto de contexto).
- **Timeouts**: `asyncio.wait_for` nas tools (`ORION_TOOL_TIMEOUT_SECONDS`); cliente OpenAI com `ORION_OPENAI_HTTP_TIMEOUT_SECONDS` (chat + embeddings).
- **Degradação**: `state.flags["perf"]` e espelho opcional em `payload["perf"]` (chaves booleanas estáveis: `tool_timeout`, `llm_budget_exhausted`, `context_truncated`, `llm_timeout`, **`mcp_unavailable`** quando o cliente gRPC falha em circuito aberto / erro e a API usa resposta parcial). Separado de `force_refresh` (re-execução de tool).

## MCP em serviço persistente (rede) — antes / depois

**Antes (anti-padrão):** `API → spawn subprocess → MCP stdio → MySQL` — arranque por pedido, sem pool estável, latência e debug piores.

**Depois (alvo):** `API (FastAPI) → cliente gRPC persistente → MCP server (processo long-lived) → pool MySQL + Redis L2`. O orquestrador **não** sobe subprocesso do servidor MCP no hot path do `/chat`; apenas canal **gRPC** reutilizável (`ORION_MCP_GRPC_TARGET`), com deadlines, retry limitado a erros transitórios e **circuit breaker** no cliente.

**PostgreSQL** permanece no domínio Orion (sessão, estado, memória vector, etc.). **MySQL** fica no domínio de negócio acedido **só** pelo processo do serviço MCP (`ORION_MCP_MYSQL_URL` no container do MCP, não no worker HTTP principal).

### Contrato em rede

- **Wire obrigatório API↔MCP:** serviço protobuf **`AnalyticsServiceV1`** (`mcp_adapter/proto/orion_mcp_tools.proto`), codegen em `mcp_adapter/grpc_gen/`. Alterações **só aditivas** em V1; breaking → `AnalyticsServiceV2`.
- **Tools:** `RunTool(tool_name, args_json)` devolve envelope JSON (`type`, `name`, `value`, `metadata`) em `envelope_json`; o núcleo consome `value` com o mesmo shape que as tools in-process quando aplicável.
- **Queries SQL:** ficheiros versionados em [`../src/orion_mcp/mcp_adapter/query_sql/`](../src/orion_mcp/mcp_adapter/query_sql/) (`*.sql` com cabeçalho `/* @mcp_query_meta */`, YAML: `query_id`, `output_shape`, etc.; alinhado a `project_mcp_v1/mcp_server/query_sql`). Catálogo em `mcp_adapter/sql_catalog.py` (`SQL_CATALOG`); execução só por `query_id` em `mcp_adapter/queries/` + `mcp_adapter/server/query_executor.py` (sem SQL livre do LLM). Placeholders: `__MCP_DATE_FROM__` / `__MCP_DATE_TO__` via `sql_placeholders.py` (`YYYY-MM-DD`). `run_domain_query`: parâmetros no JSON raiz ou em `params`; `limit`/`offset` (cap 10000); `summarize` só compacta com `rows_sample` (sem sampling MCP no servidor). Semáforo: `ORION_MCP_QUERY_CONCURRENCY`. Validação: `PYTHONPATH=src python3 scripts/check_query_sql_meta.py`.
- **Cache em dois níveis:** **L1** — cache de resumo de tool no host da API (`ToolRegistry` + `ORION_MCP_L1_TOOL_CACHE_TTL_SECONDS` quando há MCP remoto). **L2** — Redis no serviço MCP (`ORION_MCP_REDIS_URL` ou fallback `ORION_REDIS_URL`), TTL `ORION_MCP_L2_CACHE_TTL_SECONDS`.
- **Gateway HTTP (opcional):** `ORION_MCP_HTTP_GATEWAY_ENABLED` arranca rotas mínimas (`/debug/run_tool`, `/health`) no mesmo processo, por trás de rede isolada ou auth em produção; **não** substitui o cliente gRPC do orquestrador.
- **TLS/mTLS:** em produção, ativar `ORION_MCP_GRPC_USE_TLS=true` e credenciais de canal no cliente (`GrpcMcpToolClient`); não passar segredos em query string.
- **Legado stdio:** `orion-mcp-server-stdio` / `orion_mcp.mcp_adapter.stdio_server` apenas para dev/Cursor; contrato de produção é gRPC (`orion-mcp-server` → `mcp_adapter.server.main`).

### Observabilidade (MCP)

- Logs com `extra` estruturado (`query_id`, `tool`, latência onde aplicável). OpenTelemetry no servidor MCP é **opcional** (fase posterior); até lá, logs JSON/texto no processo são suficientes para diagnóstico.
- **Escala:** várias réplicas do MCP atrás de balanceamento **gRPC-aware** (client-side LB, mesh ou DNS multi-A); afinar `ORION_MCP_MYSQL_POOL_*` e `ORION_MCP_QUERY_CONCURRENCY` por réplica em função de CPU/RAM.

## Princípios adicionais

- **Write-through**: o estado é gravado antes da resposta HTTP ser concluída.
- **Memória longa**: opcional via pgvector; indexação pesada pode ir para fila (Celery).
