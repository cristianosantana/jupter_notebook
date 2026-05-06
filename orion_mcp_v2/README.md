# Orion MCP v2

Pacote paralelo a `orion_mcp/` com memória curta Redis, Celery Beat para consolidação noturna e catálogo MySQL com allowlist. O fluxo HTTP mantém-se: decisão determinística → SQL → [`run_data_pipeline`](src/orion_mcp_v2/core/data_engine/pipeline.py) → LLM.

**Agregados por query (`skill_aggregate`)**: para `query_id` com agregador registado (p.ex. `cross_selling` em [`core/aggregators/`](src/orion_mcp_v2/core/aggregators/)), o pipeline adiciona um bloco JSON compacto ao resultado e o user prompt inclui a secção «Agregados específicos». **Pandas** está nas dependências principais do pacote; sem ele, a instalação normal não deveria falhar, mas se faltar de propósito o merge regista `skill_aggregate_error` em vez de calcular agregados. O servidor MCP expõe as tools `aggregate_for_query_id` e `list_aggregatable_queries` (allowlist: só ids com agregador e presentes no catálogo SQL).

**Lookups ID → nome**: o ficheiro [`skill/reference_lookups.md`](src/orion_mcp_v2/skill/reference_lookups.md) é **anexado automaticamente** ao system prompt pelo orquestrador (`reference_lookups_loader`). Opcional: `ORION_V2_REFERENCE_LOOKUPS_FILE`, `ORION_V2_REFERENCE_LOOKUPS_MAX_CHARS`, `ORION_V2_REFERENCE_LOOKUPS_ENABLED` — ver [`.env.example`](.env.example).

## Três serviços isolados (deploy)

| Serviço | Processo | Entrypoint típico |
|--------|----------|-------------------|
| **A — API** | FastAPI apenas (sem MCP no mesmo processo) | `uvicorn orion_mcp_v2.main:app` ou [`run_server.py`](run_server.py) |
| **B — MCP Server** | FastMCP + MySQL (read-only) | `python -m orion_mcp_v2.mcp_server_standalone` |
| **C — MCP Client** | Só SDK cliente (`fastmcp.Client`) | [`scripts/mcp_remote_client.py`](scripts/mcp_remote_client.py) |

Imagens distintas: [`docker/Dockerfile.api`](docker/Dockerfile.api), [`docker/Dockerfile.mcp-server`](docker/Dockerfile.mcp-server), [`docker/Dockerfile.mcp-client`](docker/Dockerfile.mcp-client). Compose de exemplo na raiz do pacote: [`docker-compose.yml`](docker-compose.yml).

## Variáveis de ambiente (resumo)

Prefixo geral da API: `ORION_V2_`. Copie [`.env.example`](.env.example) para `.env` e ajuste.

### API (Serviço A)

| Variável | Descrição |
|----------|-----------|
| `ORION_V2_DATABASE_URL` | Postgres (asyncpg), ex. `postgresql://user:pass@host:5432/db` |
| `ORION_V2_DB_REQUIRED` | `true`/`false` — falhar arranque se PG obrigatório |
| `ORION_V2_MYSQL_URL` | MySQL do orquestrador (queries catalogadas) |
| `ORION_V2_REDIS_URL` | Memória curta / rate limit |
| `ORION_V2_OPENAI_API_KEY` | Se vazio, o LLM usa modo mock em dev |
| `ORION_V2_OTEL_ENABLED` | `true` activa tracing OTEL (consola) no lifespan da API |
| `ORION_V2_LLM_IO_DUMP_ENABLED` | `true` grava JSON por chamada LLM (prompt + `response_raw`) em `ORION_V2_LLM_IO_DUMP_DIR` (só no processo que chama o LLM, i.e. **API**). |
| `ORION_V2_LLM_IO_DUMP_DIR` | Directório dos ficheiros (em Docker, monte volume para o host, ex. `/tmp/orion_mcp_v2_llm_io`). |
| `ORION_V2_AGENT_DEBUG_NDJSON_ENABLED` | `true` grava NDJSON com contexto completo antes do LLM (orquestrador); também activa se `LLM_IO_DUMP_ENABLED=true`. |
| `ORION_V2_AGENT_DEBUG_LOG_PATH` | Caminho do NDJSON (default `/tmp/orion_mcp_v2_agent_debug.ndjson` no container). |

Orçamento opcional do prompt: `ORION_V2_LLM_CONTEXT_MAX_CHARS`, `ORION_V2_LLM_PROMPT_TOKEN_BUDGET`, `ORION_V2_CONTEXT_SECTION_BUDGET_TOKENS` (ver `config/settings.py`).

### Servidor MCP (Serviço B)

| Variável | Descrição |
|----------|-----------|
| `ORION_V2_MCP_SRV_MYSQL_URL` | MySQL para o executor MCP (preferido para este processo) |
| `ORION_V2_MYSQL_URL` | Fallback se a anterior não estiver definida |
| `ORION_V2_MCP_SRV_HOST` | Bind HTTP, ex. `0.0.0.0` |
| `ORION_V2_MCP_SRV_PORT` | Porta, ex. `8765` |
| `ORION_V2_MCP_SRV_TRANSPORT` | `sse` (remoto), `stdio` (dev), ou `http` / `streamable-http` |

### Cliente MCP (Serviço C)

| Variável | Descrição |
|----------|-----------|
| `MCP_SERVER_URL` | URL SSE do FastMCP, ex. `http://localhost:8765/sse` ou `http://mcp-server:8765/sse` em Docker |

### Chat HTTP (`POST /api/v1/chat` e `/chat/stream`)

- `session_id` e `user_id` são **opcionais** na primeira mensagem; o servidor gera UUIDs e devolve-os no JSON (e `user_id` no evento SSE `done`).
- Nos pedidos seguintes envie pelo menos `session_id` (e `user_id` se não existir estado persistido — por exemplo sem Postgres). Com Postgres activo, só `session_id` + `message` pode bastar para recuperar o `user_id` da sessão guardada.

## Arranque rápido (API local)

```bash
cd orion_mcp_v2
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # editar segredos
python scripts/migrate.py
python run_server.py    # http://0.0.0.0:8010
```

## Servidor MCP (SSE) local

Com MySQL acessível e URL configurada:

```bash
export ORION_V2_MCP_SRV_MYSQL_URL='mysql://user:pass@localhost:3306/db'
# ou: export ORION_V2_MYSQL_URL='...'
python -m orion_mcp_v2.mcp_server_standalone
```

Por defeito escuta em `ORION_V2_MCP_SRV_HOST` / `ORION_V2_MCP_SRV_PORT` (ver `.env.example`).

## Smoke do cliente MCP

Com o **Serviço B** já a correr e a aceitar SSE:

```bash
chmod +x scripts/smoke_mcp_client.sh
export MCP_SERVER_URL=http://127.0.0.1:8765/sse
./scripts/smoke_mcp_client.sh
```

Saída esperada: JSON com a lista de nomes das tools (`run_analytics_query`, `list_analytics_queries`, …).

## Docker Compose (três serviços)

Na pasta `orion_mcp_v2`:

```bash
docker compose up --build
```

**Rede externa:** o [`docker-compose.yml`](docker-compose.yml) junta os serviços à rede `docker-env_cs_backend` (tem de existir). Para aceder a Postgres/MySQL/Redis noutro stack (contentores `cs_postgres`, `cs_mysql`, `cs_redis`), coloque no `.env` esses **nomes como host** — por exemplo `postgresql://...@cs_postgres:5432/...` e `redis://cs_redis:6379/0`. Dentro de um contentor, `localhost` aponta só para o próprio contentor.

- **api**: porta `8010` (define Postgres/MySQL/Redis via [.env.example](.env.example) copiado para `.env`).
- **mcp-server**: porta `8765` — MySQL via `ORION_V2_MYSQL_URL` / `ORION_V2_MCP_SRV_MYSQL_URL` (mesmo padrão de host `cs_mysql` em Docker).
- **mcp-client**: executa o smoke contra `http://mcp-server:8765/sse` (só faz sentido se o servidor MCP subir com MySQL válido).

## Testes

```bash
pip install -e ".[dev]"
pytest
# Com pandas/sklearn (extras analytics): pip install -e ".[dev,analytics]"
# Integração MCP (requer Serviço B a correr): MCP_SERVER_URL=http://host:8765/sse pytest -m integration
```
