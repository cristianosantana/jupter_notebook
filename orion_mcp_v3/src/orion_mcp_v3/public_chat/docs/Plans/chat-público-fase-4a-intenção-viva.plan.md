---
name: Chat Público Fase 4A
overview: "Enriquecer IntentContract com operation e dimension; heurística local; semantic_hash e topic que distinguem perguntas semanticamente diferentes — intenção viva até ao cache."
todos:
  - id: f4a-contract
    content: IntentContract + parser — campos operation, dimension, sort_direction
    status: pending
  - id: f4a-heuristics
    content: domain/intent_heuristics.py — sinais pior/melhor/forma pagamento (sem import runtime)
    status: pending
  - id: f4a-prompt
    content: public_chat_intent.yaml — ranking_asc/desc, dimension, distinção comparacao vs ranking
    status: pending
  - id: f4a-hash-topic
    content: normalize_contract_for_hash + resolve_topic incluem operation/dimension
    status: pending
  - id: f4a-logging
    content: snapshot_intent() + logs intent.interpret com novos campos
    status: pending
  - id: f4a-tests
    content: tests/phase4a/ — parser, hash, topic, heurística
    status: pending
isProject: false
---

# Fase 4A — Intenção Viva

**Índice:** [Fase 4 — Contexto focalizado](chat-público-fase-4-contexto-focalizado.plan.md)

**Pré-requisito:** Fase 3 concluída.

**Próxima sub-fase:** [4B Preparação do documento](chat-público-fase-4b-preparação-documento.plan.md) ou [4C Selecção](chat-público-fase-4c-selecção-contexto.plan.md) (4C requer 4B).

---

## Responsabilidade semântica

> **Capturar o que o utilizador quer saber** — não responder, não seleccionar secções.

Corrige a perda de intenção entre a pergunta e o cache/narrador. No log actual, `"pior forma pagamento março"` vira `comparacao + periodo:2026-03` — colide com qualquer pergunta genérica sobre março.

---

## Escopo IN

| Item | Ficheiro |
|---|---|
| Campos `operation`, `dimension` | `domain/intent_contract.py` |
| Parser + hash canónico | `domain/intent_parser.py`, `domain/semantic_hash.py` |
| Topic enriquecido | `domain/topic_resolver.py` |
| Heurística pré-LLM | `domain/intent_heuristics.py` **(novo)** |
| Prompt intent | `prompts/public_chat_intent.yaml` |
| Interpreter passa sinais ao LLM | `infrastructure/intent_interpreter.py` |
| Snapshot logging | `infrastructure/pipeline_snapshots.py` |
| Testes | `tests/phase4a/` **(novo)** |

## Escopo OUT

- Section parser, period scoper, context selector, narrator QA
- Alterações no `ConsultaTurnRunner` (excepto persistência de contrato já existente)
- Nova chamada LLM além do intent interpreter actual

---

## Contrato alvo

```python
operation: str | None   # ranking_asc | ranking_desc | list | summary | comparison
dimension: str | None   # forma_pagamento | concessionaria | servico | produto | ...
```

Mapeamento prompt/heurística:
- `pior`, `menor`, `mínimo` → `ranking_asc`
- `melhor`, `maior`, `top`, `dominante` → `ranking_desc`
- `forma de pagamento` → `dimension: forma_pagamento`

Hash inclui `operation` + `dimension` → `"resumo março"` ≠ `"pior forma pagamento março"`.

Topic: `forma_pagamento:2026-03` em vez de `periodo:2026-03`.

---

## DoD (Definition of Done)

- [ ] `"qual a forma de pagamento foi pior em março de 2026?"` → `operation: ranking_asc`, `dimension: forma_pagamento`, `period: 2026-03`
- [ ] `semantic_hash` diferente para pergunta genérica vs ranking sobre o mesmo mês
- [ ] `resolve_topic()` → `forma_pagamento:2026-03`
- [ ] Log `intent.interpret` inclui `operation` e `dimension` no `contract`
- [ ] `pytest public_chat/tests/phase4a/` verde
- [ ] Regressão phases 1–3 verde (contrato retrocompatível via defaults `null`)

---

## Testes mínimos

- `test_intent_ranking_asc_pior`
- `test_semantic_hash_distinguishes_questions`
- `test_topic_includes_dimension`
- `test_heuristics_pior_maps_ranking_asc`
- `test_contract_backward_compatible_defaults`
