---
name: Chat Público Fase 4B
overview: "Preparação determinística do conhecimento recuperado — filtrar documento por período e dividir validated_answer em secções nomeadas, sem LLM e sem regras analíticas."
todos:
  - id: f4b-section-parser
    content: domain/section_parser.py — DocumentSection, ParsedDocument, split por headers
    status: pending
  - id: f4b-period-scoper
    content: domain/knowledge_scoper.py — filtro hits por contract.period / context_key
    status: pending
  - id: f4b-trace
    content: Eventos pipeline section.parse e knowledge.scope
    status: pending
  - id: f4b-tests
    content: tests/phase4b/ — parser multi-secção + scoper 5 meses → 1 março
    status: pending
isProject: false
---

# Fase 4B — Preparação do Documento

**Índice:** [Fase 4 — Contexto focalizado](chat-público-fase-4-contexto-focalizado.plan.md)

**Pré-requisito:** Fase 3 concluída. **Independente de 4A** (pode correr em paralelo).

**Próxima sub-fase:** [4C Selecção de contexto](chat-público-fase-4c-selecção-contexto.plan.md)

---

## Responsabilidade semântica

> **Transformar retrieval bruto em documentos estruturados e filtrados** — sem escolher secção, sem responder.

Resolve dois problemas do log:
1. **5 meses** carregados quando a pergunta é só março → period scoper
2. **Relatório monolítico** → section parser divide em árvore de secções

```text
Documento Março
├─ Formas de Pagamento
├─ Tipos de Venda
├─ Concessionárias
├─ Serviços
...
```

---

## Escopo IN

| Item | Ficheiro |
|---|---|
| Modelos de secção | `domain/section_parser.py` **(novo)** |
| Filtro por período | `domain/knowledge_scoper.py` **(novo)** |
| Trace | `infrastructure/pipeline_trace.py` / `pipeline_snapshots.py` |
| Testes + fixture fechamento março | `tests/phase4b/` **(novo)** |

## Escopo OUT

- Context Selector (LLM)
- Narrator, runner wiring
- Intent contract (usa `period` quando disponível; funciona com `period=None` → fallback score)

---

## Section parser

```python
@dataclass(frozen=True)
class DocumentSection:
    id: str              # estável dentro do documento, ex. "s1"
    title: str
    body: str
    source_hit_id: int
    context_key: str

@dataclass(frozen=True)
class ParsedDocument:
    context_key: str
    source_hit_id: int
    sections: tuple[DocumentSection, ...]
```

Split heurístico (genérico, não negócio):
- Headers: linhas Title Case, terminam em `:`, padrões fechamento (`Formas de pagamento`, `Produção por serviço`, `Top N`, `Parcelamento`)
- Fallback: secção única `"documento"`

API: `parse_document(hit: KnowledgeHit) -> ParsedDocument`

---

## Period scoper

```python
def scope_knowledge(
    knowledge: ConhecimentoRecuperado,
    *,
    period: str | None,
) -> tuple[ConhecimentoRecuperado, bool]:  # (scoped, degraded)
```

Regras:
1. `period == "2026-03"` → hits com `2026-03` ou `marco_2026` no `context_key`
2. Fallback: hit de maior `score` + `degraded=True`

API: `scope_knowledge(knowledge, period=contract.period)`

---

## DoD

- [ ] Fixture fechamento março → ≥ 5 secções nomeadas incluindo `"Formas de pagamento"`
- [ ] 5 hits (jan–mai) + `period=2026-03` → 1 hit março
- [ ] Fallback degraded quando period não matcha nenhum hit
- [ ] Logs `section.parse` (count) e `knowledge.scope` (before/after hit_count)
- [ ] `pytest public_chat/tests/phase4b/` verde
- [ ] Zero imports proibidos; sem LLM

---

## Testes mínimos

- `test_section_parser_splits_fechamento`
- `test_section_parser_fallback_single_section`
- `test_period_scoper_filters_march`
- `test_period_scoper_degraded_fallback`
