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
  api/                      ← POST /api/v1/public/ask (SSE)
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

Com `PUBLIC_CHAT_ENABLED=true` e credenciais válidas, o endpoint fica disponível em `POST /api/v1/public/ask` (SSE).

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
