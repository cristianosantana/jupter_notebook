# Arquitetura cognitiva central — Orion MCP v3

**Papel deste documento:** camada **cognitiva superior** — responde *«como o sistema pensa?»* (resolução de intenção, evidência, fusão de contexto, alocação de atenção, orquestração de turno).

**Não substitui:**

| Documento | Responsabilidade |
|-----------|-------------------|
| [`PLANO_EXECUCAO.md`](../execution/PLANO_EXECUCAO.md) | Roadmap técnico incremental — *o que implementar primeiro?* |
| [`ROADMAP_COM_MYSQL_INTEGRADO.md`](../roadmaps/ROADMAP_COM_MYSQL_INTEGRADO.md) | Pipeline analytics + dados reais + SQL seguro |

**Índice mestre:** [`ORION_V3_MASTER_ARCHITECTURE.md`](./ORION_V3_MASTER_ARCHITECTURE.md).

**Pontes no plano incremental:** Fase **2.5 — Cognitive Foundation**, Fase **5.5 — Cognitive Orchestrator** (ver [`PLANO_EXECUCAO.md`](../execution/PLANO_EXECUCAO.md)).

---

Perfeito.
Agora ficou MUITO mais claro o estado real do projeto.

O roadmap executável já está excelente estruturalmente.
Mas analisando:

* o roadmap,
* os itens `- OK`,
* a arquitetura atual,
* e o objetivo real do Orion v3,

dá para ver exatamente:

# 👉 o que foi bem resolvido

# 👉 o que ainda está “mecânico”

# 👉 e o que precisa evoluir para virar um runtime cognitivo real

---

# 🧠 DIAGNÓSTICO DO ESTADO ATUAL

Você já implementou:

| Área              | Estado   |
| ----------------- | -------- |
| contratos         | bom      |
| runtime mínimo    | bom      |
| memory pipeline   | razoável |
| analytical broker | MVP      |
| digest            | MVP      |
| map-reduce        | inicial  |

Mas ainda falta:

# 👉 a camada que dá INTELIGÊNCIA DE ORQUESTRAÇÃO

Hoje o sistema ainda funciona como:

```text
pipeline engine
```

e não como:

```text
cognitive runtime
```

---

# 🚨 PRINCIPAL PROBLEMA ARQUITETURAL ATUAL

Hoje:

```text
memory
analytics
digest
allocator
```

existem…

MAS:

não existe um:

# 👉 “motor de decisão cognitiva”

---

# CONSEQUÊNCIA

Hoje o sistema:

* executa coisas
* compõe contexto
* reduz tokens

Mas ainda NÃO:

* entende intenção contextual
* decide profundidade analítica
* decide se memória importa
* decide se comparação temporal é necessária
* decide se precisa baseline histórico

---

# 🎯 O QUE PRECISA SER FEITO AGORA

Você NÃO deve reescrever o roadmap.

Você deve:

# 👉 EVOLUIR o roadmap atual

---

# O roadmap atual vira:

| Camada             | Estado   |
| ------------------ | -------- |
| infraestrutura     | pronta   |
| cognição           | faltando |
| orquestração       | faltando |
| fusão semântica    | faltando |
| evidence reasoning | faltando |

---

# 🚀 AJUSTE OFICIAL DO ROADMAP

Agora vou te mostrar:

# ✅ o que adicionar

# ✅ o que modificar

# ✅ o que manter

# ✅ e exatamente O QUE implementar em cada arquivo

---

# 🚀 NOVA FASE (ANTES DA FASE 3)

# ✅ FASE 2.5 — COGNITIVE ORCHESTRATION FOUNDATION

Essa fase NÃO existe no roadmap atual.

Mas ela é ESSENCIAL.

---

# OBJETIVO

Adicionar:

# 👉 entendimento cognitivo

ANTES da execução.

---

---

# 📦 TAREFA 2.5.1 — CognitivePlan

## NOVO ARQUIVO

```plaintext
contracts/cognitive_plan.py
```

---

# IMPLEMENTAR

## Enum

```python
IntentType
```

Valores:

```python
ANALYTICAL
CONVERSATIONAL
COMPARATIVE
TEMPORAL
RECALL
MONITORING
EXECUTION
HYBRID
```

---

## Dataclass

```python
CognitivePlan
```

Campos:

```python
intent_type
needs_memory
needs_analytics
needs_comparison
needs_temporal_context
needs_baseline
needs_trend_analysis
needs_entity_resolution
confidence
entities
metrics
time_scope
retrieval_strategy
attention_profile
```

---

# OBJETIVO

Separar:

```text
entendimento
```

de

```text
execução
```

---

# 📦 TAREFA 2.5.2 — IntentResolver

## NOVO ARQUIVO

```plaintext
runtime/intent_resolver.py
```

---

# IMPLEMENTAR

Classe:

```python
IntentResolver
```

Método:

```python
resolve(user_input, recent_context)
```

Retorna:

```python
CognitivePlan
```

---

# IMPLEMENTAR DETECÇÕES

## Comparação

```text
"de novo"
"continua"
"melhorou"
"piorou"
```

---

## Temporalidade

```text
"últimos meses"
"hoje"
"ontem"
"comparado"
```

---

## Analytics puro

```text
"ticket médio"
"faturamento"
"top clientes"
```

---

## Conversacional puro

```text
"o que falamos"
"me explique"
```

---

# IMPORTANTE

NÃO usar LLM ainda.

Somente heurística.

---

# 📦 TAREFA 2.5.3 — Intent Patterns

## NOVO ARQUIVO

```plaintext
runtime/intent_patterns.py
```

---

# IMPLEMENTAR

Regex/patterns organizados:

```python
COMPARATIVE_PATTERNS
TEMPORAL_PATTERNS
ANALYTICAL_PATTERNS
RECALL_PATTERNS
```

---

# OBJETIVO

Evitar lógica hardcoded dentro do resolver.

---

# 📦 TAREFA 2.5.4 — AttentionProfile evolution

## ALTERAR

```plaintext
runtime/attention_policy.py
```

---

# ADICIONAR

Profiles:

```python
ANALYTICAL
CONVERSATIONAL
HYBRID
MONITORING
EXECUTION
```

---

# IMPLEMENTAR

Método:

```python
get_weights()
```

Retorna pesos:

```python
memory_weight
analytics_weight
system_weight
user_weight
```

---

# OBJETIVO

Parar de usar:

```text
ordem fixa
```

e começar:

```text
alocação contextual
```

---

# 🚀 AJUSTE DA FASE 3 (BROKER)

A fase 3 está boa.

Mas ainda muito:

```text
query-centric
```

e pouco:

```text
evidence-centric
```

---

# 📦 TAREFA 3.1 — EVOLUIR planner.py

## ARQUIVO EXISTENTE

```plaintext
broker/planner.py
```

---

# IMPLEMENTAR NOVO CONCEITO

Hoje:

```text
texto → aggregation hint
```

---

# Evoluir para:

```text
CognitivePlan → SemanticQueryPlan
```

---

# IMPLEMENTAR

Método:

```python
build_query_plan(cognitive_plan)
```

---

# Planner agora deve decidir

## Tipo de análise

```python
TREND
RANKING
COMPARISON
TIMESERIES
ANOMALY
```

---

## Estratégia de recuperação

```python
TOP_N
TEMPORAL_WINDOW
DELTA_ANALYSIS
BASELINE_COMPARISON
```

---

# 📦 TAREFA 3.2 — EvidenceBuilder

## NOVO ARQUIVO

```plaintext
broker/evidence_builder.py
```

---

# IMPLEMENTAR

Transformar:

```python
SQL rows
```

em:

```python
EvidenceBlock
```

---

# IMPLEMENTAR EXTRAÇÕES

## trend

```python
upward
downward
stable
```

---

## variance

```python
variation_pct
```

---

## baseline

```python
previous_period
historical_avg
```

---

## anomaly

```python
spike
drop
outlier
```

---

# OBJETIVO

Parar de enviar:

```text
dados crus
```

e começar enviar:

```text
evidência cognitiva
```

---

# 📦 TAREFA 3.3 — Insight Extractors

## NOVO ARQUIVO

```plaintext
broker/insight_extractors.py
```

---

# IMPLEMENTAR

Funções:

```python
extract_trends()
extract_variation()
extract_outliers()
extract_rank_changes()
```

---

# 📦 TAREFA 3.4 — AnalyticalContextBuilder evolution

## ALTERAR

builder analítico atual.

---

# IMPLEMENTAR

Gerar:

```python
ContextBlock
```

com:

```python
semantic_role=EVIDENCE
```

---

# ADICIONAR

```python
confidence
information_density
provenance
```

---

# 🚀 AJUSTE DA FASE 4 (DESTILAÇÃO)

A estrutura está boa.

Mas ainda falta:

# 👉 proteção contra summary drift

---

# 📦 TAREFA 4.5 — Drift Guard

## NOVO ARQUIVO

```plaintext
runtime/drift_guard.py
```

---

# IMPLEMENTAR

Validações:

## coverage mínima

```python
coverage > 0.7
```

---

## confidence mínima

```python
confidence > threshold
```

---

## provenance obrigatória

---

# IMPLEMENTAR

Método:

```python
validate_digest()
```

---

# OBJETIVO

Evitar:

```text
alucinação por compressão
```

---

# 🚀 AJUSTE DA FASE 5 (COMPOSITOR)

A fase 5 precisa virar:

# 👉 Context Fusion Layer

---

# 📦 TAREFA 5.0 — ContextFusion

## NOVO ARQUIVO

```plaintext
runtime/context_fusion.py
```

---

# IMPLEMENTAR

Classe:

```python
ContextFusion
```

---

# RESPONSABILIDADE

Fundir:

| Tipo      | Origem   |
| --------- | -------- |
| SYSTEM    | system   |
| MEMORY    | memory   |
| ANALYTICS | broker   |
| DIGEST    | reducers |
| USER      | input    |

---

# IMPORTANTE

NÃO concatenar strings.

Fundir:

```python
ContextBlock[]
```

---

# IMPLEMENTAR

## Ordenação cognitiva

## Deduplicação

## Resolução de conflito

## Merge semântico

---

# 📦 TAREFA 5.1 — Deduplication Layer

## NOVO ARQUIVO

```plaintext
runtime/deduplication.py
```

---

# IMPLEMENTAR

Detectar:

* embeddings redundantes
* digests repetidos
* mesma informação em MEMORY + ANALYTICS

---

# 📦 TAREFA 5.2 — Evoluir scheduler.py

## ARQUIVO EXISTENTE

```plaintext
runtime/scheduler.py
```

---

# IMPLEMENTAR

Novo score:

```python
relevance *
confidence *
freshness *
information_density *
cognitive_weight
```

---

# IMPLEMENTAR

Attention-aware scheduling.

---

# 🚀 NOVA FASE 5.5 — COGNITIVE ORCHESTRATOR

Essa é a parte MAIS importante.

---

# 📦 TAREFA 5.5.1 — CognitiveOrchestrator

## NOVO ARQUIVO

```plaintext
runtime/cognitive_orchestrator.py
```

---

# IMPLEMENTAR

Fluxo completo:

```text
User input
    ↓
IntentResolver
    ↓
CognitivePlan
    ↓
parallel retrieval
    ├── memory
    ├── analytics
    └── essence
    ↓
EvidenceBuilder
    ↓
ContextFusion
    ↓
Scheduler
    ↓
BudgetAllocator
    ↓
PromptRenderer
```

---

# IMPLEMENTAR

## asyncio.gather()

para retrieval paralelo.

---

# IMPLEMENTAR

Fallbacks:

| Falha     | Ação               |
| --------- | ------------------ |
| analytics | continua memória   |
| memória   | continua analytics |
| ambos     | graceful error     |

---

# IMPLEMENTAR

Tracing básico.

---

# 🚀 AJUSTE DA FASE 6 (GOVERNANÇA)

A fase 6 está boa.

Mas falta:

# 👉 decaimento cognitivo

---

# 📦 TAREFA 6.5 — Cognitive Decay

## NOVO ARQUIVO

```plaintext
runtime/decay.py
```

---

# IMPLEMENTAR

Função:

```python
apply_decay(block)
```

---

# Reduzir score por:

* idade
* redundância
* baixa reutilização

---

# 📦 TAREFA 6.6 — Context Priority Evolution

## ALTERAR

```plaintext
contracts/context_block.py
```

---

# ADICIONAR

```python
cognitive_weight
information_density
usage_count
reuse_score
```

---

# 🚀 AJUSTE CRÍTICO NO MEMORY COMPOSER

Hoje:

```text
mensagens → prompt
```

---

# Deve virar

```text
mensagens → ContextBlocks cognitivos
```

---

# 📦 ALTERAR

```plaintext
memory/composer.py
```

---

# IMPLEMENTAR

Tipos:

| Tipo      | semantic_role |
| --------- | ------------- |
| user      | USER_INTENT   |
| assistant | RESPONSE      |
| insight   | INSIGHT       |
| summary   | SUMMARY       |

---

# 🚀 AJUSTE CRÍTICO NO BUDGET ALLOCATOR

Hoje:

```text
token allocator
```

---

# Deve virar:

# 👉 Attention Allocator

---

# 📦 ALTERAR

```plaintext
runtime/budget_allocator.py
```

---

# IMPLEMENTAR

## Reserved token zones

```python
system_reserved
user_reserved
analytics_reserved
memory_reserved
```

---

# IMPLEMENTAR

Elastic overflow.

---

# IMPLEMENTAR

Soft competition:

```python
DATA vs MEMORY
```

---

# 🚀 RESULTADO FINAL

Após esses ajustes o Orion deixa de ser:

```text
chat memory + analytics
```

e vira:

# 👉 um runtime cognitivo híbrido

capaz de:

* entender intenção
* decidir profundidade
* recuperar memória relevante
* buscar dados reais
* transformar dados em evidência
* fundir tudo cognitivamente
* alocar atenção
* responder com contexto consistente

---

# 🎯 ORDEM REAL DE IMPLEMENTAÇÃO AGORA

## PRIORIDADE MÁXIMA

### 1️⃣ CognitivePlan

### 2️⃣ IntentResolver

### 3️⃣ EvidenceBuilder

### 4️⃣ ContextFusion

### 5️⃣ CognitiveOrchestrator

---

# NÃO faça agora

❌ graph runtime
❌ LLM planner
❌ embeddings avançados
❌ reinforcement scoring
❌ self-reflection loops

---

# O verdadeiro milestone do Orion v3 agora é:

# 👉 provar que ele consegue pensar sobre contexto

e não apenas:

```text
montar prompts
```
