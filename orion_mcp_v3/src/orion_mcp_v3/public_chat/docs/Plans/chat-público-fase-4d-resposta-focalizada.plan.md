---
name: Chat Público Fase 4D
overview: "Integrar pipeline completo no runner; Narrator em modo Question Answering sobre secções seleccionadas; critério de aceite E2E e guardrails."
todos:
  - id: f4d-narrator
    content: PublicNarrator — assinatura contract + SelectedContext; prompt QA anti-summary
    status: pending
  - id: f4d-runner
    content: ConsultaTurnRunner — scope → parse → select → narrate (hit e miss)
    status: pending
  - id: f4d-factory
    content: factory.py — wire PublicContextSelector
    status: pending
  - id: f4d-trace
    content: narrator.stream — selected_section_count, context_chars before/after
    status: pending
  - id: f4d-tests
    content: tests/phase4d/ — E2E pior forma pagamento + regressão 1–3 + guardrails
    status: pending
isProject: false
---

# Fase 4D — Resposta Focalizada

**Índice:** [Fase 4 — Contexto focalizado](chat-público-fase-4-contexto-focalizado.plan.md)

**Pré-requisito:** [4A](chat-público-fase-4a-intenção-viva.plan.md) + [4B](chat-público-fase-4b-preparação-documento.plan.md) + [4C](chat-público-fase-4c-selecção-contexto.plan.md)

---

## Responsabilidade semântica

> **Responder à pergunta literal** sobre contexto mínimo — Question Answering, não Executive Summary.

Integra todas as sub-fases no `ConsultaTurnRunner` e entrega o produto completo da Fase 4.

---

## Escopo IN

| Item | Ficheiro |
|---|---|
| Narrator QA | `infrastructure/narrator.py`, `prompts/public_chat_narrator.yaml` |
| Runner pipeline | `application/consulta_turn_runner.py` |
| Factory | `application/factory.py` |
| Trace enrich | `infrastructure/pipeline_snapshots.py` |
| Testes E2E | `tests/phase4d/` **(novo)** |

---

## Pipeline no runner

```
intent → (topic, semantic_hash)
→ retrieve / reload_from_payload
→ scope_knowledge(knowledge, contract.period)          # 4B
→ parse_documents(scoped_hits)                         # 4B
→ context_selector.select(message, contract, docs)     # 4C
→ narrator.stream(message, contract, selected)         # 4D
```

**Cache:** `answer_payload` inalterado (IDs brutos). Scope + select recomputados cada turno. Hash enriquecido (4A) evita colisões.

---

## Narrator QA

Entrada:
```json
{
  "user_message": "...",
  "intent_contract": { "operation": "ranking_asc", "dimension": "forma_pagamento", "period": "2026-03" },
  "context_sections": [{ "title": "Formas de pagamento", "body": "..." }]
}
```

Prompt:
- Primeira frase = resposta directa à pergunta
- Usar **só** `context_sections`
- Proibir: dominante, destaque, resumo executivo
- Zeros: excluir da resposta principal; nota breve Cheque/Permuta se existirem

O LLM **continua a raciocinar** (comparar valores) — sobre 1 secção, não 7.

---

## DoD (aceite global Fase 4)

Pergunta: *"qual a forma de pagamento foi pior em março de 2026?"*

- [ ] Log intent: `ranking_asc`, `forma_pagamento`, `2026-03`
- [ ] Scoper: 1 documento março
- [ ] Selector: secção pagamento only
- [ ] Resposta: **Depósito Bancário** R$ 3.690; nota zeros
- [ ] **Não** Cartão dominante, Parcelamento pior, secções serviço/produto
- [ ] `context_chars` narrador << chars documento completo (log)
- [ ] Cache hit e miss passam pelo pipeline selector
- [ ] `pytest public_chat/tests/phase4d/` + phases 1–3 + `test_guardrails.py` verdes

---

## Testes mínimos

- `test_narrator_prompt_contains_only_selected`
- `test_narrator_qa_not_summary`
- `test_runner_end_to_end_pior_forma_pagamento`
- `test_runner_cache_hit_recomputes_selection`
- Regressão phases 1–3
