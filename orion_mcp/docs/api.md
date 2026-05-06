# API

- `POST /api/v1/chat` — ver OpenAPI em `/openapi.json`.
- `POST /api/v1/chat/stream` — SSE (`text/event-stream`); evento final `done` inclui `payload` com a mesma forma que o JSON de `/chat`.
- `GET /health`
- `GET /metrics` (Prometheus)

## Corpo do chat (`ChatRequest`)

Além de `session_id`, `message` e `strategy`, podes enviar campos **opcionais** para uma consulta SQL **catalogada** no MCP:

| Campo | Tipo | Descrição |
|-------|-----|------------|
| `query_id` | string opcional | ID registado no catálogo MCP (`ALLOWED_QUERY_IDS`). Se enviado, tem de ser válido. |
| `date_from` / `date_to` | string opcional | Datas `YYYY-MM-DD` passadas ao executor SQL (placeholders da query). |
| `limit` | int opcional | `LIMIT` na página (1–10000). Por defeito na API usa-se um valor conservador se omitires. |
| `offset` | int opcional | `OFFSET` (≥ 0). |
| `summarize` | bool opcional | Modo compacto no MCP (`rows_sample`). Por defeito `true` no fluxo chat. |

**Requisito:** com `query_id` definido, a API tem de ter **`ORION_MCP_GRPC_TARGET`** configurado; caso contrário o pedido falha na validação do corpo (erro 422).

**Validação:** `query_id` desconhecido → erro de validação (422 no FastAPI).

**Paginação / volume:** o MCP devolve `row_count`, `limit` e `offset`. Se `row_count >= limit`, pode haver mais dados — usa `offset` na chamada seguinte ou ajusta `limit`. Para explorar página completa sem modo compacto, podes enviar `summarize: false` com `limit` moderado (atenção ao tamanho da resposta).

**Dados e LLM:** o texto em «Dados resumidos» no contexto do modelo é produzido pelo **DataInterpreter** (pré-visualização por linhas completas + metadados), não por truncar JSON bruto por caracteres.

**System prompt e perfil de tarefa:** a mensagem `system` do chat vem de `ORION_LLM_SYSTEM_PROMPT` (`Settings.llm_system_prompt`; por defeito alinhada a limites de verdade e pragmatismo). Antes de `decide()`, o estado ganha `entities["task_profile"]` via heurística determinística descrita em [`docs/heurística_de_tomada_de_decisão.md`](heurística_de_tomada_de_decisão.md); esse perfil é incluído no contexto enviado ao modelo.

**Carregamento de `.env`:** o `Settings` lê `.env` no CWD e, em seguida, `orion_mcp/.env` na raiz do repositório (este último sobrepõe o primeiro). Variáveis já definidas no ambiente do processo sobrepõem ambos. Reinicia o servidor após alterar `ORION_LLM_HALT_BEFORE_CHAT` (o `get_settings()` usa cache em memória).

**Docker e `llm_debug_log_file`:** com a imagem por defeito (`WORKDIR /app`), o caminho devolvido é tipicamente `/app/logs/....json` **dentro do contentor**. Para listar: `docker exec -it <container_api> ls -la /app/logs` (caminho absoluto com `/` inicial; `app/logs` sem barra falha). O `docker/docker-compose.yml` monta `orion_mcp/logs` no host em `/app/logs` para editar os JSON no repo.

**Export de dataset completo:** não há rota dedicada nesta versão; usa paginação ou ferramentas externas se precisares do ficheiro integral.

Alias opcional: `POST /api/chat` e `POST /api/chat/stream` quando `ORION_API_ENABLE_LEGACY_CHAT_ALIAS=true`.

---

**`payload.perf` (opcional, Secção 3):** mapa de avisos de degradação do turno (valores `true` apenas). Chaves estáveis:

- `tool_timeout` — execução da tool excedeu `ORION_TOOL_TIMEOUT_SECONDS`.
- `llm_budget_exhausted` — limite `ORION_MAX_LLM_CALLS_PER_REQUEST` atingido antes da resposta LLM.
- `context_truncated` — contexto ou prompt final foi truncado ao teto de tokens (`ORION_LLM_PROMPT_TOKEN_BUDGET`, ou `min(ORION_CONTEXT_MAX_TOKENS, ORION_LLM_MAX_PROMPT_TOKENS)` se o canónico estiver vazio).
- `llm_timeout` — pedido HTTP ao modelo excedeu `ORION_OPENAI_HTTP_TIMEOUT_SECONDS`.
- `mcp_unavailable` — cliente gRPC para o serviço MCP falhou (circuito aberto / erro) e foi usada resposta parcial da tool (`ORION_MCP_GRPC_*`).
- `llm_debug_halt` — `ORION_LLM_HALT_BEFORE_CHAT=true`: o LLM não foi chamado; o pedido foi gravado em ficheiro JSON sob `ORION_LLM_DEBUG_LOG_DIR` (caminho também em `payload.llm_debug_log_file`). O JSON inclui `extra` com snapshot do estado (`data_cache`, `metrics_tool_calls`, truncagens de contexto, etc.).
- **Trace opcional:** `ORION_ORCHESTRATOR_CHAT_TRACE=true` regista linhas JSON no logger `orion_mcp.orchestration` após cada `_prepare_turn` e no halt, e grava ficheiros `trace_context_<kind>_<transport>_*.txt` em `ORION_LLM_DEBUG_LOG_DIR` com **system** + **user** enviados ao LLM; no log aparece `event: trace_context_file` com o `path`. **Docker:** o orquestrador corre só no contentor **`api`**; o compose fixa `ORION_LLM_DEBUG_LOG_DIR=/app/logs` e monta `orion_mcp/logs` → `/app/logs`, por isso os `.txt` e JSON aparecem em `orion_mcp/logs/` no host após `docker compose up`.

O mesmo conteúdo é persistido em `state.flags["perf"]` para o turno seguinte (além de `force_refresh` quando aplicável).

**MCP remoto:** com `ORION_MCP_GRPC_TARGET` definido (ex.: `mcp-grpc:50051`), a tool de analytics executa no processo MCP via gRPC; consultas catalogadas usam `run_domain_query`. Ver `docs/ARCHITECTURE.md` e `.env.example`.

**Tetos LLM (resumo):** `ORION_LLM_PROMPT_TOKEN_BUDGET` (tokens estimados; teto canónico do prompt + `cap_llm_prompt`). Se vazio, usa-se `min(ORION_CONTEXT_MAX_TOKENS, ORION_LLM_MAX_PROMPT_TOKENS)`. **`ORION_LLM_CONTEXT_MAX_CHARS`** (opcional): por pedido HTTP ao chat, garante `len(system)+len(user)` ≤ valor; omissão = sem este corte por caracteres (mantêm-se os tetos por tokens). **Dados catalogados (caracteres):** `ORION_TOOL_LLM_SUMMARY_MAX_CHARS` ou alias `ORION_LLM_TOOL_CONTEXT_CHARS`; se omitidos, o valor deriva do orçamento de prompt (`× 4 × 0.6`, teto 100000). `ORION_LLM_COMPLETION_MAX_TOKENS` controla a geração do chat; `ORION_LLM_INSIGHTS_MAX_TOKENS` a chamada insights. Outras: `ORION_TOOL_LLM_PREVIEW_ROWS` (1–10000; também no MCP com `summarize=true`), `ORION_TOOL_DOMAIN_DEFAULT_LIMIT`, `ORION_TOOL_DOMAIN_DEFAULT_SUMMARIZE`, `ORION_MCP_DEBUG_STDOUT`, `ORION_CONTEXT_SECTION_BUDGET_TOKENS` (soma de secções; efectivo `min` com o teto de prompt).
