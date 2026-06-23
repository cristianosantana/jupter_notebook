# Fact Engine Spec v1 — Chat Público Analítico

Contrato transversal para o pipeline remissivo: **Intent → Facts → Memories → Workspace → Answer**.

## Princípio

O Chat Público não pergunta *"qual documento ler?"* — pergunta *"quais fatos combinar?"*.

## Pipeline canónico

```text
Intent → FactPlanner → facts_needed
facts_needed → MemoryJoinPlan → MemoryResolver → memory_curta hits
hits → FactExtractor → RemissiveWorkspace
RemissiveWorkspace → AnalyticalNarrator → Resposta
```

## Separação de responsabilidades

| Camada | Pensa em | Não pensa em |
|---|---|---|
| `FactPlanner` | Necessidades analíticas (`facts_needed`) | Quais memórias existem |
| `MemoryJoinPlan` | Quais fontes combinar e por qual chave | Valores concretos |
| `MemoryResolver` | Quais `context_key`/hits satisfazem cada fact | Como responder |
| `FactExtractor` | Valores + confiança + trace | Sinónimos da pergunta |
| `AnalyticalNarrator` | Resposta a partir do workspace (RAW vs DERIVED) | SQL, novos factos |

## Fact Semantics

Cada `fact_key` declara o que é um fact válido — não só o nome.

Ficheiro: `config/fact_semantics.yaml`

Tipos em `domain/fact_engine/semantics.py`:
- `AggregationRule`: SUM, MAX, MIN, LAST, DERIVED, LOOKUP
- `Comparator`: ASC, DESC, NONE
- `SourcePriority`: KEY_METRICS → STRUCTURED → PARSED_TEXT → LLM

Exemplos canónicos:

| fact_key | aggregation | comparator | source_priority |
|---|---|---|---|
| `faturamento_total_periodo` | LOOKUP | NONE | key_metrics → parsed_text |
| `ranking_forma_pagamento` | MIN | asc | structured → parsed_text |
| `participacao_oficina` | DERIVED | NONE | — (oficina / total) |

## Fact Resolution Trace

Cada fact extraído carrega rastreabilidade em `FactTrace`:
- `resolved_from`: origin_ids
- `context_keys`
- `rule_applied`: CATALOG | VECTOR_RETRIEVAL | LLM_FALLBACK | JOIN_PLAN
- `extraction_path`: KEY_METRICS | STRUCTURED_PARSER | RANKING_DERIVED | LLM_EXTRACT | DERIVED_COMPUTE

Logging JSONL (5E): `fact.plan`, `fact.join_plan`, `fact.resolve`, `fact.extract`, `workspace.build`.

## MemoryJoin Strategy

`MemoryJoinPlan` planifica join entre memórias por `period` (extensível a entity).

Exemplo composta maio + oficina:

```yaml
period: "2026-05"
required_sources:
  - theme_slug: fechamento_gerencial
    fact_keys: [faturamento_total_periodo]
  - theme_slug: vendas_departamento
    fact_keys: [faturamento_departamento_oficina]
join_keys: [period]
```

## Gap Reason Codes

Substituem gaps opacos por `FactGap` tipado:

| Reason | Significado |
|---|---|
| `NOT_IN_CATALOG` | fact_key desconhecido |
| `NO_MEMORY_FOUND` | zero hits no período |
| `MEMORY_EXISTS_BUT_NO_MATCH` | hit errado tema/entity |
| `PARTIAL_MATCH_ONLY` | key_metrics vazio, só texto |
| `EXTRACTION_FAILED` | extractor falhou |
| `LOW_CONFIDENCE` | abaixo threshold |

## Confiança por camada

```python
EXTRACTION_CONFIDENCE = {
    KEY_METRICS: 0.95,
    STRUCTURED_PARSER: 0.75,
    RANKING_DERIVED: 0.85,
    DERIVED_COMPUTE: 0.90,
    LLM_EXTRACT: 0.70,
}
MIN_FACT_CONFIDENCE = 0.65
MIN_DERIVE_CONFIDENCE = 0.80
```

## Proof binding (FactType)

| Tipo | Narrador |
|---|---|
| `RAW` | Citável como hard truth |
| `DERIVED` | Citável com fórmula explícita |
| `ESTIMATED` | Linguagem cautelosa |

Proibido inventar `DERIVED` sem facts pai presentes no workspace.

## FallbackPolicy

Ordem fixa por fact_key:

1. Catálogo + SQL por period/theme (`MemoryJoinPlan`)
2. Se miss e catalog_hit_exists → merge vector_hits do retriever
3. Se still missing → LLM fact resolution (extract only)
4. Se still missing → `FactGap` com reason explícito

| Estado | Acção |
|---|---|
| Catálogo encontra theme + SQL hit | Extrair via source_priority |
| Catálogo ok, SQL miss, vector tem hit | Usar vector; trace `VECTOR_RETRIEVAL` |
| Hit existe, extractor falha | Gap `EXTRACTION_FAILED` |
| Nunca inventar valor | Gap `NO_MEMORY_FOUND` |

## Mapeamento EvidenceBlock ↔ RemissiveWorkspace

Não importar `EvidenceBlock` do Chat Analítico — equivalência documentada:

| EvidenceBlock (Chat Analítico) | RemissiveWorkspace (Chat Público) |
|---|---|
| `summary` | narrador sintetiza a partir de `facts[]` |
| `metrics` | `ExtractedFact[]` com `fact_type=RAW` |
| `insights` | `ExtractedFact[]` com `fact_type=DERIVED` |
| `supporting_data.direct_answer_set` | parser local em `validated_answer` |
| `coverage` | `confidence` agregada + `gaps[]` |
| `provenance` | `FactTrace.resolved_from` + `context_keys` |

**Regra Fase 6:** qualquer extensão a um lado deve actualizar esta tabela.

## Feature flag

| Flag | Comportamento |
|---|---|
| `PUBLIC_CHAT_USE_WORKSPACE=false` (default) | Fase 4 — section_parser + context_selector |
| `PUBLIC_CHAT_USE_WORKSPACE=true` | Fact Engine pipeline |

## Critérios de aceite

1. **Simples:** ranking forma pagamento março → Depósito Bancário; facts <500 chars no narrador
2. **Composta:** maio + oficina → 2 memórias, participação DERIVED
3. **Gap tipado:** memória departamento ausente → `NO_MEMORY_FOUND`
4. **Confiança:** derivado bloqueado se confiança insuficiente
