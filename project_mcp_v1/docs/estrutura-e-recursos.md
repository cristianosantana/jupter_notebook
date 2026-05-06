# Estrutura do repositório e recursos MCP

## Visão geral

O projeto é uma **API FastAPI** que orquestra um **agente** (OpenAI + loop de ferramentas) ligado a um **servidor MCP** em processo separado (stdio). O servidor MCP expõe ferramentas (tools) e **recursos** (resources) para consultas analíticas sobre uma base MySQL e utilitários como data/hora.

```txt
project_mcp_v1/
├── app/                 # Aplicação HTTP e agente
├── ai_provider/         # Abstração do modelo LLM
├── mcp_client/          # Cliente MCP (stdio + sampling)
├── mcp_server/          # Servidor MCP (FastMCP + SQL + MySQL)
├── exemplos/            # Material didático (notebook, queries de referência)
├── docs/                # Esta documentação
├── run.py               # Entrada: uvicorn
├── requirements.txt
└── .env                 # Credenciais (não versionar segredos)
```

---

## Responsabilidades por diretório

### `app/`

| Ficheiro | Responsabilidade |
|----------|------------------|

| `main.py` | FastAPI: startup (OpenAI, MCP client, orquestrador), `POST /chat`, shutdown. Injeta variáveis MySQL no ambiente para o subprocesso MCP. |
| `orchestrator.py` | **Agent loop**: mensagens → `model.chat` → se houver `tool_calls`, executa MCP → mensagens `role: tool` → repete até resposta só texto. Mantém histórico com TTL e limite de mensagens. Devolve `tools_used` por pedido. |
| `config.py` | `pydantic-settings`: `OPENAI_*`, `MYSQL_*` a partir de `.env` / ambiente. |
| `mcp_sampling.py` | Implementa o **callback MCP sampling**: pedidos `sampling/createMessage` do servidor → `AsyncOpenAI.chat.completions`. |

### `ai_provider/`

| Ficheiro | Responsabilidade |
|----------|------------------|

| `base.py` | Contrato `ModelProvider.chat(messages, tools)`. |
| `openai_provider.py` | Cliente OpenAI: converte ferramentas no formato MCP dump para o formato exigido pela API Chat Completions (`type: function`, `parameters`). |

### `mcp_client/`

| Ficheiro | Responsabilidade |
|----------|------------------|

| `client.py` | Arranca `mcp_server/server.py` com `sys.executable`, `ClientSession` com `sampling_callback` e capabilities de sampling. Expõe `list_tools` e `call_tool`. |

### `mcp_server/`

| Ficheiro / pasta | Responsabilidade   |
|------------------|--------------------|

| `server.py` | **FastMCP**: registo de tools, recurso template de analytics, `mcp.run()` em modo stdio. |
| `analytics_queries.py` | Constrói `QUERY_REGISTRY` e `TABULAR_MULTIROW_QUERY_IDS` a partir dos cabeçalhos YAML em `query_sql/*.sql`; `GLOBAL_PERIOD_HELP` e `format_catalog_for_model`. Espelho em [CATALOGO_ANALYTICS_MCP.md](CATALOGO_ANALYTICS_MCP.md). |
| `query_sql/` | SQL executável + cabeçalho `/* @mcp_query_meta */` (YAML: `resource_description`, `when_to_use`, `output_shape`, opcional `not_confused_with`). |
| `query_sql_meta.py` | Parser do cabeçalho YAML; usado por `analytics_queries.py` e `scripts/check_analytics_sql_meta.py`. |
| `sql_params.py` | Substituição validada de placeholders (ex.: `__MCP_DATE_FROM__` / `__MCP_DATE_TO__`). |
| `db.py` | Pool **aiomysql**, execução `SELECT * FROM (sql) LIMIT/OFFSET`, serialização JSON segura (ex.: `Decimal`). |
| `context_retrieval/` | Tools PostgreSQL: `context_embed_sessions`, `context_embed_messages`, `context_rebuild_kmeans`, `context_retrieve_similar` (ILIKE + embeddings); worker/CLI para batch. |

### Índice de contexto (operação)

- **Single-tenant:** contagem **global** de sessões com mensagens mas sem linha em `session_embeddings` dispara o gatilho quando ≥ `CONTEXT_INDEX_REBUILD_SESSION_THRESHOLD` (omissão **20**), ou quando o K-Means está *stale* por TTL (`CONTEXT_INDEX_KMEANS_TTL_DAYS`, omissão **5** dias). Estado em `context_index_state` (migração `003_context_index_state.sql`).
- **API (síncrono):** após `replace_conversation_messages`, [`app/context_index_service.py`](../app/context_index_service.py) chama as tools MCP com `asyncio.wait_for` e tecto `CONTEXT_INDEX_SYNC_TIMEOUT_SECONDS` / `CONTEXT_INDEX_EMBED_CAP_PER_TRIGGER`.
- **Cron (garantia):** **1× por dia** costuma ser suficiente; **2×** é opcional. Exemplo com raiz do projecto no `PYTHONPATH`: `python -m mcp_server.context_retrieval.cli` ou variáveis `CONTEXT_WORKER_*` em [`mcp_server/context_retrieval/worker.py`](../mcp_server/context_retrieval/worker.py).
- **Embeddings por mensagem** (`conversation_message_embeddings`, migração `002_context_retrieval.sql`): a tool **`context_embed_messages`** preenche a tabela por `(message_id, embedding_model)` para reduzir chamadas OpenAI no retrieve. Com **`CONTEXT_MESSAGE_EMBEDDINGS_ENABLED=true`**, `context_retrieve_similar` lê a cache (hit/miss), embeda só faltantes em blocos de até **`CONTEXT_MESSAGE_EMBED_BATCH_SIZE`**, e opcionalmente faz write-back se **`CONTEXT_MESSAGE_EMBED_WRITEBACK_ON_RETRIEVE=true`**. A resposta JSON inclui `message_embedding_cache` (`hits` / `misses`). Ingestão manual: `python scripts/embed_sessions_from_db.py --session-id … --messages`.

### `exemplos/`

Material de curso / referência (notebook, cópias de queries). O servidor MCP em produção usa **`mcp_server/query_sql/`**, não depende de `exemplos/` em runtime.

### Raiz

| Ficheiro | Responsabilidade |
|----------|------------------|

| `run.py` | `uvicorn.run(app, host="0.0.0.0", port=8000)`. |

---

## Recursos MCP (detalhado)

No protocolo MCP, **resources** são conteúdos endereçáveis por URI, normalmente só leitura. Aqui servem para o cliente (ou o LLM, via host) inspecionar o **SQL completo** de cada análise sem inflar a descrição das tools.

### Template de URI

Há **um** template registado:

| Campo | Valor  |
|-------|--------|

| **URI template** | `analytics://query/{query_id}` |
| **Nome** | `analytics_query_sql` |
| **Descrição (MCP)** | SQL completo com filtros de período `__MCP_DATE_FROM__` / `__MCP_DATE_TO__` (substituídos em `run_analytics_query` com `date_from` / `date_to`). |

O parâmetro `{query_id}` deve ser um dos identificadores abaixo. Uma leitura bem-sucedida devolve **texto plano** com o SQL (comentário de cabeçalho + placeholders de período em todas as análises atuais).

### Instâncias válidas (`query_id`)

Cada linha corresponde a **uma** análise; o conteúdo do recurso é o ficheiro homónimo em `mcp_server/query_sql/`.

| `query_id` | Conteúdo semântico do SQL (resumo)  |
|------------|-------------------------------------|

| `cross_selling` | Pares de serviços na mesma OS, ranking por concessionária e mês. |
| `taxa_retrabalho_servico_produtivo_concessionaria` | Retrabalho vs serviço produtivo por concessionária e período. |
| `taxa_conversao_servico_concessionaria_vendedor` | Conversão de serviço por concessionária e vendedor. |
| `servicos_vendidos_por_concessionaria` | Mix de serviços e participação percentual por concessionária e mês. |
| `sazonalidade_por_concessionaria` | Padrão sazonal de volume/OS por concessionária. |
| `performance_vendedor_mes` | KPIs de vendedor por **mês** (YYYY-MM): OS, faturamento, ticket, desconto, serviços por OS. |
| `performance_vendedor_ano` | Mesmas KPIs agregadas por **ano civil** (YYYY) no intervalo de datas. |
| `faturamento_ticket_concessionaria_periodo` | Faturamento de serviços, quantidade de OS e ticket médio por concessionária e mês. |
| `faturamento_mensal_recebidos_pendentes` | Por mês de competência: OS distintas, total recebido, pendente e faturamento previsto (tabelas `caixas` / `caixas_pendentes`). |
| `faturamento_mensal_recebidos_pendentes_por_concessionaria` | Igual à anterior com GROUP BY por concessionária (`concessionarias.nome`); uma linha por mês e loja. |
| `distribuicao_ticket_percentil` | Distribuição de ticket por quartis (NTILE) por concessionária. |
| `propenso_compra_hora_dia_servico` | Propensão de compra por hora, dia da semana e tipo de serviço. |
| `volume_os_concessionaria_mom` | Volume de OS por concessionária com variação MoM; resultado JSON (`resultado`). Ver [30_QUERIES_OTIMIZADAS.md](30_QUERIES_OTIMIZADAS.md) Query 1. |
| `volume_os_vendedor_ranking` | Ranking de vendedores por volume de OS (JSON). Ver [30_QUERIES_OTIMIZADAS.md](30_QUERIES_OTIMIZADAS.md) Query 2. |
| `ticket_medio_concessionaria_agg` | Ticket médio e dispersão por concessionária (JSON). Ver [30_QUERIES_OTIMIZADAS.md](30_QUERIES_OTIMIZADAS.md) Query 3. |
| `ticket_medio_vendedor_top_bottom` | Top 5 e bottom 5 vendedores por ticket médio (JSON). Ver [30_QUERIES_OTIMIZADAS.md](30_QUERIES_OTIMIZADAS.md) Query 4. |
| `taxa_conversao_servicos_os_fechada` | Taxa conversão serviços/OS fechada, global e por concessionária (JSON). Ver [30_QUERIES_OTIMIZADAS.md](30_QUERIES_OTIMIZADAS.md) Query 5. |

### Como o host usa os recursos

- Na listagem MCP (`resources/templates`), aparece o template `analytics://query/{query_id}`.
- Para obter o SQL: **read resource** com URI concreta, por exemplo `analytics://query/cross_selling`.
- A tool `list_analytics_queries` devolve um catálogo em texto com os mesmos ids e URIs sugeridas.

### Relação com as tools

- **Recurso** = documentação / transparência do que o servidor pode executar (SQL bruto ou com placeholders).
- **Tool `run_analytics_query`** = execução controlada no MySQL (whitelist, `LIMIT`/`OFFSET`, substituição de placeholders validados).

---

## Ferramentas MCP (resumo)

Para detalhe de argumentos e exemplos HTTP no host, ver [tecnologias-padroes-e-exemplos.md](tecnologias-padroes-e-exemplos.md).

| Tool | Função |
|------|--------|

| `get_current_time` | Data/hora ISO do servidor. |
|--------------------|----------------------------|

| `list_analytics_queries` | Catálogo textual das análises e URIs de recurso. |
|--------------------------|--------------------------------------------------|

| `run_analytics_query` | Executa uma análise por `query_id` com `date_from` / `date_to` obrigatórios. |
|-----------------------|------------------------------------------------------------------------------|
