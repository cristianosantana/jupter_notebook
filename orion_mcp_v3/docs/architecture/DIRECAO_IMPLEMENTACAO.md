# Direcção de implementação — daqui para a frente

**Papel:** fixar o que “implementar” significa no Orion MCP v3 **depois** da separação entre núcleo analítico e Memory Augmentation (experimental).

**Documentos relacionados:**

- [`ORION_V3_MASTER_ARCHITECTURE.md`](./ORION_V3_MASTER_ARCHITECTURE.md) — índice mestre (infra × execução × cognição)
- [`MEMORY_AUGMENTATION_LAYER.md`](./MEMORY_AUGMENTATION_LAYER.md) — regras e modos do subsistema vectorial
- [`PLANO_EXECUCAO.md`](../execution/PLANO_EXECUCAO.md) — ordem incremental de entregas

---

## Leitura honesta do produto

O Orion **não** é um sistema de memória vetorial.

Está a evoluir para um **runtime cognitivo analítico** orientado por:

- atenção (`AttentionPolicy`, allocator, scheduler),
- proveniência (`CoverageInfo`, `ProvenanceAnchor`),
- destilação contextual (digest, map-reduce, evidence builder).

O valor cognitivo está no pipeline **dados → evidência → cognição → LLM**, não nos vectores.

```text
Core:     dados → evidência → cognição → contexto LLM
Optional: Memory Augmentation (pgvector, chat_turn_embeddings)
```

---

## O que já está no código (não reimplementar)

| Princípio | Onde |
|-----------|------|
| Embeddings opcionais | `ORION_EMBEDDING_MODE=off` por defeito em `config/settings.py` |
| Só indexar / só recuperar / ambos | `off` \| `index_only` \| `retrieve` |
| Retrieval fora do composer | `MemoryRetrievalPipeline` + `MemoryComposer` só compõe |
| Broker sem vector | Nenhum import de embeddings em `broker/` |
| Vector + lexical em paralelo | `api/routes/chat.py` (nunca substituir `SemanticRetriever`) |
| Subsistema congelado | `MEMORY_AUGMENTATION_LAYER.md` + README migrações 007/008 |

Com `embedding_mode=off`: memória episódica + lexical; **zero** chamadas à API de embeddings.

---

## O que “implementar” significa daqui para a frente

Não é construir mais pipeline vectorial. É **disciplina de produto e entregas no núcleo analítico**.

### Fazer (prioridade)

1. **Planner cognitivo** — `intent → analytical strategy` (`CognitivePlan` → `SemanticQueryPlan`).
2. **SemanticQueryPlan + compiler** — DSL, validação, templates SQL, trace `semantic_plan` antes de MySQL.
3. **Evidence builder** — baseline, variação, anomalias, confidence, coverage como motor de raciocínio analítico.
4. **Provenance + drift guard** — âncoras em evidence/digest; regressões na narração.
5. **Orquestração** — `CognitiveOrchestrator`, fusão, políticas de atenção (evidence acima de memória conversacional).
6. **Medir antes de expandir vector** — com `retrieve` activo, comparar no trace `memory_layer_vector` vs pipeline analytics (`evidence_builder`, `map_reduce_digest`).

### Não fazer (até decisão arquitectural explícita)

- Embedding-centric orchestration ou vector-first memory.
- “Semantic everything” (writer para `memory_embeddings` / migração 003 sem caso de uso analítico).
- Novos retrievers vector no `broker/`.
- Retrieval dentro do `MemoryComposer` ou do planner.
- Pipelines que **exijam** OpenAI embeddings para o `POST /chat` funcionar.
- Async no `runtime/` / `broker/` **só** por causa de embeddings.

### Manter (scope mínimo de Memory Augmentation)

| Componente | Ficheiro / tabela |
|------------|-------------------|
| `chat_turn_embeddings` | migrações 007, 008 |
| `ChatTurnEmbeddingStore` | `memory/chat_turn_embedding_store.py` |
| `VectorRetriever` | `memory/vector_retriever.py` |
| `MemoryRetrievalPipeline` | `memory/retrieval_pipeline.py` |

Sem novas features nesta camada enquanto o núcleo analítico não estiver maduro.

---

## Configuração recomendada (`.env`)

```env
# Produção — núcleo analítico sem vector (recomendado)
ORION_EMBEDDING_MODE=off

# Arquivo de turnos para sessões longas, sem busca vectorial no chat
# ORION_EMBEDDING_MODE=index_only

# Experimento: indexação + VectorRetriever em paralelo com lexical
# ORION_EMBEDDING_MODE=retrieve
```

Postgres + migrações 007/008 só são necessários com `index_only` ou `retrieve`.

Legado: `ORION_EMBEDDING_ENABLED=true` sem `EMBEDDING_MODE` equivale a `retrieve` — preferir definir o modo explicitamente.

---

## Fluxo de um turno (referência)

```text
POST /chat
  → IntentResolver → CognitivePlan
  → MemoryRetrievalPipeline (episódico + lexical; + vector se retrieve)
  → Analytics (se needs_analytics): planner → SQL → evidence → digest
  → CognitiveOrchestrator: fusão + allocator → prompt → LLM
  → (opcional) indexação em chat_turn_embeddings se index_only/retrieve
```

O trecho que importa nos logs de pipeline **não** é o vector retrieval isolado; é o ramo analytics (`mysql_analytics_select`, `evidence_builder`, `analytical_reduction_merge`, `map_reduce_digest`, `drift_guard`).

---

## Critérios de sucesso

- Com embeddings **off**: comportamento estável sem dependência externa de embed API.
- Com embeddings **on**: ganho mensurável em sessões longas; vector permanece camada pequena face à evidence.
- Roadmap e PRs priorizam planner / evidence / provenance **antes** de qualquer expansão pgvector.
- Nenhum módulo em `broker/` importa `memory/chat_turn_*` ou `providers/openai_embedding`.

---

## Melhorias opcionais (não bloqueantes)

| Ideia | Motivo |
|-------|--------|
| Indexação em background (`asyncio.create_task`) | Reduz latência do `POST /chat` em `index_only`/`retrieve` |
| Deprecar `ORION_EMBEDDING_ENABLED` | Um único knob: `ORION_EMBEDDING_MODE` |
| Teste de contrato “off → 0 chamadas embed” | Evitar regressão para embedding-first |
| Provider de embeddings injectável | Desacoplar de OpenAI sem mudar arquitectura |

Estas melhorias **não** alteram a direcção: núcleo analítico primeiro, Memory Augmentation congelada.

---

## Resumo em uma frase

**Implementar** = aprofundar o runtime cognitivo analítico (planner, SQL semântico, evidence, proveniência, orquestração) e tratar embeddings como **opcional, simples e congelado** — nunca como núcleo do sistema.
