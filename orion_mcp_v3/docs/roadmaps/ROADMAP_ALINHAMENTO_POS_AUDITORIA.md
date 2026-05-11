# ROADMAP — Alinhamento Pós Auditoria (2026-05-11)

Baseado na análise conjunta de:

* `docs/audit/AUDITORIA_ALINHAMENTO_ARQUITETURA_20260505.md`
* `docs/architecture/ORION_V3_MASTER_ARCHITECTURE.md`
* `docs/architecture/ARQUITETURA_COGNITIVA_CENTRAL.md`
* `docs/execution/PLANO_EXECUCAO.md`
* `docs/roadmaps/ROADMAP_COM_MYSQL_INTEGRADO.md`
* `docs/roadmaps/ROADMAP_EXECUTÁVEL.md`
* logs de integração em `logs/*.jsonl`
* testes existentes em `tests/`

---

# 1. Conclusão da auditoria (importante antes do roadmap)

O arquivo `AUDITORIA_ALINHAMENTO_ARQUITETURA_20260505.md` está COERENTE com o estado real do projeto.

A auditoria acertou principalmente:

* o pipeline cognitivo realmente existe;
* o planner cognitivo já está funcional;
* o compilador SQL já está seguro via allowlist;
* o fluxo MySQL → Evidence → Digest → Fusion → Allocator → Prompt já está operacional;
* o runtime cognitivo já existe parcialmente;
* o grande GAP atual é:

  * produto HTTP;
  * narrador LLM;
  * governança centralizada;
  * políticas reais de attention;
  * unificação formal entre memória e analytics;
  * dedupe inteligente;
  * configuração central;
  * fechamento do “turno completo”.

A auditoria também identificou corretamente:

* o projeto NÃO é mais apenas “chat memory”;
* ele já virou um runtime cognitivo orientado a contexto;
* o coração do sistema já é:

```text
Pergunta
→ intenção cognitiva
→ plano semântico
→ recuperação analítica
→ destilação
→ fusão contextual
→ orçamento cognitivo
→ prompt final
```

Ou seja:

A base arquitetural principal JÁ EXISTE.

O roadmap abaixo serve para:

* fechar lacunas;
* estabilizar contratos;
* evitar dívida arquitetural;
* transformar o runtime cognitivo em produto utilizável.

---

# 2. O que JÁ ESTÁ IMPLEMENTADO (não refazer)

## Foundation Cognitiva

* OK ContextBlock
* OK CognitivePlan
* OK SemanticQueryPlan
* OK Digest contracts
* OK runtime base
* OK context_state
* OK attention_policy inicial
* OK budget_allocator
* OK scheduler inicial
* OK conflict_resolution inicial
* OK provenance parcial

---

## Broker Cognitivo

* OK planner heurístico
* OK semantic_query_compiler
* OK sql_compiler allowlist
* OK AnalyticsExecutor
* OK aggregation.group_by
* OK reducers.merge
* OK evidence_builder
* OK map_reduce_digest
* OK drift_guard

---

## MySQL Integration

* OK MySQL executor
* OK parameter binding
* OK allowlist SQL
* OK pipeline analítico real
* OK evidence pipeline
* OK integração MySQL real

---

## Memory

* OK memory_episodic_retrieve
* OK memory_semantic_retrieve
* OK memory composer inicial
* OK fusion parcial

---

## Runtime Cognitivo

* OK CognitiveOrchestrator
* OK prompt rendering
* OK token allocation básico
* OK fusion pipeline
* OK scheduler básico

---

## Observabilidade

* OK JSONL auditável
* OK integração ponta-a-ponta
* OK testes integrados
* OK provenance parcial

---

# 3. PRINCIPAL PROBLEMA ATUAL

O sistema possui:

* planner;
* broker;
* analytics;
* memory;
* fusion;
* allocator;
* prompt.

MAS:

Ainda falta uma GOVERNANÇA CENTRAL.

Hoje o sistema funciona.

Mas ainda não existe:

* política cognitiva madura;
* competição real entre DATA vs MEMORY;
* orchestrator de turno completo;
* unificação formal de pipelines;
* runtime state consistente;
* prioridade cognitiva robusta;
* narrator final.

Ou seja:

O projeto já pensa.
Agora precisa aprender a decidir o que merece atenção.

---

# 4. NOVA ORDEM DE IMPLEMENTAÇÃO (IMPORTANTE)

A ordem abaixo substitui a ordem implícita anterior.

Ela foi reorganizada para evitar:

* retrabalho;
* conflitos entre runtime e fusion;
* pipelines duplicados;
* regras contraditórias;
* acoplamento futuro.

---

# FASE 1 — GOVERNANÇA COGNITIVA CENTRAL - OK

STATUS:

PARCIALMENTE IMPLEMENTADA.

OBJETIVO:

Transformar componentes soltos em um runtime cognitivo coordenado.

---

## 1.1 — Formalizar ContextBlock

ARQUIVOS:

```text
contracts/context_block.py
runtime/token_estimator.py
```

IMPLEMENTAR:

### Campos novos

```python
confidence
source_priority
cognitive_weight
information_density
token_cost
compressibility
recency_score
```

---

### Métodos

```python
estimate_token_cost()
compute_attention_score()
```

---

OBJETIVO:

Permitir competição real entre:

* memória;
* dados;
* digest;
* system;
* embeddings.

---

## 1.2 — Reescrever BudgetAllocator

ARQUIVO:

```text
runtime/budget_allocator.py
```

IMPLEMENTAR:

### Entrada

```python
list[ContextBlock]
```

### Saída

```python
AllocationResult(
    fitted_blocks,
    dropped_blocks,
    token_usage,
    allocation_trace,
)
```

---

### Regras

Implementar score:

```text
attention_score =
relevance × recency × confidence × source_priority × information_density
```

---

### Policies

```python
analytical
memory_heavy
balanced
monitoring
```

---

OBJETIVO:

Hoje o allocator ainda é “packing”.

Precisa virar:

Attention Allocator.

---

## 1.3 — Consolidar AttentionPolicy

ARQUIVO:

```text
runtime/attention_policy.py
```

IMPLEMENTAR:

### Policies reais

```python
ANALYTICAL
BALANCED
MEMORY_FOCUSED
MONITORING
EXECUTION
```

---

### Cada policy define

```python
source_weights
max_blocks_per_source
token_ratio_per_source
mandatory_sources
```

---

OBJETIVO:

Hoje policy ainda é simbólica.

Precisa controlar o runtime.

---

## 1.4 — Runtime State Real

ARQUIVO:

```text
runtime/context_state.py
```

IMPLEMENTAR:

### Estado da sessão

```python
active_intent
active_entities
last_digest
last_query_plan
memory_pressure
analytics_pressure
```

---

### Ciclo cognitivo

```python
IDLE
RETRIEVING
DISTILLING
FUSING
ALLOCATING
NARRATING
```

---

OBJETIVO:

Evitar pipelines independentes sem coordenação.

---

## 1.5 — Conflict Resolution REAL

ARQUIVO:

```text
runtime/conflict_resolution.py
```

IMPLEMENTAR:

### Detecção

* duplicação semântica;
* user turn repetido;
* memory vs digest repetidos;
* analytics redundante.

---

### Estratégias

```python
KEEP_HIGHEST_RELEVANCE
KEEP_MOST_RECENT
MERGE_CONTEXT
DROP_DUPLICATE
```

---

OBJETIVO:

Resolver problema visível no log:

```text
pergunta do usuário aparecendo múltiplas vezes
```

---

# FASE 2 — BROKER COGNITIVO COMPLETO

STATUS:

PARCIALMENTE IMPLEMENTADO.

OBJETIVO:

Transformar executor SQL em Broker Semântico.

---

## 2.1 — Planner Cognitivo Real

ARQUIVO:

```text
broker/planner.py
```

IMPLEMENTAR:

### Novo output

```python
SemanticRetrievalPlan
```

---

### Capaz de inferir

```python
trend_analysis
ranking
comparison
baseline
monitoring
anomaly_scan
```

---

### Planejamento antes da query

Exemplo:

```text
“queda de vendas”
→ série temporal
→ comparação
→ baseline
→ outliers
```

---

OBJETIVO:

Hoje planner ainda é muito textual.

Precisa virar:

Intent → Retrieval Strategy.

---

## 2.2 — Samplers Reais

ARQUIVO:

```text
broker/samplers.py
```

IMPLEMENTAR:

### Samplers

```python
RecentSampler
OutlierSampler
StratifiedSampler
TopKSampler
```

---

### Metadata

```python
sample_strategy
coverage
omitted_rows
```

---

OBJETIVO:

Hoje o digest ainda é simples.

Precisa reduzir Big Data corretamente.

---

## 2.3 — Reducers Cognitivos

ARQUIVOS:

```text
broker/reducers.py
broker/map_reduce.py
```

IMPLEMENTAR:

### Reducers

```python
TrendReducer
AnomalyReducer
RankingReducer
ComparisonReducer
```

---

### Provenance obrigatória

```python
source_refs
aggregation_logic
coverage
confidence
```

---

OBJETIVO:

Redução precisa virar:

Destilação Cognitiva.

---

## 2.4 — Evidence Builder Evoluído

ARQUIVO:

```text
broker/evidence_builder.py
```

IMPLEMENTAR:

### Insights estruturados

```python
trends
baselines
variation
anomalies
comparisons
```

---

### Confidence scoring

---

### Coverage scoring

---

OBJETIVO:

Evidence precisa virar:

“narrative evidence package”.

---

# FASE 3 — MEMÓRIA COGNITIVA

STATUS:

PARCIALMENTE IMPLEMENTADA.

OBJETIVO:

Transformar retrieval em memória útil.

---

## 3.1 — Episodic Memory Scoring

ARQUIVO:

```text
memory/episodic_retriever.py
```

IMPLEMENTAR:

### Score composto

```python
semantic_similarity
recency
intent_match
entity_overlap
importance
```

---

OBJETIVO:

Hoje retrieval episódico ainda é simples.

---

## 3.2 — Semantic Retriever Melhorado

ARQUIVO:

```text
memory/semantic_retriever.py
```

IMPLEMENTAR:

### Hybrid retrieval

```python
embedding + metadata + intent
```

---

### Filtros

```python
entity
intent
time_window
```

---

## 3.3 — Memory Composer Inteligente

ARQUIVO:

```text
memory/composer.py
```

IMPLEMENTAR:

### Camadas formais

```python
WORKING_MEMORY
SEMANTIC_MEMORY
EPISODIC_MEMORY
ESSENCE_MEMORY
```

---

### Dedupe interno

---

### Compressão contextual

---

# FASE 4 — CONTEXT FUSION REAL

STATUS:

PARCIAL.

OBJETIVO:

Unificar analytics + memory + system + user.

---

## 4.1 — Reescrever Context Fusion

ARQUIVO:

```text
runtime/context_fusion.py
```

IMPLEMENTAR:

### Sources

```python
SYSTEM
DATA
DIGEST
MEMORY
USER
ASSISTANT
```

---

### Pipeline

```text
normalize
→ dedupe
→ rank
→ allocate
→ render
```

---

### Ordenação dinâmica

Baseada em:

```python
attention_policy
```

---

OBJETIVO:

Hoje fusion ainda é estática.

---

## 4.2 — Scheduler Cognitivo

ARQUIVO:

```text
runtime/scheduler.py
```

IMPLEMENTAR:

### Score real

```python
relevance
confidence
coverage
importance
information_density
```

---

### Slot competition

DATA vs MEMORY competem por budget.

---

# FASE 5 — NARRADOR LLM

STATUS:

AUSENTE.

OBJETIVO:

Fechar ciclo cognitivo.

---

## 5.1 — LLM Provider Contracts

ARQUIVOS:

```text
protocols/llm.py
providers/openai_provider.py
```

IMPLEMENTAR:

### Interface

```python
generate(prompt)
chat(messages)
stream(messages)
```

---

### Metadata

```python
usage
latency
finish_reason
```

---

## 5.2 — Narrator Runtime

ARQUIVO:

```text
runtime/narrator.py
```

IMPLEMENTAR:

### Entrada

```python
CognitiveOrchestrationResult
```

---

### Responsabilidades

* chamar LLM;
* aplicar salvaguardas;
* narrar usando evidências;
* explicar limitações;
* citar coverage.

---

### Regras anti-alucinação

```text
“com base no resumo estatístico...”
“dados amostrados...”
“sem acesso à totalidade...”
```

---

# FASE 6 — API DE PRODUTO

STATUS:

AUSENTE.

OBJETIVO:

Transformar runtime em copilot utilizável.

---

## 6.1 — FastAPI

ARQUIVOS:

```text
api/main.py
api/routes/chat.py
api/models.py
```

IMPLEMENTAR:

### Endpoint

```text
POST /api/v1/chat
```

---

### Fluxo

```text
request
→ orchestrator
→ narrator
→ response
```

---

### Streaming

SSE ou websocket.

---

## 6.2 — Session Management

ARQUIVO:

```text
runtime/session_manager.py
```

IMPLEMENTAR:

### Sessões

```python
conversation_id
memory_window
runtime_state
```

---

# FASE 7 — CONFIGURAÇÃO CENTRAL

STATUS:

NÃO IMPLEMENTADO.

OBJETIVO:

Evitar drift operacional.

---

## 7.1 — Centralizar Settings

ARQUIVO:

```text
config/settings.py
```

IMPLEMENTAR:

### Configs

```python
MYSQL_URL
POSTGRES_URL
REDIS_URL
MAX_TOKENS
DEFAULT_LIMIT
TIMEOUTS
LLM_MODEL
```

---

### pydantic-settings

---

# FASE 8 — OBSERVABILIDADE AVANÇADA

STATUS:

PARCIAL.

OBJETIVO:

Transformar logs em telemetria cognitiva.

---

## 8.1 — Structured Tracing

ARQUIVOS:

```text
runtime/tracing.py
runtime/metrics.py
```

IMPLEMENTAR:

### Métricas

```python
allocation_pressure
memory_pressure
drift_frequency
coverage_loss
hallucination_risk
```

---

## 8.2 — Prompt Trace

Salvar:

```python
prompt_before_allocate
prompt_after_allocate
blocks_dropped
allocation_trace
```

---

# FASE 9 — HARDENING

OBJETIVO:

Preparar produção.

---

## 9.1 — SQL Runtime Policies

ARQUIVO:

```text
broker/policies.py
```

IMPLEMENTAR:

### Limites

```python
max_rows
max_scan
query_timeout
safe_mode
```

---

## 9.2 — Cache Cognitivo

ARQUIVO:

```text
runtime/cache.py
```

IMPLEMENTAR:

### Cache

```python
query_plan
analytics_digest
prompt_fragments
```

---

# 5. NOVA ORDEM CORRETA DE EXECUÇÃO

IMPORTANTE:

Esta passa a ser a ordem RECOMENDADA.

---

## PASSO 1

FASE 1 — Governança Cognitiva

Porque:

Sem isso o resto cresce desorganizado.

---

## PASSO 2

FASE 4 — Context Fusion REAL

Porque:

Tudo depende da competição correta entre blocos.

---

## PASSO 3

FASE 2 — Broker Cognitivo Completo

Porque:

Planner/reducers precisam das novas políticas cognitivas.

---

## PASSO 4

FASE 3 — Memória Cognitiva

Porque:

Memory retrieval depende:

* scheduler;
* allocator;
* fusion.

---

## PASSO 5

FASE 5 — Narrador LLM

Porque:

Agora já existe contexto maduro.

---

## PASSO 6

FASE 6 — API HTTP

Porque:

Produto só faz sentido depois do runtime fechado.

---

## PASSO 7

FASE 7 → 9

Hardening + observabilidade.

---

# 6. O QUE NÃO DEVE SER REFEITO

NÃO reimplementar:

* sql_compiler;
* executor;
* evidence_builder base;
* planner heurístico atual;
* cognitive_orchestrator;
* tests foundation;
* integração MySQL.

Eles já são fundação válida.

O foco agora é:

* governança;
* atenção;
* fusão cognitiva;
* narrador;
* produto.

---

# 7. Conclusão

O projeto já ultrapassou a fase de “assistente com memória”.

Hoje ele já é:

```text
um runtime cognitivo orientado a analytics,
com atenção contextual,
destilação semântica,
e fusão entre memória e evidência.
```

O principal desafio agora NÃO é mais:

* SQL;
* embeddings;
* memória;
* planner.

O desafio agora é:

```text
governar atenção,
controlar competição cognitiva,
e fechar o ciclo narrativo.
```

Isso muda completamente a natureza do sistema.
