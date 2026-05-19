# Orion MCP v3 — Arquitetura documental (índice mestre)

Este ficheiro **não duplica** o conteúdo dos outros roadmaps. Serve para:

- fixar **três níveis** de documentação;
- indicar **o que cada documento responde**;
- evitar trocar **roadmap operacional** por **roadmap só conceitual** (perde-se incrementalismo, entregas e testes).

---

## Os três níveis

| Nível | Documento | Pergunta que responde | Analogia |
|-------|-----------|------------------------|----------|
| **1 — Infraestrutura de dados & analytics** | [`ROADMAP_COM_MYSQL_INTEGRADO.md`](../roadmaps/ROADMAP_COM_MYSQL_INTEGRADO.md) | *Como os dados reais entram no runtime?* (SQL seguro, broker, pipelines, integração MySQL) | Sistema nervoso periférico |
| **2 — Execução incremental** | [`PLANO_EXECUCAO.md`](../execution/PLANO_EXECUCAO.md) | *O que implementar primeiro?* (ordem, milestones, contratos, testes cognitivos, checkpoints) | Plano cirúrgico / entregas |
| **3 — Cognição & arquitetura superior** | [`ARQUITETURA_COGNITIVA_CENTRAL.md`](./ARQUITETURA_COGNITIVA_CENTRAL.md) | *Como o sistema pensa?* (intenção, evidência, fusão de contexto, atenção, orquestração) | Cérebro / política cognitiva |

---

## Visão de evolução do produto

O caminho de maturidade **não** é só “memória + SQL”. O alvo é um **sistema cognitivo orientado por evidência**:

```text
Core:     dados → evidência → cognição → contexto LLM
Optional: Memory Augmentation (pgvector, chat_turn_embeddings) — ver MEMORY_AUGMENTATION_LAYER.md
```

- **ROADMAP MySQL** cobre sobretudo **dados → digest estruturado** e runtime seguro.
- **PLANO** garante **entregas incrementais** até lá e para as camadas seguintes.
- **Arquitetura cognitiva** define **evidência explícita**, **IntentResolver**, **ContextFusion**, **CognitiveOrchestrator** — sem substituir SQL nem milestones.

---

## O que cada camada absorve / não substitui

| Absorvido na visão cognitiva (conceitos) | Continua responsabilidade operacional |
|------------------------------------------|--------------------------------------|
| Broker, aggregators, reducers, digest, map-reduce, allocator, provenance, chunking | Detalhes em **ROADMAP MySQL** + código |
| Ordem de trabalho, testes de fluxo, contratos primeiro | **PLANO_EXECUCAO** |
| Intent, EvidenceBuilder, fusão de contexto | **ARQUITETURA_COGNITIVA_CENTRAL** (especificação); implementação segue **PLANO** |

**O plano cognitivo não substitui:** sequência de implementação, setup técnico, pipelines reais, camada SQL, integração MySQL, nem checklists de milestone — apenas **orienta** a próxima geração de módulos.

---

## Fases de ponte (referência cruzada)

| Fase | Onde está detalhada | Função |
|------|---------------------|--------|
| **Fase 2.5 — Cognitive Foundation** | [`PLANO_EXECUCAO.md`](../execution/PLANO_EXECUCAO.md) + [`ARQUITETURA_COGNITIVA_CENTRAL.md`](./ARQUITETURA_COGNITIVA_CENTRAL.md) | Separar *entendimento* (`CognitivePlan`, intent) de *execução* (SQL/planos semânticos). |
| **Fase 5.5 — Cognitive Orchestrator** | Idem | Fundir evidência analítica + memória conversacional + políticas de atenção num turno coerente. |

---

## Camada opcional — Memory Augmentation

Subsistema **experimental** e **congelado** para expansão: embeddings só para recuperação de turnos de chat, desacoplado do broker analítico.

- [`MEMORY_AUGMENTATION_LAYER.md`](./MEMORY_AUGMENTATION_LAYER.md) — regras MAY/MUST NOT, modos `off` / `index_only` / `retrieve`, lista de não-fazer.

---

## Outros documentos úteis

- [`ROADMAP_EXECUTÁVEL.md`](../roadmaps/ROADMAP_EXECUTÁVEL.md) — roadmap genérico por fases 0–6 (destilação, scheduler, governança).
- [`COMO_GEMINI_FUNCIONA.md`](../guides/COMO_GEMINI_FUNCIONA.md) — notas de modelo/memória.
- [`MEMORY_KEYSPACE.md`](../../src/orion_mcp_v3/infra/redis/MEMORY_KEYSPACE.md) — keyspace Redis.

---

## Mapa da pasta `docs/`

Ver **[`README.md`](../README.md)** na raiz de `docs/` — estrutura por diretórios (`execution/`, `roadmaps/`, `architecture/`, etc.).

---

## Resumo em uma frase

**Três documentos complementares:** infraestrutura de analytics (MySQL), plano incremental de execução (PLANO), arquitetura cognitiva central (ARQUITETURA) — coordenados por este índice.
