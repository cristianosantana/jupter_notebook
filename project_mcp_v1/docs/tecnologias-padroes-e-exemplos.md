# Tecnologias, padrões de projeto, configuração e exemplos

## Tecnologias (stack)

| Camada | Tecnologia | Versão (referência) | Uso |
|--------|------------|---------------------|-----|

| API HTTP | FastAPI | 0.135.x | Rotas, lifecycle, JSON. |
| Servidor ASGI | Uvicorn | 0.42.x | Execução da app (`run.py`). |
| LLM | OpenAI API | SDK openai 2.30.x | Chat completions + tools; sampling via callback. |
| Validação / settings | Pydantic v2, pydantic-settings | 2.12.x / 2.13.x | Corpos de pedido, `Settings` + `.env`. |
| Protocolo agente ↔ ferramentas | MCP (Model Context Protocol) | `mcp` 1.26.x | Servidor FastMCP (stdio), `ClientSession`. |
| Base de dados | MySQL | — | Consultas analíticas somente leitura. |
| Driver async MySQL | aiomysql | 0.2.x | Pool e cursores dict no servidor MCP. |
| Concorrência | anyio / asyncio | — | I/O assíncrono ponta a ponta na API e no cliente. |
| HTTP cliente | httpx | 0.28.x | Dependência transitiva típica (OpenAI). |

Ferramentas listadas em `requirements.txt` mas não no núcleo do fluxo chat+MCP: **Typer**, **Rich**, **Loguru** (úteis para CLI/logging se extenderes o projeto).

---

## Padrões de projeto

### 1. Separação host vs servidor MCP

- O **host** (FastAPI) não executa SQL diretamente: fala com o processo MCP via stdio.
- **Benefício**: isolamento, mesma superfície MCP que outros clientes (Cursor, Claude Desktop, etc.) poderiam usar.

### 2. Agent loop (reasoning loop)

- O orquestrador implementa o ciclo clássico: utilizador → modelo → (opcional) tools → resultados → modelo até resposta final.
- Limite de segurança: `MAX_TOOL_ROUNDS` evita loops infinitos.

### 3. Provider de modelo (`ModelProvider`)

- Abstração em `ai_provider/base.py`; implementação OpenAI converte tools MCP → formato OpenAI.
- Facilita trocar de provedor mantendo o orquestrador.

### 4. Whitelist de SQL

- Apenas SQL carregado de `mcp_server/query_sql/` com `query_id` conhecido.
- Não há execução de SQL arbitrário vindo do LLM.

### 5. Agregação no servidor de dados

- As queries são pensadas com `GROUP BY`, janelas, etc., para reduzir volume devolvido; ainda assim aplica-se `LIMIT`/`OFFSET` no wrapper.

### 6. MCP Sampling

- O servidor MCP pode pedir ao **cliente** uma conclusão LLM (`create_message`); o cliente traduz para OpenAI.
- Permite resumos sem inflar o contexto do utilizador na primeira instância (quando `summarize=true` na tool).

### 7. Histórico com TTL e integridade de tools

- Timestamps paralelos às mensagens; remoção por idade (`MAX_MESSAGE_AGE_SECONDS`) e por contagem (`MAX_HISTORY_MESSAGES`).
- Evita-se começar o histórico com mensagem `tool` sem o assistente correspondente.

### 8. Configuração por ambiente

- Segredos e URLs em `.env`, mapeados por `pydantic-settings` e, para o subprocesso MCP, `os.environ.setdefault` no startup da FastAPI.

---

## Variáveis de ambiente (obrigatórias / usuais)

| Variável | Onde | Descrição |
|----------|------|-----------|

| `OPENAI_API_KEY` | Host | Chave da API OpenAI. |
| `OPENAI_MODEL` | Host | Modelo (ex.: `gpt-4o-mini`). Usado no provider e no sampling. |
| `MYSQL_HOST` | Servidor MCP (herdado do processo pai) | Host MySQL. |
| `MYSQL_PORT` | Idem | Porta (default comum 3306). |
| `MYSQL_USER` | Idem | Utilizador. |
| `MYSQL_PASSWORD` | Idem | Palavra-passe. |
| `MYSQL_DATABASE` | Idem | **Obrigatório** para `run_analytics_query` executar queries. |

Os campos em `app/config.py` (`mysql_*`, `openai_*`) leem o mesmo `.env`; o `main.py` copia-os para `os.environ` antes de arrancar o MCP.

---

## API HTTP — exemplos

Base URL de exemplo: `http://localhost:8000` (definido em `run.py`).

### `POST /chat`

**Request** (JSON):

```http
POST /chat HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "message": "Que horas são no servidor?"
}
```

**Response** `200` (exemplo quando o modelo chamou `get_current_time`):

```json
{
  "reply": "No servidor são cerca das 15:42 (horário local).",
  "tools_used": [
    {
      "name": "get_current_time",
      "arguments": {},
      "ok": true,
      "error": null,
      "result_preview": "2026-03-29T15:42:01.123456"
    }
  ]
}
```

**Response** `200` quando o modelo **não** chama tools neste turno (pode ainda usar histórico antigo):

```json
{
  "reply": "Com base nos dados anteriores, o ticket médio subiu no último trimestre.",
  "tools_used": []
}
```

**Campos da resposta:**

| Campo | Tipo | Descrição |
|-------|------|-----------|

| `reply` | string | Texto final do assistente (`content` da última mensagem). |
| `tools_used` | array | Só ferramentas **executadas neste** `POST`. Cada item: `name`, `arguments`, `ok`, `error`, `result_preview` (truncado). |

**Erros comuns:**

| Situação | Comportamento típico |
|----------|----------------------|

| Agente não inicializado | `500` / `RuntimeError` em desenvolvimento. |
| OpenAI rejeita pedido | Exceção da SDK (tratar com middleware em produção). |
| MySQL indisponível | JSON de erro dentro do resultado da tool `run_analytics_query`, ou falha na chamada MCP. |

---

## Ferramentas MCP relevantes para integradores

### `run_analytics_query`

Argumentos principais:

| Argumento | Tipo | Notas |
|-----------|------|-------|

| `query_id` | string (enum) | Um dos 9 ids documentados em [estrutura-e-recursos.md](estrutura-e-recursos.md). |
| `limit` | int | Máximo 10000 (clamp no servidor). |
| `offset` | int | Paginação. |
| `summarize` | bool | Se true, tenta MCP sampling para resumo (requer cliente com sampling). |
| `date_from` / `date_to` | string opcional | **Obrigatórios** para `faturamento_ticket_concessionaria_periodo` (`YYYY-MM-DD`). |

Exemplo de **argumentos** (como o LLM envia na `tool_call`):

```json
{
  "query_id": "faturamento_ticket_concessionaria_periodo",
  "date_from": "2024-01-01",
  "date_to": "2024-12-31",
  "limit": 50,
  "offset": 0
}
```

Corpo de retorno da tool: string JSON com `query_id`, `limit`, `offset`, `row_count`, `rows`, e opcionalmente `llm_summary`.

---

## Como executar localmente

```bash
cd project_mcp_v1
python -m venv .venv && source .venv/bin/activate   # opcional
pip install -r requirements.txt
# Preencher .env (OPENAI_*, MYSQL_*)
python run.py
```

Teste rápido:

```bash
curl -s -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Diz a hora exata do servidor MCP."}' | jq .
```

---

## Segurança e operações (checklist)

- Utilizador MySQL com permissões **mínimas** (idealmente só `SELECT` nas tabelas necessárias).
- Não commitar `.env` com segredos (usar `.gitignore`).
- `tools_used` pode conter **argumentos** de tools; em produção filtra campos sensíveis se expuseres a API a terceiros.
- O histórico do agente é **em memória** por processo; reiniciar o servidor apaga conversas.

---

## O que mais costuma constar em documentação (referência)

- **Diagrama de sequência**: Cliente → FastAPI → OpenAI → MCP → MySQL (opcional para evolução).
- **Versionamento de API**: prefixo `/v1/chat` se houver breaking changes.
- **Limites de taxa** e autenticação na API (não implementados neste projeto base).
- **Changelog** ou notas de release ao alterar `query_id` ou contratos JSON.
