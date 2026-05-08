# Estratégia implementação

> **Índice entre documentos:** [`ORION_V3_MASTER_ARCHITECTURE.md`](../architecture/ORION_V3_MASTER_ARCHITECTURE.md) — liga este roadmap genérico (fases 0–6) ao plano incremental e ao pipeline MySQL/cognitivo.

# ✅ Vertical slices evolutivos

Cada etapa deve:

* funcionar isoladamente
* ser testável
* deixar o sistema melhor
* preparar a próxima camada

---

# 🧠 Estratégia correta para o Orion v3

Vamos dividir em:

| Fase | Objetivo               |
| ---- | ---------------------- |
| 0    | contratos fundamentais |
| 1    | runtime mínimo         |
| 2    | memória conversacional |
| 3    | broker analítico       |
| 4    | destilação             |
| 5    | scheduler              |
| 6    | governança avançada    |

---

# 🚀 ROADMAP EXECUTÁVEL (PASSO A PASSO)

---

# ✅ FASE 0 — FUNDAÇÃO SEMÂNTICA - OK

# Objetivo

Criar os tipos centrais do sistema.

SEM lógica complexa.

---

# 📦 Tarefa 0.1 — Criar estrutura base

## Criar diretórios

```plaintext
orion_mcp_v3/
├── runtime/
├── broker/
├── contracts/
├── memory/
└── protocols/
```

---

# 📦 Tarefa 0.2 — ContextBlock

## Arquivo

```plaintext
contracts/context_block.py
```

---

## Implementar

Primeiro só:

```python
ContextSource
ContextRole
ContextBlock
```

---

## NÃO implementar ainda

❌ scheduler
❌ allocator
❌ scoring
❌ truncagem

---

## Objetivo

Ter uma unidade formal de contexto.

---

# 📦 Tarefa 0.3 — Provenance types

## Arquivo

```plaintext
runtime/provenance.py
```

---

## Implementar

```python
ProvenanceAnchor
CoverageInfo
```

Apenas dataclasses/pydantic.

SEM lógica.

---

# 📦 Tarefa 0.4 — RuntimeEvent

## Arquivo

```plaintext
runtime/events.py
```

---

## Criar

```python
RuntimeEventType
RuntimeEvent
```

Eventos básicos:

```python
DIGEST_CREATED
MEMORY_PROMOTED
BUDGET_EXCEEDED
CONFLICT_DETECTED
```

---

# 📦 Tarefa 0.5 — SemanticQueryPlan

## Arquivo

```plaintext
contracts/query_plan.py
```

---

## Implementar

Somente:

```python
SemanticQueryPlan
RetrievalStrategy
```

SEM compilador SQL ainda.

---

# ✅ RESULTADO DA FASE 0

Você terá:

```text
contratos cognitivos estáveis
```

Isso é MUITO importante.

---

# 🚀 FASE 1 — RUNTIME MÍNIMO - OK

Agora começamos a dar comportamento ao sistema.

---

# 📦 Tarefa 1.1 — ContextState

## Arquivo

```plaintext
runtime/context_state.py
```

---

## Implementar

Estado mínimo:

```python
current_phase
active_policy
token_budget
active_blocks
```

---

## NÃO implementar

❌ persistência
❌ multiturn complexo

---

# 📦 Tarefa 1.2 — AttentionPolicy

## Arquivo

```plaintext
runtime/attention_policy.py
```

---

## Criar

Policies fixas:

```python
CONVERSATIONAL
ANALYTICAL
PLANNING
```

Cada uma retorna pesos simples.

---

# 📦 Tarefa 1.3 — BudgetAllocator MVP

## Arquivo

```plaintext
runtime/budget_allocator.py
```

---

## Implementar primeiro

Somente:

```python
allocate(blocks, max_tokens)
```

---

## Regras simples

1. reserve SYSTEM
2. reserve ESSENCE
3. ordenar por relevance_score
4. cortar excesso

---

## NÃO implementar

❌ cognitive weighting complexo
❌ elasticity
❌ score dinâmico

---

# 📦 Tarefa 1.4 — Teste do allocator

## Objetivo

Criar blocos fake e validar:

* reserve essencial
* corta excesso
* respeita prioridade

---

# ✅ RESULTADO FASE 1

Você terá:

```text
runtime cognitivo mínimo funcional
```

---

# 🚀 FASE 2 — MEMÓRIA CONVERSACIONAL - OK

Agora conectar com dados reais.

---

# 📦 Tarefa 2.1 — Repository literal

## Arquivo

```plaintext
memory/repositories/conversation_state.py
```

---

## Implementar

CRUD simples:

```python
append_message()
get_recent()
```

---

# 📦 Tarefa 2.2 — Converter memória → ContextBlock

Muito importante.

Toda memória vira bloco formal.

---

# 📦 Tarefa 2.3 — MemoryComposer MVP

## Arquivo

```plaintext
memory/composer.py
```

---

## Fluxo inicial

```text
recent messages
→ context blocks
→ allocator
→ prompt final
```

---

# 📦 Tarefa 2.4 — Redis cache

Somente cache de summaries.

Sem invalidação complexa ainda.

---

# 🚀 FASE 3 — BROKER ANALÍTICO - OK

Agora começa Big Data.

---

# 📦 Tarefa 3.1 — Planner MVP

## Arquivo

```plaintext
broker/planner.py
```

---

## Implementar

heurísticas simples:

```text
"últimos meses"
→ temporal aggregation

"top clientes"
→ ranking aggregation
```

Sem LLM ainda.

---

# 📦 Tarefa 3.2 — SemanticQueryPlan → SQL compiler

Primeira versão:

* SELECT only
* LIMIT obrigatório
* allowlist

---

# 📦 Tarefa 3.3 — Aggregators

## Arquivo

```plaintext
broker/aggregators.py
```

---

## Implementar

```python
group_by()
time_series()
top_n()
```

---

# 📦 Tarefa 3.4 — Samplers

## Arquivo

```plaintext
broker/samplers.py
```

---

## Primeiro sampler

```python
recent_sampler()
```

Depois:

```python
outlier_sampler()
```

---

# 📦 Tarefa 3.5 — AnalyticalDigest

## Arquivo

```plaintext
contracts/digest.py
```

---

## Implementar

Primeira versão simples:

```python
summary
volume
sample
coverage
```

---

# 🚀 FASE 4 — DESTILAÇÃO - OK

Agora entra map-reduce.

---

# 📦 Tarefa 4.1 — Chunking

## Arquivo

```plaintext
broker/chunking.py
```

---

## Implementar

Chunk por:

```python
max_rows
max_tokens
```

---

# 📦 Tarefa 4.2 — Summarizer Protocol

## Arquivo

```plaintext
protocols/summarizer.py
```

---

## Apenas interface primeiro

---

# 📦 Tarefa 4.3 — ChunkReducer

## Arquivo

```plaintext
broker/reducers.py
```

---

## Fluxo

```text
chunks
→ mini summaries
→ merged digest
```

---

# 📦 Tarefa 4.4 — Provenance integration

Cada digest carrega:

```python
source_refs
coverage
aggregation_logic
```

---

# 🚀 FASE 5 — COMPOSITOR REAL

Agora o sistema começa a ficar inteligente.

---

# 📦 Tarefa 5.1 — Scheduler score-based

## Arquivo

```plaintext
runtime/scheduler.py
```

---

## Score inicial

```python
relevance *
recency *
confidence
```

---

# 📦 Tarefa 5.2 — Redundancy filter

Evitar:

* embeddings repetidos
* digests duplicados

---

# 📦 Tarefa 5.3 — Conflict resolution

## Arquivo

```plaintext
runtime/conflict_resolution.py
```

---

## Primeiro conflito

```text
digest vs literal
```

---

# 🚀 FASE 6 — GOVERNANÇA AVANÇADA

Agora vira runtime cognitivo real.

---

# 📦 Tarefa 6.1 — Dynamic attention profiles

Policies dinâmicas.

---

# 📦 Tarefa 6.2 — Runtime transitions

Estados:

```text
ANALYZING
RETRIEVING
COMPRESSING
RESPONDING
```

---

# 📦 Tarefa 6.3 — Context decay

Blocos perdem prioridade com tempo.

---

# 📦 Tarefa 6.4 — Insight promotion pipeline

Mover digest → essence.

---

# 🚨 MUITO IMPORTANTE

# NÃO pule estas etapas:

## 1️⃣ Contratos primeiro

## 2️⃣ Testes do allocator

## 3️⃣ ContextBlock em TODO lugar

## 4️⃣ Provenance cedo

## 5️⃣ Scheduler só depois do MVP

---

# 🧠 O segredo para isso funcionar

Você NÃO está construindo:

```text
features
```

Você está construindo:

# 👉 um sistema de alocação de atenção

Isso muda completamente como evoluir o projeto.

---

# ⭐ Minha recomendação REAL

Comece AGORA somente com:

# FASE 0

e

# FASE 1

E valide:

```text
ContextBlocks → BudgetAllocator → Prompt final
```

ANTES de tocar em:

* broker
* embeddings
* map-reduce
* Redis
* summarization

---

# 🎯 Milestone correta

Seu primeiro objetivo real não é Big Data.

É:

# 👉 provar que o runtime consegue escolher contexto corretamente

Se isso funcionar, o resto escala naturalmente.
