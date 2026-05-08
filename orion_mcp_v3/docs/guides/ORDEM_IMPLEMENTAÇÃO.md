Perfeito.
Agora estamos entrando na parte MAIS importante:

# 👉 dependência arquitetural real

Porque o risco agora NÃO é código ruim.

O risco é:

```text id="2v8q8q"
implementar módulos fora de ordem
```

e depois descobrir que:

* allocator precisava do ContextBlock evoluído
* orchestrator precisava do CognitivePlan
* broker precisava do planner novo
* fusion precisava de provenance
* memory precisava de semantic roles

---

# 🧠 PRINCÍPIO QUE VAMOS USAR

A ordem correta NÃO é:

```text id="1xdybl"
infra → features
```

A ordem correta é:

# 👉 contratos → cognição → evidência → fusão → execução

---

# 🚨 REGRA FUNDAMENTAL

NÃO implemente:

❌ orchestrator final
❌ scheduler avançado
❌ fusion complexa
❌ map-reduce sofisticado
❌ DSL completa

ANTES de:

✅ ContextBlock
✅ CognitivePlan
✅ provenance
✅ intent resolution

---

# 🎯 ORDEM CORRETA (REAL)

Vou te dar agora:

# 👉 sequência operacional ideal

misturando:

* roadmap executável
* roadmap mysql
* plano cognitivo

na ordem CERTA de dependência.

---

# 🚀 ETAPA 0 — NÃO IMPLEMENTAR MAIS FEATURES

Antes:

# 👉 consolidar os contratos

---

# 1️⃣ PRIMEIRO - OK

# ROADMAP_EXECUTAVEL

## FASE 0 — contratos fundamentais

---

# IMPLEMENTAR

## ContextBlock evolução

Arquivo:

```text id="x7wshf"
contracts/context_block.py
```

Adicionar:

* semantic_role
* confidence
* cognitive_weight
* information_density
* freshness_score
* provenance
* token_cost

---

# IMPLEMENTAR

## Provenance types

Arquivo:

```text id="30c18t"
runtime/provenance.py
```

---

# IMPLEMENTAR

## AttentionProfile

Arquivo:

```text id="96z37r"
runtime/attention_policy.py
```

---

# ❗ NÃO CONTINUE antes disso

Porque TODO o resto depende disso.

---

# 2️⃣ SEGUNDO - OK

# NOVA FASE COGNITIVA

## Cognitive foundation

---

# IMPLEMENTAR

## CognitivePlan

Arquivo:

```text id="hmbqq8"
contracts/cognitive_plan.py
```

---

# IMPLEMENTAR

## Intent patterns

Arquivo:

```text id="mj8o7u"
runtime/intent_patterns.py
```

---

# IMPLEMENTAR

## IntentResolver

Arquivo:

```text id="9v4oaq"
runtime/intent_resolver.py
```

---

# 🚨 IMPORTANTE

NÃO use LLM.

Heurística primeiro.

---

# DEPENDÊNCIA

Isso precisa do:

✅ ContextBlock
✅ AttentionPolicy

---

# 3️⃣ TERCEIRO - OK

# ROADMAP_EXECUTAVEL

## runtime mínimo

---

# IMPLEMENTAR

## ContextState

Arquivo:

```text id="7zj2c2"
runtime/context_state.py
```

---

# IMPLEMENTAR

## ConflictResolution

Arquivo:

```text id="lfmq4w"
runtime/conflict_resolution.py
```

---

# IMPLEMENTAR

## Decay

Arquivo:

```text id="o6jfgc"
runtime/decay.py
```

---

# OBJETIVO

Criar governança mínima.

---

# 🚀 SÓ AGORA ENTRE NO MYSQL

---

# 4️⃣ QUARTO - OK

# ROADMAP_COM_MYSQL_INTEGRADO

## planner e query plan

---

# IMPLEMENTAR

## Evoluir planner.py

Arquivo:

```text id="ux16p0"
broker/planner.py
```

---

# IMPLEMENTAR

SemanticQueryPlan.

---

# IMPLEMENTAR

Estratégias:

* trend
* ranking
* temporal
* comparison
* anomaly

---

# DEPENDÊNCIA

Agora planner recebe:

```text id="g6ub97"
CognitivePlan
```

e não mais texto cru.

---

# 🚨 ISSO É MUITO IMPORTANTE

Esse é o momento que separa:

```text id="z5n5u8"
query engine
```

de

```text id="1l3e2l"
cognitive analytics runtime
```

---

# 5️⃣ QUINTO - OK

# ROADMAP_COM_MYSQL_INTEGRADO

## aggregators/samplers/reducers

---

# IMPLEMENTAR

## aggregators.py

---

# IMPLEMENTAR

## samplers.py

---

# IMPLEMENTAR

## reducers.py

---

# MAS:

todos devem retornar:

```text id="r3vfif"
estruturas cognitivas
```

e NÃO rows crus.

---

# 🚨 IMPORTANTE

Já implementar:

* confidence
* coverage
* provenance

---

# 6️⃣ SEXTO - OK

# NOVA CAMADA

## EvidenceBuilder

---

# IMPLEMENTAR

Arquivo:

```text id="l66yr8"
broker/evidence_builder.py
```

---

# OBJETIVO

Transformar:

```text id="n55zqv"
resultado SQL
```

em:

```text id="x87x1v"
EvidenceBlock
```

---

# IMPLEMENTAR

* trends
* baseline
* variation
* anomalies

---

# 🚨 IMPORTANTE

Aqui nasce:

# 👉 analytical reasoning

---

# 7️⃣ SÉTIMO - OK

# ROADMAP_EXECUTAVEL

## map-reduce

---

# IMPLEMENTAR

Chunk summarization.

---

# IMPLEMENTAR

Merge semântico.

---

# IMPLEMENTAR

coverage aggregation.

---

# IMPLEMENTAR

provenance merge.

---

# 🚨 SÓ AGORA

implementar:

## DriftGuard

Arquivo:

```text id="lsqic0"
runtime/drift_guard.py
```

---

# DEPENDÊNCIA

Porque agora já existem:

* reducers
* summaries
* provenance

---

# 8️⃣ OITAVO - OK

# ROADMAP_EXECUTAVEL

## Memory pipeline

---

# IMPLEMENTAR

## EpisodicRetriever

Arquivo:

```text id="9dzvgs"
memory/episodic_retriever.py
```

---

# IMPLEMENTAR

## SemanticRetriever

Arquivo:

```text id="a8txul"
memory/semantic_retriever.py
```

---

# IMPLEMENTAR

## Evoluir memory composer

Arquivo:

```text id="x9plp0"
memory/composer.py
```

---

# 🚨 IMPORTANTE

Agora memória retorna:

```text id="7ozrq0"
ContextBlocks
```

e não prompt texto.

---

# 9️⃣ NONO

# NOVA CAMADA

## ContextFusion

---

# IMPLEMENTAR

Arquivo:

```text id="l5w9pd"
runtime/context_fusion.py
```

---

# DEPENDÊNCIA

Precisa existir:

✅ analytics
✅ memory
✅ evidence
✅ provenance

---

# IMPLEMENTAR

* deduplicação
* merge cognitivo
* ordenação
* conflito

---

# 1️⃣0️⃣ DÉCIMO

# ROADMAP_EXECUTAVEL

## BudgetAllocator evolution

---

# ALTERAR

Arquivo:

```text id="2agq2w"
runtime/budget_allocator.py
```

---

# IMPLEMENTAR

Attention-aware allocation.

---

# IMPLEMENTAR

elastic zones.

---

# IMPLEMENTAR

soft competition:

```text id="w7u43d"
DATA vs MEMORY
```

---

# 🚨 SÓ AGORA

Porque agora já existem:

* blocos cognitivos
* fusion
* evidência
* semantic roles

---

# 1️⃣1️⃣ DÉCIMO PRIMEIRO

# ROADMAP_EXECUTAVEL

## scheduler

---

# IMPLEMENTAR

Scoring composto.

---

# IMPLEMENTAR

Profiles:

* analytical
* conversational
* hybrid

---

# DEPENDÊNCIA

Allocator precisa existir primeiro.

---

# 1️⃣2️⃣ DÉCIMO SEGUNDO

# FASE MAIS IMPORTANTE

## CognitiveOrchestrator

---

# IMPLEMENTAR

Arquivo:

```text id="5h0lb9"
runtime/cognitive_orchestrator.py
```

---

# IMPLEMENTAR

Fluxo completo:

```text id="i2qxd8"
IntentResolver
    ↓
CognitivePlan
    ↓
parallel retrieval
    ├── analytics
    ├── memory
    └── essence
    ↓
EvidenceBuilder
    ↓
Fusion
    ↓
Scheduler
    ↓
Allocator
    ↓
PromptRender
```

---

# 🚨 SOMENTE AGORA

Porque agora TODO ecossistema existe.

---

# 1️⃣3️⃣ DÉCIMO TERCEIRO

# ROADMAP_EXECUTAVEL

## DSL / compiler

---

# IMPLEMENTAR

SemanticQueryPlan compiler.

---

# IMPLEMENTAR

validation layer.

---

# IMPLEMENTAR

allowlist.

---

# 🚨 POR ÚLTIMO

Porque agora:

planner já está estável.

---

# 1️⃣4️⃣ DÉCIMO QUARTO

# DOCUMENTAÇÃO E TESTES

---

# IMPLEMENTAR

## drift tests

## provenance tests

## attention allocation tests

## orchestration tests

## fusion tests

---

# 🚀 RESUMO FINAL (ORDEM REAL)

# ETAPA 1 — FUNDAÇÃO

1. contracts/context_block.py
2. runtime/provenance.py
3. runtime/attention_policy.py

---

# ETAPA 2 — COGNIÇÃO

4. contracts/cognitive_plan.py
5. runtime/intent_patterns.py
6. runtime/intent_resolver.py

---

# ETAPA 3 — GOVERNANÇA

7. runtime/context_state.py
8. runtime/conflict_resolution.py
9. runtime/decay.py

---

# ETAPA 4 — ANALYTICS

10. broker/planner.py
11. aggregators.py
12. samplers.py
13. reducers.py
14. evidence_builder.py

---

# ETAPA 5 — DESTILAÇÃO

15. map-reduce
16. drift_guard.py

---

# ETAPA 6 — MEMÓRIA

17. episodic_retriever.py
18. semantic_retriever.py
19. memory/composer.py

---

# ETAPA 7 — FUSÃO

20. context_fusion.py

---

# ETAPA 8 — ALOCAÇÃO

21. budget_allocator.py
22. scheduler.py

---

# ETAPA 9 — ORQUESTRAÇÃO

23. cognitive_orchestrator.py

---

# ETAPA 10 — DSL

24. semantic compiler

---

# ETAPA 11 — TESTES

25. testes integrados

---

# 🎯 ESSA ORDEM EVITA

✅ retrabalho
✅ contratos quebrando
✅ allocator incompatível
✅ orchestrator prematuro
✅ fusion antes dos blocos cognitivos
✅ drift sem provenance
✅ analytics sem intenção

---

# 🚨 PRINCIPAL RECOMENDAÇÃO

Agora você NÃO deve implementar “features”.

Você deve implementar:

# 👉 dependências cognitivas na ordem correta
