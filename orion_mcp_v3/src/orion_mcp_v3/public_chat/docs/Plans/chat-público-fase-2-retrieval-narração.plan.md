---
name: "Chat Público Fase 2"
overview: "Leitura remissiva (memory_*), narrador, ConsultaTurnRunner caminho cache-miss — retrieve, narrar, gravar answer_payload. Sem cache hit nem API."
todos:
  - id: f2-remissive-reader
    content: PublicRemissiveReader (SQL próprio) + RemissiveRetriever retrieve/reload_from_payload
    status: pending
  - id: f2-narrator
    content: prompt public_chat_narrator.yaml + infrastructure/narrator.py
    status: pending
  - id: f2-response-store-cache
    content: ResponseStore — find/upsert resolution, link pivot, knowledge_fingerprint
    status: pending
  - id: f2-runner-miss
    content: ConsultaTurnRunner v1 — só cache miss (intent → miss → retrieve → narrate → persist)
    status: pending
  - id: f2-tests
    content: Testes phase2 + auditoria + guardrail sem embedding em public_chat_*
    status: pending
isProject: false
---

# Fase 2 — Retrieval Remissivo e Narração

**Pré-requisito:** [Fase 1 concluída](chat-público-fase-1-fundação-intenção.plan.md) — domain, intent, perguntas persistidas.

**Próxima fase:** [Fase 3 — Cache Hit e API](chat-público-fase-3-api-cache.plan.md)

Plano mestre: [chat_público_remissivo_03507a27.plan.md](chat_público_remissivo_03507a27.plan.md)

---

## Objetivo da fase

Completar o **caminho cache miss**: após interpretar intenção, buscar conhecimento em `memory_*`, narrar e **persistir resolução** (`answer_payload` + `knowledge_fingerprint`) — **sem** atalho de cache hit, **sem** API HTTP.

Fluxo entregue:

```
pergunta → intent → (topic, semantic_hash)
  → cache lookup → SEMPRE miss (ou runner ignora hit)
  → memory_embeddings retrieval
  → PublicNarrator
  → upsert public_chat_responses + pivot + presentation_delivered
```

---

## Escopo IN

| Item | Detalhe |
|---|---|
| `infrastructure/remissive_reader.py` | SQL read-only; **não** altera `RemissiveMemoryStore` |
| `infrastructure/remissive_retriever.py` | `retrieve()` + `reload_from_payload()` |
| `infrastructure/narrator.py` | `PublicNarrator.stream()` |
| `prompts/public_chat_narrator.yaml` | Apresentação only |
| `response_store.py` | Completar: `find_resolution`, `upsert_resolution`, `link_question_response` |
| `application/consulta_turn_runner.py` | **v1** — ramo miss apenas |
| `application/factory.py` | `build_runner_miss_only()` para testes |

## Escopo OUT

- Ramo cache hit no runner (reload sem retrieval)
- `POST /api/v1/public/ask`
- Wiring `main.py` / `ORION_PUBLIC_CHAT_ENABLED`
- `presentation_snapshot` optimization

---

## Princípios (herdados do plano mestre)

- **Único índice semântico:** `memory_embeddings` — vetores **não** em `public_chat_*`
- **Tópico:** só do contrato — `category` do hit não altera `topic`
- **Cache:** `answer_payload` + `knowledge_fingerprint` — narrativa regenerável
- **EmbeddingService:** só dentro de `PublicRemissiveReader` para `memory_embeddings`

---

## Entregáveis

```
src/orion_mcp_v3/public_chat/
  infrastructure/
    remissive_reader.py       # NOVO
    remissive_retriever.py    # NOVO
    narrator.py               # NOVO
    response_store.py         # ESTENDIDO
  application/
    consulta_turn_runner.py   # NOVO (v1 miss-only)
    factory.py                # NOVO (parcial)
```

---

## ConsultaTurnRunner v1 (pseudo)

```python
async def run_turn_miss_only(message, parent_question_id=None):
    contract = await intent_interpreter.interpret(...)
    topic = resolve_topic(contract)
    semantic_hash = build_semantic_hash(contract)
    question_id = await store.insert_question(...)
    # find_resolution → sempre tratar como miss em v1
    knowledge = await retriever.retrieve(message)
    async for delta in narrator.stream(message, knowledge):
        yield delta
    payload = build_answer_payload(knowledge)
    k_fp = build_knowledge_fingerprint(knowledge)
    response_id = await store.upsert_resolution(topic, semantic_hash, payload, k_fp)
    await store.link_question_response(question_id, response_id, is_repeat=False, ...)
```

---

## Critérios de conclusão

- [ ] `retrieve()` usa `memory_embeddings` com `ivfflat.probes`; sem filtro `user_id`
- [ ] `reload_from_payload()` carrega por `knowledge_ids` (testado; usado plenamente na fase 3)
- [ ] Narrador não inventa fatos — só `validated_answer` / `key_metrics` / essence
- [ ] Fallback sem hits remissivos
- [ ] `upsert_resolution` grava `answer_payload` + `knowledge_fingerprint` — sem `content` como fonte
- [ ] Auditoria: pergunta → contrato → payload → `presentation_delivered`
- [ ] `category` do hit **não** altera `topic` persistido na pergunta
- [ ] `pytest tests/focused/public_chat/phase2/` verde
- [ ] Fase 1 tests continuam verdes

---

## Testes desta fase (`tests/focused/public_chat/phase2/`)

| Teste | Verifica |
|---|---|
| `test_remissive_reader_global` | SQL sem `user_id`; set_config probes |
| `test_remissive_reader_readonly` | Sem writes em `memory_*` |
| `test_retriever_returns_knowledge` | Mock pool → ConhecimentoRecuperado |
| `test_reload_from_payload` | Carrega por knowledge_ids |
| `test_narrator_fallback_no_hits` | Mensagem fixa sem hits |
| `test_narrator_stream_mock_llm` | Deltas SSE |
| `test_knowledge_fingerprint_changes` | Conteúdo diferente → hash diferente |
| `test_upsert_resolution_payload` | answer_payload gravado |
| `test_category_divergence_contract_wins` | topic imutável pós-retrieval |
| `test_audit_chain_miss_path` | 4 elos da auditoria |
| `test_no_semantic_cache_on_responses` | Sem embedding/HNSW em public_chat_* |
| `test_synonymy_via_remissive_on_miss` | Contratos distintos, mesmo knowledge via vectors |
| `test_runner_miss_end_to_end` | Mock full pipeline miss |

---

## Ordem de implementação

1. `remissive_reader.py` + testes
2. `remissive_retriever.py` + testes
3. `public_chat_narrator.yaml` + `narrator.py`
4. Estender `response_store.py` (resolution + pivot)
5. `consulta_turn_runner.py` v1
6. `factory.py` parcial
7. Suite `phase2/`

---

## Dependências de config

Para testes de integração com Postgres + embeddings (opcional nesta fase):

- `ORION_POSTGRES_URL`
- `ORION_LLM_API_KEY` (narrator + intent)
- `embedding_active` para retrieval real

Testes unitários com mocks são suficientes para DoD.
