# Chat Público (`public_chat`)

Módulo **totalmente isolado** do pipeline analítico Orion. Consulta exclusivamente conhecimento validado em `memory_*` — sem broker, sem MySQL, sem sessão conversacional.

## Princípio

> O Chat Público não é chatbot — é mecanismo de consulta sobre conhecimento destilado.

## Estrutura

```
public_chat/
  README.md                 ← este ficheiro
  .env.example
  config/                   ← settings próprios (PUBLIC_CHAT_*)
  docs/                     ← documentação do módulo
  domain/                   ← contrato, tópico, hash, regras puras
  application/              ← orquestração de turno
  api/                      ← POST /api/v1/public/ask (JSON)
  integration/              ← mount_public_chat (cola Orion)
  infrastructure/
    postgres/               ← pool, migrações, apply
    intent_interpreter.py
    response_store.py
    database.py             ← fábrica pool + store
  prompts/                  ← YAML + registry isolados
  scripts/                  ← apply_migrations
  tests/                    ← suite por fase
```

## Isolamento

| Dentro de `public_chat/` | Fora (proibido importar) |
|---|---|
| Postgres pool + migrações | `connection_hub`, `infra/postgres` global |
| Settings `PUBLIC_CHAT_*` | `orion_mcp_v3.config.settings` |
| Prompts + registry | `orion_mcp_v3.prompts` |
| Testes | `tests/focused/public_chat` (legado removido) |

Única dependência partilhada aceite: `orion_mcp_v3.protocols.llm` (interface `LLMProvider`).

## Configuração

Copie `.env.example` para `.env` na pasta `public_chat/` ou use variáveis no `.env` do projeto:

```bash
PUBLIC_CHAT_ENABLED=false
PUBLIC_CHAT_POSTGRES_URL=postgresql://postgres:secret@127.0.0.1:5432/dev
PUBLIC_CHAT_LLM_API_KEY=sk-...
PUBLIC_CHAT_CONTEXT_DEPTH=3
PUBLIC_CHAT_INTENT_MIN_CONFIDENCE=0.5
```

Com `PUBLIC_CHAT_ENABLED=true` e credenciais válidas, o endpoint fica disponível em `POST /api/v1/public/ask` (JSON).

## Migrações

```bash
cd orion_mcp_v3
python -m orion_mcp_v3.public_chat.scripts.apply_migrations
```

Ver [`infrastructure/postgres/migrations/README.md`](infrastructure/postgres/migrations/README.md).

## Testes

```bash
pytest src/orion_mcp_v3/public_chat/tests/phase1/ \
       src/orion_mcp_v3/public_chat/tests/phase2/ \
       src/orion_mcp_v3/public_chat/tests/phase3/ -v
```

## Fases de implementação

| Fase | Estado | Entrega |
|---|---|---|
| 1 | Concluída | Schema, domain, intent LLM, perguntas encadeadas |
| 2 | Concluída | Retrieval `memory_*`, narrador, runner cache-miss |
| 3 | Concluída | Cache hit, API `POST /ask`, wiring via `integration/` |

Documentação detalhada: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Logging do pipeline (ficheiro JSONL)

Eventos estruturados gravados em **ficheiro** (não no terminal). Logger: `orion.public_chat.pipeline` com `propagate=False`.

| Variável | Default |
|---|---|
| `PUBLIC_CHAT_PIPELINE_TRACE` | `true` |
| `PUBLIC_CHAT_PIPELINE_LOG_DIR` | `logs/public_chat` |

Ficheiro gerado por sessão uvicorn:

```
logs/public_chat/public_chat_pipeline_20260616T130209Z.jsonl
```

| Etapa | Onde |
|---|---|
| `api.ask` | Entrada/saída HTTP |
| `runner.turn` | Orquestração do turno |
| `context_window.load` | Cadeia ancestral |
| `intent.interpret` | LLM de intenção |
| `reader.search_origin_ids` | Busca vetorial |
| `retriever.retrieve` / `reload_from_payload` | Retrieval |
| `narrator.stream` | Narrativa |
| `runner.cache_hit` / `cache_miss` | Ramo de cache |

Cada pedido recebe um `trace_id` (UUID) correlacionado em todos os eventos do turno.

Eventos-chave para auditoria **pergunta → resposta**:

| Etapa | Conteúdo |
|---|---|
| `qa.turn_summary` | Pergunta, resposta, cache, memory_* consolidados |
| `memory.accessed` | Hits de `memory_curta` / `memory_essence` com métricas e previews |
| `cache.resolution` | Resultado do lookup `(topic, semantic_hash)` |
| `cache.stored` | Payload gravado em `public_chat_responses` |
| `reader.search_origin_ids` | Matches vetoriais (`memory_embeddings`) com scores |

Exemplo de linha no JSONL:

```json
{"canal":"public_chat_pipeline","etapa":"api.ask","fase":"post","trace_id":"...","dados":{"latency_ms":842.1,"cached":false}}
```

Desactivar gravação: `PUBLIC_CHAT_PIPELINE_TRACE=false`


## Como servir o orion_mcp_v3.public_chat com uvicorn?

Hoje **não existe** um alvo uvicorn dedicado tipo `orion_mcp_v3.public_chat:app`. O Chat Público expõe-se através da app Orion, via `mount_public_chat()` em `orion_mcp_v3.api.main:app`.

## Forma actual (recomendada)

Na raiz do repo (`orion_mcp_v3/`):

```bash
# 1. Instalar o pacote (se ainda não estiver)
pip install -e .

# 2. Migrações do public_chat (uma vez)
python -m orion_mcp_v3.public_chat.scripts.apply_migrations

# 3. Subir a API
uvicorn orion_mcp_v3.api.main:app --reload --host 0.0.0.0 --port 8000
```

Sem `pip install -e .`:

```bash
uvicorn --app-dir src orion_mcp_v3.api.main:app --reload --host 0.0.0.0 --port 8000
```

## Configuração

O `load_settings()` lê, por ordem:

1. `src/orion_mcp_v3/public_chat/.env`
2. `.env` na raiz do projeto

No mínimo:

```bash
PUBLIC_CHAT_ENABLED=true
PUBLIC_CHAT_POSTGRES_URL=postgresql://...
PUBLIC_CHAT_LLM_API_KEY=sk-...
PUBLIC_CHAT_EMBEDDING_API_KEY=sk-...   # ou reutiliza a LLM key
```

Com `PUBLIC_CHAT_ENABLED=true` e credenciais válidas, o endpoint fica em:

**`POST http://localhost:8000/api/v1/public/ask`**

Teste:

```bash
curl -X POST http://localhost:8000/api/v1/public/ask \
  -H 'Content-Type: application/json' \
  -d '{"message": "Qual o faturamento de maio de 2026?"}'
```

Resposta JSON (texto montado no servidor antes de devolver):

```json
{
  "message": "Faturamento líquido de maio de 2026: R$ 2.691.655",
  "finish_reason": "stop",
  "question_id": "...",
  "thread_id": "...",
  "cached": false,
  "topic": "faturamento:2026-05",
  "semantic_hash": "..."
}
```

## Notas

| Situação | Comportamento |
|---|---|
| `PUBLIC_CHAT_ENABLED=false` | `503 Public chat unavailable` |
| Postgres do Orion activo | `public_chat` reutiliza `shared_state["postgres_pool"]` |
| Postgres só do public_chat | Cria pool próprio via `PUBLIC_CHAT_POSTGRES_URL` |
| LLM | Usa `PUBLIC_CHAT_LLM_API_KEY` (provider interno) ou o provider injectado pelo Orion |

## Só o public_chat (sem pipeline analítico)

Não há `main.py` standalone no módulo. A app completa Orion sobe MySQL, chat analítico, etc. — mesmo que só uses `/api/v1/public/ask`.

Para servir **apenas** o public_chat, seria preciso um entrypoint novo (ex.: `orion_mcp_v3.public_chat.api.main:app` com FastAPI mínima + `mount_public_chat`). Isso ainda não está no repo.

Se quiseres, posso criar esse entrypoint isolado num próximo passo.