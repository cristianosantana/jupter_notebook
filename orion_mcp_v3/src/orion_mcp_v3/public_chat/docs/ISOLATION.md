# Isolamento do módulo

## Regras

1. **Nenhum import** de `broker`, `memory` analítico, `api/routes/chat`, `connection_hub`, `infra/postgres` global, `orion_mcp_v3.prompts`, `orion_mcp_v3.config.settings`, `orion_mcp_v3.providers`.
2. **Migrações, pool, settings e testes** vivem dentro de `public_chat/`.
3. **Wiring Orion → public_chat** só via `public_chat/integration/fastapi.py` (`mount_public_chat`); `main.py` importa apenas esse módulo.
4. **Documentação** do produto consultivo fica em `public_chat/docs/`.

## Guardrails automatizados

`tests/phase1/test_guardrails.py` verifica imports proibidos no código de produção (exclui pasta `tests/`).

## Dependências partilhadas

| Import | Motivo |
|---|---|
| `orion_mcp_v3.protocols.llm.LLMProvider` | interface fina para intent + narrador |

Embeddings e LLM OpenAI: implementação **100% interna** em `infrastructure/embedding/` e `infrastructure/llm/`.
