---
name: Chat Público Fase 1
overview: Fundação do módulo public_chat/ — schema, domain, interpretador de intenção (LLM), encadeamento parent_question_id. Sem retrieval, narrador nem API HTTP.
todos:
  - id: f1-migration
    content: Migração 015_public_chat_schema.sql + teste estático (semantic_hash, UNIQUE topic+hash, sem embedding)
    status: completed
  - id: f1-domain
    content: domain/ — models, intent_contract, semantic_hash, topic_resolver, intent_parser, knowledge_fingerprint
    status: completed
  - id: f1-intent-llm
    content: prompt public_chat_intent.yaml + infrastructure/intent_interpreter.py
    status: completed
  - id: f1-context-store
    content: application/context_window.py + ResponseStore (só perguntas + ancestor chain)
    status: completed
  - id: f1-tests
    content: Testes fase 1 + guardrails isolamento (sem imports analíticos)
    status: completed
isProject: false
---

# Fase 1 — Fundação e Intenção

**Pré-requisito:** nenhum (primeira fatia).

**Próxima fase:** [Fase 2 — Retrieval e Narração](chat-público-fase-2-retrieval-narração.plan.md)

Plano mestre: [chat_público_remissivo_03507a27.plan.md](chat_público_remissivo_03507a27.plan.md)

---

## Objetivo da fase

Entregar o **esqueleto consultivo** e o **pipeline de intenção** completo, persistindo perguntas com encadeamento — **sem** consultar `memory_*`, **sem** narrador, **sem** cache de resolução, **sem** rota HTTP.

Ao final desta fase você consegue (via testes):

```
pergunta (+ parent_question_id?)
  → cadeia ancestral
  → LLM → contrato
  → topic + semantic_hash
  → INSERT public_chat_questions
```

---

## Escopo IN

| Item | Detalhe |
|---|---|
| Migração `015` | Schema **completo** (questions + responses + pivot) — responses vazia até fase 2/3 |
| `public_chat/domain/` | Todos os módulos de domínio |
| `public_chat/infrastructure/intent_interpreter.py` | LLM + parser |
| `prompts/public_chat_intent.yaml` + `registry.yaml` | Prompt dedicado |
| `application/context_window.py` | `load_ancestor_chain` |
| `infrastructure/response_store.py` | **Parcial:** `insert_question`, `load_ancestor_chain`, regras `thread_id` |
| `public_chat/__init__.py` | Pacote vazio inicial |

## Escopo OUT (fases seguintes)

- `PublicRemissiveReader` / `RemissiveRetriever`
- `PublicNarrator`
- `ConsultaTurnRunner` completo
- Uso de `public_chat_responses` (cache)
- `POST /api/v1/public/ask`
- Wiring em `main.py`
- Settings `ORION_PUBLIC_CHAT_ENABLED` (opcional stub em fase 1)

---

## Entregáveis por pasta

```
src/orion_mcp_v3/public_chat/
  __init__.py
  domain/
    models.py
    intent_contract.py
    semantic_hash.py
    topic_resolver.py
    intent_parser.py
    knowledge_fingerprint.py      # só função pura + testes; uso pleno na fase 2
  infrastructure/
    intent_interpreter.py
    response_store.py           # métodos de pergunta/ancestral apenas
  application/
    context_window.py
```

---

## Critérios de conclusão (Definition of Done)

- [x] Migração aplicável sem erro; teste estático passa
- [x] `build_semantic_hash()` estável para contratos equivalentes
- [x] `resolve_topic()` só do contrato — sem input de `memory_*`
- [x] `PublicIntentInterpreter` com mock LLM retorna contrato válido
- [x] Raiz: `parent_question_id=NULL`, `thread_id=id` após insert
- [x] Follow-up: herda `thread_id`, `parent_question_id` válido
- [x] `parent_question_id` inválido → exceção/erro de domínio (HTTP 400 na fase 3)
- [x] Guardrail: `public_chat/*` não importa `broker`, `RemissiveMemoryStore`, `chat.py`
- [x] `pytest src/orion_mcp_v3/public_chat/tests/phase1/` verde

---

## Testes desta fase (`tests/focused/public_chat/phase1/`)

| Teste | Verifica |
|---|---|
| `test_migration_schema` | `semantic_hash`, `UNIQUE(topic, semantic_hash)`, sem embedding em `public_chat_*` |
| `test_semantic_hash_stable` | Contratos idênticos → mesmo sha256 |
| `test_semantic_hash_equivalent_phrasings` | 3 redações → mesmo hash (via parser mock) |
| `test_topic_from_contract_only` | Slug só de metric/period/domain |
| `test_intent_parser_valid_json` | Parse + normalização período |
| `test_intent_parser_invalid_json` | Fallback `geral` |
| `test_intent_interpreter_mock_llm` | Mock provider → contrato |
| `test_root_question_thread_id` | Raiz: thread_id = id |
| `test_follow_up_chain` | Herança thread_id + parent |
| `test_context_window_depth` | Trunca em `CONTEXT_DEPTH` |
| `test_guardrail_isolation` | Imports proibidos |
| `test_no_regression_analytical` | `chat.py` sem import `public_chat` |

---

## Ordem de implementação

1. Migração `015` + teste estático
2. `domain/` (models → contract → parser → hash → topic)
3. Prompt `public_chat_intent.yaml`
4. `intent_interpreter.py`
5. `response_store.py` (perguntas + ancestral)
6. `context_window.py`
7. Suite `phase1/` + guardrails

---

## Como validar manualmente (opcional)

```bash
pytest tests/focused/public_chat/phase1/ -v
# Aplicar migração se tiver Postgres local:
# python scripts/apply_migrations.py
```

Nenhum endpoint exposto nesta fase.
