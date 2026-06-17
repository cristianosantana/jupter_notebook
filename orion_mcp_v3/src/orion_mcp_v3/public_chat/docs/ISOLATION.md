# Isolamento do módulo

## Regras

1. **Nenhum import** de `broker`, `memory` analítico, `api/routes/chat`, `connection_hub`, `infra/postgres` global, `orion_mcp_v3.prompts`, `orion_mcp_v3.config.settings`.
2. **Migrações, pool, settings e testes** vivem dentro de `public_chat/`.
3. **O núcleo Orion** não importa `public_chat` até wiring explícito na fase 3.
4. **Documentação** do produto consultivo fica em `public_chat/docs/`.

## Guardrails automatizados

`tests/phase1/test_guardrails.py` verifica imports proibidos no código de produção (exclui pasta `tests/`).

## Dependência partilhada

`orion_mcp_v3.protocols.llm.LLMProvider` — contrato fino para providers LLM já existentes no monólito. Substituível por protocol local quando o módulo for extraído.
