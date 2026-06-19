---
name: Chat Público Fase 4C
overview: "Context Selector — LLM escolhe secções relevantes a partir de catálogo parseado; não responde, não narra, não interpreta negócio."
todos:
  - id: f4c-models
    content: domain/selected_context.py — SelectedContext + parse resposta JSON do selector
    status: pending
  - id: f4c-selector
    content: infrastructure/context_selector.py — PublicContextSelector.select()
    status: pending
  - id: f4c-prompt
    content: prompts/public_chat_context_selector.yaml + registry.yaml
    status: pending
  - id: f4c-trace
    content: Eventos selector.select pre/post (ids, reason, degraded)
    status: pending
  - id: f4c-tests
    content: tests/phase4c/ — mock LLM, fallback degraded, integração parser+scoper
    status: pending
isProject: false
---

# Fase 4C — Selecção de Contexto

**Índice:** [Fase 4 — Contexto focalizado](chat-público-fase-4-contexto-focalizado.plan.md)

**Pré-requisito:** [4A Intenção viva](chat-público-fase-4a-intenção-viva.plan.md) + [4B Preparação do documento](chat-público-fase-4b-preparação-documento.plan.md)

**Próxima sub-fase:** [4D Resposta focalizada](chat-público-fase-4d-resposta-focalizada.plan.md)

---

## Responsabilidade semântica

> **Escolher quais secções do documento são relevantes à pergunta** — reduzir ~100% do relatório para ~5%.

Não codifica `resolver_pior_forma_pagamento()`. O selector recebe catálogo de títulos+previews e devolve IDs de secções.

---

## Escopo IN

| Item | Ficheiro |
|---|---|
| Modelo de saída | `domain/selected_context.py` **(novo)** |
| Selector LLM | `infrastructure/context_selector.py` **(novo)** |
| Prompt | `prompts/public_chat_context_selector.yaml` **(novo)** |
| Registry | `prompts/registry.yaml` |
| Settings opcional | `config/settings.py` — `selector_max_tokens` |
| Testes | `tests/phase4c/` **(novo)** |

## Escopo OUT

- Narrator QA, runner wiring completo
- Period scoper / section parser (consumidos, não alterados)

---

## API

```python
@dataclass(frozen=True)
class SelectedContext:
    sections: tuple[DocumentSection, ...]
    selection_reason: str | None
    degraded: bool = False

class PublicContextSelector:
    async def select(
        self,
        message: str,
        *,
        contract: IntentContract,
        documents: tuple[ParsedDocument, ...],
    ) -> SelectedContext: ...
```

---

## Prompt (regras)

- Entrada: `user_message`, `intent_contract`, `available_sections[]` (id, title, preview ~200 chars)
- Saída JSON: `{ "selected_section_ids": ["s1"], "reason": "..." }`
- **Proibido:** responder, calcular rankings, resumir
- Preferir 1–2 secções
- Usar `operation`/`dimension` do contrato como sinal

**Fallback:** JSON inválido ou 0 secções → `degraded=True`, todas secções do documento scoped (comportamento 4B only) + log `selector.degraded`.

---

## DoD

- [ ] Mock LLM: pergunta forma pagamento pior → selecciona só `"Formas de pagamento"`
- [ ] Fallback degraded testado
- [ ] Log `selector.select` com ids, reason, degraded, section_count
- [ ] `pytest public_chat/tests/phase4c/` verde
- [ ] Test harness compõe 4A contract + 4B parse/scope + 4C select (sem runner ainda)

---

## Testes mínimos

- `test_context_selector_picks_payment_section`
- `test_context_selector_fallback_degraded`
- `test_context_selector_uses_contract_dimension`
- `test_selector_prompt_forbids_answering` (assert system prompt)
