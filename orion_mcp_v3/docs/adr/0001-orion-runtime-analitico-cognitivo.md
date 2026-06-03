# ADR 0001: Orion Como Runtime Analitico Cognitivo

## Status

Aceita.

## Contexto

O Orion MCP v3 ainda carrega duas filosofias de produto:

- **Chat + memoria**: a conversa e a memoria aparecem como eixo principal, com analytics acoplado quando necessario.
- **Pipeline analitico cognitivo**: a pergunta vira intencao, plano, SQL controlado, evidencia, contexto e resposta narrada.

A primeira filosofia ajuda na interface e na continuidade, mas limita o produto quando vira arquitetura. Se o sistema se organizar como chatbot, ele tende a depender de memoria, prompts e perguntas conhecidas. O objetivo do Orion e responder naturalmente a partir dos dados disponiveis e ampliar sua capacidade por novas visoes analiticas.

## Decisao

O Orion MCP v3 adota definitivamente a filosofia de **runtime analitico cognitivo** como eixo principal.

Chat e memoria permanecem como camadas auxiliares:

- chat e interface de entrada e saida;
- memoria fornece contexto, continuidade, preferencias e follow-up;
- evidencia analitica decide respostas factuais sobre dados.

O fluxo canonico passa a ser:

```text
pergunta -> intencao -> contrato validado -> visao analitica
         -> SQL controlado -> evidencia -> contexto auxiliar -> LLM narrador
```

A LLM pode atuar em dois pontos distintos:

- **LLM interprete**: entende perguntas novas e produz contrato estruturado, sem gerar SQL.
- **LLM narrador**: recebe evidencia, pergunta e contexto, e redige a resposta final.

## Consequencias

- Novas capacidades devem nascer de metricas, dimensoes, operacoes e visoes, nao de perguntas cadastradas.
- Toda resposta analitica deve ter evidencia antes da narracao.
- SQL so pode nascer de templates, planos semanticos ou superficies allowlisted.
- Memoria nao substitui evidencia atual.
- Embeddings continuam opcionais e auxiliares.
- O roadmap prioriza planner, catalogo semantico, evidence, provenance, coverage e orchestration.

## Invariantes

1. O Orion conhece dados e visoes analiticas, nao uma lista fechada de perguntas.
2. Intencao gerada por LLM precisa virar contrato validado.
3. A LLM nao escolhe livremente colunas, metricas ou SQL.
4. `EvidenceBlock` e a fronteira entre dados executados e narracao.
5. Em conflito entre memoria e evidencia atual, a evidencia vence.
6. O narrador recebe contratos estruturados do pipeline, nao listas brutas concatenadas.
7. A LLM narradora apenas materializa decisoes analiticas ja tomadas pelo runtime.
8. Novas respostas analiticas devem aprofundar contratos existentes (`ProjectedAnswer`, `ProjectedAnswerSet`, `EvidenceBlock`, `AnalyticalReasoningResult`, `ContextBlock`) em vez de inventar estruturas paralelas.
