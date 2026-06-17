---
name: "Chat Público Fase 3"
overview: "Cache hit + ConsultaTurnRunner v2, API POST /ask SSE, integração via public_chat/integration/ — isolamento total, settings PUBLIC_CHAT_*, testes em public_chat/tests/phase3/."
todos:
  - id: f3-settings
    content: PublicChatSettings — PUBLIC_CHAT_ENABLED + USE_PRESENTATION_SNAPSHOT (sem OrionSettings)
    status: pending
  - id: f3-runner-hit
    content: ConsultaTurnRunner v2 — cache hit + knowledge_fingerprint staleness
    status: pending
  - id: f3-factory
    content: factory.py — build_public_chat_runner() completo
    status: pending
  - id: f3-api
    content: public_chat/api/ schemas + routes POST /ask SSE
    status: pending
  - id: f3-integration
    content: public_chat/integration/fastapi.py mount_public_chat + cola mínima main.py
    status: pending
  - id: f3-tests-e2e
    content: Testes public_chat/tests/phase3/ + regressão fases 1-2
    status: pending
isProject: false
---

# Fase 3 — Cache Hit, API e Integração

**Pré-requisito:** [Fase 2 concluída](chat-público-fase-2-retrieval-narração.plan.md) — retrieval, narrador, persistência miss.

Plano mestre: [chat_público_remissivo_03507a27.plan.md](chat_público_remissivo_03507a27.plan.md)

> Plano canónico sincronizado com `.cursor/plans/chat-público-fase-3-api-cache.plan.md`

---

## Objetivo da fase

Produto **completo** e exposto — **tudo dentro de `public_chat/`**, com cola mínima no Orion:

```
POST /api/v1/public/ask
  → intent → cache exato (topic, semantic_hash)?
       ├─ hit  → reload_from_payload → verificar knowledge_fingerprint → narrar → is_repeat=true
       └─ miss → retrieve → narrar → upsert cache → is_repeat=false
  → SSE + question_id + thread_id para follow-up
```

---

## Isolamento (obrigatório)

| Dentro de `public_chat/` | Fora / proibido importar |
|---|---|
| API, runner v2, factory, settings, testes | `OrionSettings`, `orion_mcp_v3.config.settings` |
| `integration/fastapi.py` — único ponto de cola | `broker/`, `memory/`, `api/routes/chat.py` |
| Settings `PUBLIC_CHAT_*` apenas | `ORION_PUBLIC_CHAT_*` — **não criar** |
| Testes em `public_chat/tests/phase3/` | `tests/focused/public_chat/` (legado) |

**Fora de `public_chat/` (mínimo):** `api/main.py` — 1 import + 1 chamada `mount_public_chat`.

---

## Escopo IN

| Item | Detalhe |
|---|---|
| `consulta_turn_runner.py` | **v2** — `run_turn()` hit + miss |
| `application/factory.py` | `build_public_chat_runner()` completo |
| `public_chat/api/schemas.py` | `AskRequest`, eventos SSE |
| `public_chat/api/routes.py` | `create_public_ask_router(runner)` |
| `public_chat/integration/fastapi.py` | `mount_public_chat(app, shared_state, llm_provider?)` |
| `config/settings.py` | `PUBLIC_CHAT_ENABLED`, `PUBLIC_CHAT_USE_PRESENTATION_SNAPSHOT` |
| `main.py` | Só chama `mount_public_chat` |

## Escopo OUT

- Campos `ORION_PUBLIC_CHAT_*` em `OrionSettings`
- Rotas em `orion_mcp_v3/api/routes/`

---

## Settings (`PUBLIC_CHAT_*`)

| Variável | Default |
|---|---|
| `PUBLIC_CHAT_ENABLED` | `false` |
| `PUBLIC_CHAT_USE_PRESENTATION_SNAPSHOT` | `false` |
| Demais vars | já existem em Fase 1–2 |

Pré-requisitos: `settings.enabled and settings.postgres_enabled and settings.llm_enabled and settings.embedding_enabled`

---

## Wiring

`mount_public_chat` em `public_chat/integration/fastapi.py`; `main.py` só invoca essa função.

---

## Testes

`src/orion_mcp_v3/public_chat/tests/phase3/` + regressão phase1/2.

Ver plano completo em `.cursor/plans/chat-público-fase-3-api-cache.plan.md` para critérios DoD, ordem de implementação e smoke test.
