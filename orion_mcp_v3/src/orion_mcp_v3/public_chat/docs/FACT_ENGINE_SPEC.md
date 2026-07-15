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

### Requirements dinâmicos (`dynamic:*`)

O `FactPlanner` gera `fact_key` compostos quando há múltiplos operandos ou varredura multi-período:

| Padrão | Exemplo | Quando |
|---|---|---|
| `dynamic:{index_key}` | `dynamic:faturamento_por_tipo_de_pagamento` | lookup simples, 1 entidade implícita |
| `dynamic:{index_key}@{entity}` | `dynamic:faturamento_por_tipo_de_pagamento@pix` | comparação multi-entidade no mesmo índice |
| `dynamic:{index_key}@{entity}@{period}` | `dynamic:...@pix@2026-04` | varredura multi-mês × multi-entidade |

**Classificação de filtros no planner:**
- **Operando** — dimensão com ≥2 `entity_filters` (ex.: PIX vs Cartão) → 1 requirement por valor
- **Escopo** — dimensão com 1 valor fora dos operandos (ex.: concessionária GWM BAMAQ) → `scope_entities` no requirement; restringe linha/coluna na extração, não gera requirement próprio
- A dimensão-alvo do loop do planner **nunca** entra em `scope_entities` (evita duplicar operando e escopo)

**Eixos de escopo schema-aware (fonte única):**
- Função canónica: `scope_axes_for_entry(entry)` / `scope_axes_from_hit_meta(hit, matched_key)` — derivam eixos válidos de `dimension`, `subdimension` e `entity_field` do `_meta` do índice
- Só filtros cuja dimensão ∈ eixos válidos são aplicados na extração; os restantes vão para `discarded_scope` com `reason: not_in_schema` (telemetria em `fact.plan` e `FactTrace`, não é gap)
- `FactSemantics.key_metrics_scope_axes` é **snapshot audit-only** gravado no build — o extrator **recomputa** eixos via `scope_axes_from_hit_meta`, não usa semantics para decidir filtro
- Exemplo: `parcelamento_de_cartao` só aceita escopo `parcelas`; `forma_pagamento` do intent é descartado, não filtra linhas por substring inexistente no label

**Invariante — zero é fact válido:**
- Valor numérico zero (`0.0`, `R$ 0,00`) é fact válido em `LOOKUP`; gap só quando a linha/entidade não existe (`None`)
- Casos de negócio frequentes: financiamento zerado, Cheque/Permuta sem movimento, matriz `tipo_os × concessionaria`
- Tabelas com `subdimension` expandem N valores monetários por linha física (`table_rows_sample` com múltiplos `R$` por linha)
- Filtros-predicado (ex. `>0`) nunca viram `entity`; permanecem em `discarded_scope` até suporte a filtro condicional pós-extração

**Resolução de origem no plano:**
- `source_resolution_mode: index_pinned` quando `source_origin_id` vem do índice
- `source_resolution_mode: catalog_fallback` + `source_resolution_detail` (ex.: `no_index_entry_for_period:2026-04`) quando o planner delega ao catálogo

**Expansão de período (proibido colapsar):**
- Se `contract.period` é `null` e o índice traz o mesmo `entry.key` em N meses, o planner **expande** em N requirements (um por período distinto), cada um com `source_origin_id` e `period` explícitos
- **Proibido:** escolher um `origin_id` arbitrário ou “período mais recente” quando a pergunta não fixa um único mês — isso viola *nunca inventar valor*

Exemplos canónicos:

| fact_key | aggregation | comparator | source_priority |
|---|---|---|---|
| `faturamento_total_periodo` | LOOKUP | NONE | key_metrics → parsed_text |
| `ranking_forma_pagamento` | MIN | asc | structured → parsed_text |
| `participacao_oficina` | DERIVED | NONE | — (oficina / total) |

## Fact Resolution Trace

Dois tipos separados evitam serialização enganosa no JSONL de `fact.resolve`:

### `ResolutionTrace` (só resolução — evento `fact.resolve`)

Gravado no **exact return** de cada branch do `FallbackPolicy` / `MemoryResolver`:

- `CATALOG` / `VECTOR_RETRIEVAL` — `FallbackPolicy._pick_hit_for_themes`
- `CATALOG` — `MemoryResolver._resolve_from_source_origin_id` quando o planner já fixou `source_origin_id` (ex.: `match_method: meta_exact`)

- `fact_key`
- `resolved_from`: origin_ids
- `context_keys`
- `rule_applied`: CATALOG | VECTOR_RETRIEVAL | LLM_FALLBACK | JOIN_PLAN
- `semantics_version`

**Sem** `extraction_path` — a extracção ainda não ocorreu.

### `FactTrace` (resolução + extracção — evento `fact.extract`)

Estende `ResolutionTrace` com:

- `extraction_path`: KEY_METRICS | STRUCTURED_PARSER | RANKING_DERIVED | LLM_EXTRACT | DERIVED_COMPUTE
- `discarded_scope` (opcional): filtros de escopo rejeitados por não pertencerem ao schema do `matched_key`

Montado **somente** quando o `FactExtractor` extrai valor com sucesso, mergeando
`resolution_trace` do hit resolvido com o path real do branch vencedor em `source_priority`.

Logging JSONL (5E): `fact.plan`, `fact.join_plan`, `fact.resolve`, `fact.extract`, `workspace.build`.

| Evento | Trace serializado |
|---|---|
| `fact.resolve` | `ResolutionTrace[]` por requirement |
| `fact.extract` | `FactTrace` completo nos facts; gaps com `attempted_rules` + `resolution_trace` opcional |

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
| `NOT_IN_CATALOG` | fact_key estático ausente de `fact_semantics.yaml` (facts `dynamic:*` **não** disparam este reason — têm semântica inline no `FactRequirement`) |
| `NO_MEMORY_FOUND` | zero hits no período |
| `MEMORY_EXISTS_BUT_NO_MATCH` | hit errado tema/entity/key_metrics |
| `PARTIAL_MATCH_ONLY` | key_metrics vazio, só texto |
| `EXTRACTION_FAILED` | hit estruturalmente plausível mas extractor falhou |
| `LOW_CONFIDENCE` | abaixo threshold |

Gaps de resolução/extracção incluem `attempted_rules` (rules avaliadas no `FallbackPolicy`)
e, quando aplicável, `resolution_trace` do último hit tentado.

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
| Catálogo encontra theme + key_metrics compatível | Resolver; trace `CATALOG` ou `VECTOR_RETRIEVAL` |
| Catálogo ok, vector tem hit elegível | Preferir ordem vector; trace `VECTOR_RETRIEVAL` |
| Memórias existem mas nenhum hit casa (tema/key/período) | Gap `MEMORY_EXISTS_BUT_NO_MATCH` + `attempted_rules` |
| Hit resolvido, extractor falha | Gap `EXTRACTION_FAILED` + `attempted_rules` + `resolution_trace` |
| Nunca inventar valor | Gap `NO_MEMORY_FOUND` |

`LLM_FALLBACK` reservado no enum e em `attempted_rules`; implementação real fora de escopo v1.

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
