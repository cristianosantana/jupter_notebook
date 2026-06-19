# Chat Público — Fase 5 Workspace Analítico

Índice da implementação do **Fact Engine remissivo**.

## Documentação canónica

- [FACT_ENGINE_SPEC.md](../FACT_ENGINE_SPEC.md) — contratos transversais Spec v1
- Plano detalhado: `.cursor/plans/fase_5_workspace_analítico_c979a6f4.plan.md` (não editar via implementação)

## Sub-fases

| ID | Conteúdo | Estado |
|---|---|---|
| 5.0 | Fact Engine Spec v1 — `domain/fact_engine/` | ✅ |
| 5A | FactPlanner híbrido + `fact_semantics.yaml` | ✅ |
| 5B | `memory_catalog.yaml`, MemoryResolver, SQL por theme | ✅ |
| 5C | FactExtractor + direct_answer_parser | ✅ |
| 5D | workspace_pipeline, AnalyticalNarrator, feature flag | ✅ |
| 5E | Observabilidade JSONL (`fact.*`, `workspace.build`) | ✅ |

## Pipeline

```text
Intent → FactPlanner → MemoryJoinPlan → MemoryResolver
       → FactExtractor → RemissiveWorkspace → AnalyticalNarrator
```

## Feature flag

```bash
PUBLIC_CHAT_USE_WORKSPACE=true   # Fact Engine (Fase 5)
PUBLIC_CHAT_USE_WORKSPACE=false  # Fase 4 legacy (default)
```

## Testes

- `tests/phase5a/` — Fact Planner
- `tests/phase5b/` — Memory Resolver + join
- `tests/phase5c/` — Fact Extractor + parser
- `tests/phase5d/` — Workspace E2E + Analytical Narrator

## Isolamento

100% em `public_chat/` — sem imports de `broker/`, `runtime/`, `EvidenceBlock`.

Ver [ISOLATION.md](../ISOLATION.md).
