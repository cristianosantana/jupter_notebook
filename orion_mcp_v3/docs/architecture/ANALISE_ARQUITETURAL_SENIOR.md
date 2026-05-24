# Análise Arquitetural Sênior — Orion MCP v3

Este documento revisa o Orion MCP v3 como um **runtime cognitivo analítico**. A análise usa a linguagem das skills de engenharia carregadas: **Module**, **Interface**, **Implementation**, **Seam**, **Adapter**, **Depth**, **Leverage**, **Locality** e **Deletion test**.

O objetivo não é listar arquivos; é identificar onde o sistema ganha ou perde profundidade arquitetural, quais caminhos de execução existem, onde a complexidade está concentrada e quais mudanças aumentam resiliência, escalabilidade e manutenção.

## 1. Arquitetura e Estrutura do Projeto

### 1.1 Tese arquitetural

O Orion não deve ser interpretado como um sistema de memória vetorial. Ele está mais próximo de um **runtime cognitivo analítico orientado por evidência**, onde a pergunta humana é transformada em plano, dados, evidência, contexto e narração.

O eixo central é:

```text
pergunta humana
  -> intenção cognitiva
  -> interpretação semântica LLM opcional
  -> contrato de intenção validado
  -> estratégia analítica
  -> plano semântico
  -> SQL seguro / templates
  -> capacidade de resposta
  -> resposta direta projetada
  -> evidência estruturada
  -> isolamento de contexto analítico
  -> fusão contextual
  -> prompt governado por atenção
  -> narração LLM
```

Embeddings existem, mas pertencem à camada opcional de **Memory Augmentation**. Eles devem aumentar continuidade conversacional, não decidir analytics.

### 1.2 Mapa de módulos

#### `api` — Module de borda HTTP e composition root operacional

**Interface:** rotas FastAPI (`/api/v1/chat`, `/api/v1/sessions`, `/api/v1/chat/options`, `/health`) e modelos de request/response.

**Implementation:** inicializa dependências no lifespan, injeta providers, executa fluxo de chat, controla SSE, tracing e persistência de mensagens.

**Arquivos principais:**

- `src/orion_mcp_v3/api/main.py`
- `src/orion_mcp_v3/api/routes/chat.py`
- `src/orion_mcp_v3/api/models.py`

**Avaliação de profundidade:** hoje o `api` é um Module pouco profundo no `routes/chat.py`: a Interface HTTP é simples, mas a Implementation concentra quase todo o processo. Isso dá alto acoplamento operacional e baixa Locality para bugs do turno de chat.

**Deletion test:** se `routes/chat.py` fosse removido, a complexidade não desapareceria; ela reapareceria espalhada em runtime, memory e broker. Isso indica que existe um Module real ali, mas ele ainda está mal nomeado e pouco encapsulado.

#### `runtime` — Module cognitivo

**Interface:** `IntentResolver.resolve()`, `AnalyticalIntentInterpreter.interpret()`, `IntentContractValidator.validate()`, `CognitiveOrchestrator.finalize_prompt()`, `CognitiveNarrator.narrate()`, `AttentionPolicy`, scheduler, allocator e prompt renderer.

**Implementation:** interpreta intenção, monta camadas de contexto, aplica política de atenção, aloca orçamento de tokens, renderiza prompt e chama o provider LLM.

**Arquivos principais:**

- `src/orion_mcp_v3/runtime/intent_resolver.py`
- `src/orion_mcp_v3/runtime/analytical_intent_interpreter.py`
- `src/orion_mcp_v3/runtime/analytical_intent_validator.py`
- `src/orion_mcp_v3/runtime/heuristic_signal_catalog.py`
- `src/orion_mcp_v3/runtime/cognitive_orchestrator.py`
- `src/orion_mcp_v3/runtime/analytical_context_policy.py`
- `src/orion_mcp_v3/runtime/analytical_signature.py`
- `src/orion_mcp_v3/runtime/analytical_system_prompt.py`
- `src/orion_mcp_v3/runtime/narrator.py`
- `src/orion_mcp_v3/runtime/context_fusion.py`
- `src/orion_mcp_v3/runtime/budget_allocator.py`

**Avaliação de profundidade:** é o Module mais próximo do desenho desejado. `CognitiveOrchestrator.finalize_prompt()` oferece uma Interface pequena para muita Implementation: fusão, scheduler, allocator e render. O novo `analytical_system_prompt` aumenta Leverage porque injeta regras analíticas e anti-alucinação sem espalhar instruções pelo código.

O isolamento analítico aprofunda esse Module: `AnalyticalContextIsolationPolicy` decide quando memória analítica histórica pode competir por atenção, e `AnalyticalSignature` dá ao runtime uma forma explícita de comparar métrica, dimensão, operação, template e período antes de reutilizar histórico. Isso preserva a tese central do projeto: evidência atual vence memória antiga.

A nova camada de interpretação aprofunda outro seam: `IntentResolver` continua barato e heurístico, mas seus regex agora também viram `HeuristicSignalCatalog`. O LLM usa esses sinais, o histórico recente e o catálogo de capabilities para propor um `AnalyticalIntentContract`; o `IntentContractValidator` aceita somente contratos compatíveis com enum, datas e capacidades declaradas. Assim, o sistema ganha entendimento contextual sem entregar ao LLM o poder de inventar SQL ou capacidades.

**Risco:** o `runtime/__init__.py` é um barrel grande. Ele aumenta conveniência, mas também carrega muitos símbolos e pode mascarar dependências indiretas. O risco é import coupling, não comportamento imediato.

#### `broker` — Module analítico

**Interface:** `CognitivePlan -> SemanticQueryPlan -> AnalyticsResult -> ProjectedAnswer -> EvidenceBlock`.

**Implementation:** resolve plano analítico, expande templates, compila SQL seguro, executa MySQL, projeta respostas diretas por capacidade declarada, agrega evidência e calcula estatísticas complementares.

**Arquivos principais:**

- `src/orion_mcp_v3/broker/planner.py`
- `src/orion_mcp_v3/broker/query_expander.py`
- `src/orion_mcp_v3/broker/sql_compiler.py`
- `src/orion_mcp_v3/broker/executor.py`
- `src/orion_mcp_v3/broker/answer_capability.py`
- `src/orion_mcp_v3/broker/answer_projector.py`
- `src/orion_mcp_v3/broker/evidence_builder.py`
- `src/orion_mcp_v3/broker/evidence_aggregator.py`
- `src/orion_mcp_v3/broker/queries/*.py`

**Avaliação de profundidade:** o `broker` ficou mais profundo com a camada **Answer Capability**. Antes, uma query rica era reduzida a `VALUE_KEY`; agora cada template pode declarar `MEASURES`, `DIMENSIONS`, medida padrão, dimensão padrão e operações suportadas. Isso transforma “colunas disponíveis” em “respostas possíveis” antes do LLM.

**Seams importantes:**

- `CognitivePlan -> SemanticQueryPlan`: concentra intenção e estratégia executável.
- `QueryTemplate -> AnswerCapability`: declara o que uma query sabe responder.
- `AnalyticsResult -> ProjectedAnswer`: transforma rows SQL em resposta objetiva.
- `ProjectedAnswer -> EvidenceBlock`: preserva a resposta direta e rebaixa estatística genérica a complemento.

O `broker` deve continuar livre de embeddings e de lógica conversacional. A sua responsabilidade é produzir evidência e respostas diretas auditáveis.

#### `memory` — Module de memória conversacional

**Interface:** `ConversationStateRepository`, `MemoryRetrievalPipeline.collect_blocks()`, retrievers episódico, lexical e vetorial opcional.

**Implementation:** guarda mensagens, recupera histórico recente, faz matching lexical e opcionalmente pgvector.

**Arquivos principais:**

- `src/orion_mcp_v3/memory/retrieval_pipeline.py`
- `src/orion_mcp_v3/memory/composer.py`
- `src/orion_mcp_v3/memory/episodic_retriever.py`
- `src/orion_mcp_v3/memory/semantic_retriever.py`
- `src/orion_mcp_v3/memory/vector_retriever.py`
- `src/orion_mcp_v3/memory/chat_turn_embedding_store.py`
- `src/orion_mcp_v3/memory/repositories/*.py`

**Avaliação de profundidade:** a separação `retrieval_pipeline != composer` está correta. O composer deve continuar puro: blocos prontos entram, prompt/memória composta sai. O retrieval deve continuar fora dele.

**Risco:** o seam de embeddings ainda é raso. `ChatTurnEmbeddingStore` recebe `EmbeddingService`, mas ainda depende de `OpenAIEmbeddingService.to_pgvector`. Isso prende o Module de memória a um Adapter concreto.

#### `contracts` — Module de linguagem comum

**Interface:** dataclasses e enums de domínio técnico: `CognitivePlan`, `AnalyticalIntentContract`, `SemanticQueryPlan`, `ContextBlock`, `EvidenceBlock`, `AnalyticalDigest`, `CoverageInfo`, `ProvenanceAnchor`.

**Implementation:** quase inexistente; o valor é estabilidade sem dependências de runtime/broker/memory.

**Avaliação de profundidade:** é o melhor seam do projeto. Callers dependem de tipos estáveis, e decisões de runtime podem mudar sem quebrar o broker quando o contrato é preservado.

#### `providers` e `protocols` — Adapters de borda externa

**Interface:** `LLMProvider`, `EmbeddingService`.

**Implementation:** `OpenAIProvider`, `OpenAIEmbeddingService`, `NullLLMProvider`, `EchoLLMProvider`.

**Avaliação de profundidade:** o seam de LLM está bom. O seam de embeddings precisa ser mais neutro, porque a serialização pgvector não deveria depender do adapter OpenAI.

#### `connection_hub` e `infra` — Adapters de dados

**Interface:** pools e clientes para MySQL/Postgres/Redis; migrações.

**Implementation:** drivers concretos, scripts de migração, keyspaces.

**Avaliação de profundidade:** adequado como camada de infraestrutura. A atenção principal deve ir para o modelo de persistência de mensagens, que hoje usa JSONB crescente.

### 1.3 Acoplamento e dependências

Direção saudável atual:

```text
api -> runtime / broker / memory / providers / config
runtime -> contracts / protocols
broker -> contracts / connection_hub
memory -> contracts / repositories / providers opcionais
providers -> protocols
contracts -> sem dependência de runtime, broker ou memory
```

Pontos complexos:

1. `api/routes/chat.py` é o maior nó de coordenação. Ele faz request handling, persistência, retrieval, analytics, evidence merge, orchestration, narration, streaming e tracing.
2. `api/main.py` é composition root. Isso é aceitável, mas deve continuar restrito a bootstrapping.
3. `runtime/__init__.py` e `broker/__init__.py` reduzem a clareza de dependências reais.
4. `memory/retrieval_pipeline.py` não deve depender de helpers privados do composer. Se houver lógica compartilhada, ela deve virar utilitário público ou Module próprio.
5. `memory/chat_turn_embedding_store.py` ainda deixa o Adapter OpenAI atravessar o seam de memória.
6. `broker/query_expander.py` ainda pode executar templates auxiliares demais. A camada `AnswerProjector` escolhe a melhor resposta direta, mas o fan-out complementar ainda aumenta ruído e custo.
7. Os templates agora expõem `AnswerCapability`; isso melhora Leverage, mas também cria uma nova obrigação de manutenção: toda query nova deve declarar suas métricas e dimensões semanticamente.
8. `IntentResolver` passou a usar `policy_request` como bias analítico. Isso melhora UX, mas precisa continuar fraco o bastante para não executar SQL em small talk.

### 1.4 Dependências circulares ou nós de risco

Não há sinal de ciclo fatal atual, mas existem zonas de risco:

- `runtime/__init__.py`: ao exportar muitos símbolos, pode reintroduzir ciclos se contratos ou módulos de broker importarem runtime por conveniência.
- `broker/__init__.py`: mesmo risco para executor, templates, evidence e planner.
- `api/routes/chat.py`: não é ciclo, mas é um hub. Quanto mais regras entrarem ali, menor será a Locality.
- `contracts` já foi corrigido ao mover proveniência para `contracts/provenance.py`; isso deve ser preservado.

## 2. Mapeamento Ponta a Ponta do Processo (Caminhos e Fluxos)

### 2.1 Bootstrap

1. `api/main.py` carrega `OrionSettings`.
2. Configura logging e tracing.
3. Cria aplicação FastAPI.
4. No lifespan:
   - tenta criar pool MySQL e `AnalyticsExecutor`;
   - tenta criar pool Postgres e `PostgresConversationStateRepository`;
   - cria `ChatTurnEmbeddingStore` se embeddings estiverem ativos;
   - cria provider LLM real se há API key, senão `NullLLMProvider`.
5. Cria `SessionManager`.
6. Registra router `/api/v1`.

Fluxos alternativos:

- Sem MySQL: analytics é pulado.
- Sem Postgres: sessões ficam em memória local.
- Sem LLM real: provider nulo.
- Sem embeddings: memory segue episódica + lexical.
- Falha em inicialização de pool: loga e degrada.

```mermaid
sequenceDiagram
    participant APP as FastAPI_Lifespan
    participant CFG as OrionSettings
    participant MY as MySQLPool
    participant PG as PostgresPool
    participant LLM as LLMProvider

    APP->>CFG: carregar config
    APP->>MY: criar pool se ORION_MYSQL_URL
    MY-->>APP: executor ou analytics desabilitado
    APP->>PG: criar pool se ORION_POSTGRES_URL
    PG-->>APP: repo Postgres ou fallback in-memory
    APP->>LLM: criar OpenAIProvider ou NullLLMProvider
```

### 2.2 Happy path do chat analítico

1. Cliente envia `POST /api/v1/chat`.
2. `SessionManager` cria/obtém sessão.
3. Mensagem do usuário é persistida.
4. `IntentResolver` retorna `CognitivePlan`, usando `policy_request` como bias quando a política explícita é `analytical` e o texto parece pergunta de dados.
5. `HeuristicSignalCatalog` reaproveita regex existentes como sinais genéricos.
6. Se a intenção é ambígua, contextual ou comparativa, `AnalyticalIntentInterpreter` chama o LLM para produzir `AnalyticalIntentContract`.
7. `IntentContractValidator` aceita o contrato apenas se ele respeitar capabilities, enums, datas e fontes de comparação; se falhar, o plano heurístico permanece.
8. `MemoryRetrievalPipeline` retorna `ContextBlock[]`.
9. `analytics_guard` verifica `needs_analytics`, executor e allowlist.
10. `_run_analytics` expande planos e executa templates.
11. `AnswerProjector` escolhe a melhor `AnswerCapability` e gera `ProjectedAnswer`.
12. `EvidenceAggregator` produz `EvidenceBlock`, com resposta direta em primeiro plano e estatística complementar subordinada.
13. `CognitiveOrchestrator` injeta `system_prompt`, user turn, evidence, digest e memória.
14. Scheduler e allocator empacotam blocos.
15. `CognitiveNarrator` chama `LLMProvider`.
16. Resposta é persistida e retornada.

```mermaid
sequenceDiagram
    participant U as Usuario
    participant API as ChatAPI
    participant SM as SessionManager
    participant IR as IntentResolver
    participant HS as HeuristicSignals
    participant II as IntentInterpreter
    participant IV as IntentValidator
    participant MEM as MemoryRetrievalPipeline
    participant ANA as AnalyticsPipeline
    participant AP as AnswerProjector
    participant ORCH as CognitiveOrchestrator
    participant NAR as CognitiveNarrator
    participant LLM as LLMProvider

    U->>API: POST /api/v1/chat
    API->>SM: record_user_message
    API->>IR: resolve(message, policy_request)
    IR-->>API: CognitivePlan
    API->>HS: extract regex signals
    alt ambiguous_or_contextual
        API->>II: interpret(message, context, capabilities, signals)
        II-->>API: AnalyticalIntentContract
        API->>IV: validate(contract)
        IV-->>API: accepted CognitivePlan or fallback
    end
    API->>MEM: collect_blocks
    MEM-->>API: ContextBlock[]
    API->>ANA: expand + execute
    ANA->>AP: project(rows, capabilities)
    AP-->>ANA: ProjectedAnswer
    ANA->>ANA: aggregate + attach direct answer
    ANA-->>API: EvidenceBlock
    API->>ORCH: finalize_prompt
    ORCH-->>API: prompt_text
    API->>NAR: narrate
    NAR->>LLM: chat(messages)
    LLM-->>NAR: LLMResponse
    API->>SM: record_assistant_message
    API-->>U: ChatResponse
```

### 2.3 Fluxo de memória

1. `MemoryRetrievalPipeline` recebe `session_id`, query e retrievers.
2. Adiciona summary/essence se existir.
3. Executa `SemanticRetriever` lexical.
4. Executa `VectorRetriever` somente se `ORION_EMBEDDING_MODE=retrieve`.
5. Executa `EpisodicRetriever` para turnos recentes.
6. Deduplica e comprime se configurado.
7. Retorna blocos para o orquestrador.

```mermaid
sequenceDiagram
    participant API as ChatAPI
    participant PIPE as MemoryRetrievalPipeline
    participant SEM as SemanticRetriever
    participant VEC as VectorRetriever
    participant EPI as EpisodicRetriever

    API->>PIPE: collect_blocks(query)
    PIPE->>SEM: retrieve lexical
    SEM-->>PIPE: semantic_lexical blocks
    alt embedding_mode retrieve
        PIPE->>VEC: retrieve vector
        VEC-->>PIPE: vector blocks
    else off or index_only
        PIPE-->>PIPE: skip vector
    end
    PIPE->>EPI: retrieve recent turns
    EPI-->>PIPE: episodic blocks
    PIPE-->>API: ContextBlock[]
```

### 2.4 Fluxo analítico

1. `QueryExpander` escolhe templates e planos.
2. Cada plano executa via `AnalyticsExecutor`.
3. Templates SQL usam `date_from` e `date_to` vindos do `CognitivePlan.time_scope`.
4. `asyncio.gather(..., return_exceptions=True)` captura falhas individuais.
5. `AnswerProjector` avalia os resultados válidos contra `AnswerCapability`.
6. O melhor resultado vira `ProjectedAnswer`, usando a coluna correta para a pergunta (`ticket_medio`, `total_os`, `maior_recebimento`, `faturamento`, etc.).
7. `EvidenceAggregator` gera estatística complementar e anexa a resposta direta ao `EvidenceBlock`.
8. Se todos falham, fluxo segue sem evidence.

```mermaid
sequenceDiagram
    participant API as ChatAPI
    participant EXP as QueryExpander
    participant EXE as AnalyticsExecutor
    participant SQL as MySQL
    participant AP as AnswerProjector
    participant EVD as EvidenceAggregator

    API->>EXP: expand(CognitivePlan)
    EXP-->>API: SemanticQueryPlan[]
    par plano_1
        API->>EXE: execute_template(plan_1)
        EXE->>SQL: SELECT allowlisted
        SQL-->>EXE: rows
    and plano_N
        API->>EXE: execute_template(plan_N)
        EXE->>SQL: SELECT allowlisted
        SQL-->>EXE: rows
    end
    API->>AP: build_projected_answer(query, results)
    AP-->>API: ProjectedAnswer | None
    API->>EVD: aggregate(results)
    API-->>API: attach direct_answer before complementary summary
    EVD-->>API: EvidenceBlock
```

### 2.5 Fluxo Answer Capability

1. Cada módulo em `broker/queries/*.py` declara `MEASURES` e `DIMENSIONS`.
2. `QueryTemplateRegistry` converte essas declarações em `AnswerCapability`.
3. `AnswerProjector` infere `AnswerPlan` a partir da pergunta.
4. A projeção seleciona a métrica certa e materializa os valores no resumo.
5. O LLM recebe uma resposta direta antes da estatística complementar.

Exemplo de mapeamento:

```text
"Qual o ticket médio por concessionárias entre janeiro e abril de 2026?"
  -> template_slug = performance_concessionaria
  -> measure = ticket_medio_os
  -> dimension = concessionaria
  -> operation = list
  -> summary = lista materializada de concessionária: ticket_medio_os
```

```mermaid
sequenceDiagram
    participant TPL as QueryTemplate
    participant CAP as AnswerCapability
    participant PLAN as AnswerPlan
    participant PROJ as ProjectedAnswer
    participant EVD as EvidenceBlock

    TPL->>CAP: MEASURES + DIMENSIONS
    CAP->>PLAN: infer_answer_plan(query)
    PLAN->>PROJ: project rows by measure/dimension
    PROJ->>EVD: direct_answer + summary materializado
```

### 2.5.1 Fluxo de isolamento de contexto analítico

1. `IntentResolver` cria `CognitivePlan`.
2. `AnalyticalContextIsolationPolicy.decide()` bloqueia `VectorRetriever` em turnos analíticos simples.
3. O pipeline recupera memória episódica/lexical e, quando permitido, vetorial.
4. Analytics executa normalmente e produz `EvidenceBlock` atual.
5. `AnalyticalSignature` é derivada do `ProjectedAnswer.plan` e do `CognitivePlan.time_scope`.
6. A política filtra memória histórica antes do `CognitiveOrchestrator`.
7. O prompt final recebe a evidência atual e, no máximo, memória compatível ou conversacional mínima.

```mermaid
sequenceDiagram
    participant API as ChatAPI
    participant ISO as AnalyticalContextIsolationPolicy
    participant MEM as MemoryRetrievalPipeline
    participant ANA as AnalyticsPipeline
    participant SIG as AnalyticalSignature
    participant ORCH as CognitiveOrchestrator

    API->>ISO: decide(CognitivePlan)
    ISO-->>API: allow_vector_memory
    API->>MEM: collect_blocks
    MEM-->>API: memory_blocks
    API->>ANA: run current analytics
    ANA-->>API: EvidenceBlock atual
    API->>SIG: derive from EvidenceBlock + CognitivePlan
    SIG-->>API: signature
    API->>ISO: filter_blocks(memory, signature)
    ISO-->>API: isolated_memory_blocks
    API->>ORCH: evidence atual + memória isolada
```

A regra de produto é: **não clusterizar texto bruto; clusterizar, futuramente, episódios analíticos tipados**. Clusterização pode ajudar recall e continuidade, mas só depois que a assinatura analítica impedir mistura entre `ticket_medio`, `faturamento`, `volume` e `forma_pagamento`.

### 2.6 Streaming SSE

1. O mesmo pipeline cognitivo é montado.
2. `narrate_stream()` produz chunks.
3. A rota emite SSE.
4. No `finally`, persiste texto acumulado.

Risco: se a conexão cair após poucos chunks, o texto parcial pode ser persistido. Isso deve ser tratado como comportamento explícito ou enriquecido com metadado de completion.

```mermaid
sequenceDiagram
    participant API as ChatAPI
    participant NAR as CognitiveNarrator
    participant SM as SessionManager
    participant U as Usuario

    API->>NAR: narrate_stream
    loop chunks
        NAR-->>API: delta
        API-->>U: SSE data
    end
    API->>SM: record_assistant_message(texto acumulado)
    API-->>U: done
```

### 2.7 Fluxos de exceção e tratamentos

- **MySQL ausente:** analytics não executa; resposta pode sair sem evidência.
- **Postgres ausente:** sessão fica em memória local; não há persistência cross-process.
- **LLM ausente:** `NullLLMProvider`.
- **Embedding falha:** erro é logado; chat deve continuar.
- **Uma query falha:** resultado é descartado; evidence usa o restante.
- **Sem capability em template:** o template ainda pode gerar evidence por `VALUE_KEY`, mas não produz resposta direta projetada.
- **ProjectedAnswer ausente:** `EvidenceAggregator` continua funcionando, porém o LLM volta a depender do resumo estatístico.
- **Todas queries falham:** sem evidence.
- **Persistência falha:** tende a propagar como erro HTTP.
- **LLM retorna vazio:** resolvido parcialmente aumentando budget para modelos constrained; deve permanecer observável via log do narrator.

## 3. Diagnóstico de Problemas e Gargalos

### 3.1 Pontos cegos

1. **Pergunta analítica sem evidence real.** Quando MySQL está indisponível, o fluxo pode seguir para narração. O usuário deveria receber aviso explícito de que analytics não executou.
2. **Confidence heurística.** `CognitivePlan.confidence` não é calibrada estatisticamente. Deve ser tratada como sinal operacional, não probabilidade.
3. **Fan-out ainda ruidoso.** Mesmo com `ProjectedAnswer`, `_run_analytics` ainda executa templates auxiliares e agrega estatísticas complementares que podem competir com a resposta direta se o prompt ficar grande.
4. **AnswerCapability precisa ser mantida junto da query.** Se uma nova query retornar colunas úteis, mas não declarar `MEASURES`/`DIMENSIONS`, o pipeline volta ao comportamento antigo de `VALUE_KEY`.
5. **Duplicidade de instruções ao LLM.** `analytical_system_prompt` injeta regras e `narrator` também injeta anti-alucinação/cobertura. Isso pode ser aceitável, mas deve ser racionalizado para evitar conflito.
6. **Evidence em duas vias.** O `EvidenceBlock` entra no prompt principal e parte dele também entra no coverage note do narrator. Isso aumenta tokens e pode criar prioridade ambígua.
7. **Streaming parcial.** Persistir resposta parcial sem metadata pode confundir histórico.
8. **Histórico analítico como memória comum.** Mitigado por `AnalyticalContextIsolationPolicy`, mas ainda depende de bons metadados nos blocos futuros para permitir recall analítico rico sem contaminação.

### 3.2 Gargalos de performance

1. **Caminho crítico longo.** Persistência, memory retrieval, analytics, orchestration, LLM e persistência final acontecem na requisição.
2. **JSONB crescente em conversas.** Append de mensagem lê e regrava array inteiro, com lock por sessão. Isso degrada com histórico longo.
3. **`GET /sessions` pesado.** O limite padrão de mensagens completas por sessão é alto e pode gerar payloads muito grandes.
4. **Fan-out analytics sem orçamento dedicado.** Há paralelismo, mas não um Module claro para timeout, cancelamento, limite global ou circuit breaker.
5. **LLM constrained model.** Modelos como `gpt-5*` consomem tokens internos; sem budget adequado, podem retornar vazio.
6. **Resposta direta + resumo complementar aumentam prompt.** A projeção direta melhora a precisão, mas o resumo estatístico complementar ainda pode adicionar muitas linhas quando há fan-out.
7. **Embeddings no caminho de gravação.** Mesmo opcionais, se ativos podem adicionar latência externa ao turno.

### 3.3 Gargalos de concorrência

- `PostgresConversationStateRepository` serializa updates por conversa.
- Sessões in-memory não são distribuídas entre workers.
- Analytics concorrente pode saturar MySQL.
- LLM e embeddings não têm semaphore/rate limiter local.
- Streaming mantém requisição aberta e consome recursos por conexão.

### 3.4 Dívidas técnicas

1. `api/routes/chat.py` precisa virar Module de aplicação.
2. `_run_analytics` não deveria viver dentro da rota.
3. `AnswerProjector` ainda usa heurísticas lexicais simples; isso é aceitável como primeira camada, mas deve evoluir para ranking de capacidade mais explícito.
4. `ConversationStateRepository` precisa de Adapter Postgres append-only.
5. `ChatTurnEmbeddingStore` não deve conhecer `OpenAIEmbeddingService.to_pgvector`.
6. Barrels grandes devem ser reduzidos ou tratados como API pública estável.
7. Logs JSONL são úteis, mas métricas operacionais ainda faltam.

## 4. Plano de Ação e Melhorias

### Prioridade 1 — Deepen o Module de turno de chat

**Problema:** `api/routes/chat.py` concentra responsabilidades demais.

**Solução proposta:** extrair um Module `ChatTurnRunner` ou `ChatTurnService`.

**Interface sugerida:**

```python
result = await chat_turn_runner.run(request)
stream = chat_turn_runner.stream(request)
```

**O que fica atrás da Implementation:**

- sessão;
- persistência;
- intent;
- memory retrieval;
- analytics;
- orchestration;
- narration;
- tracing;
- estado cognitivo.

**Benefício:** aumenta Locality para bugs de chat e aumenta Leverage dos testes. Um teste de integração chamaria a Interface do turno e validaria comportamento sem passar por HTTP.

### Prioridade 2 — Extrair `AnalyticsPipeline`

**Problema:** `_run_analytics` é um pipeline real, mas está embutido na rota.

**Interface sugerida:**

```python
evidence = await analytics_pipeline.run(cognitive_plan, message, trace_context)
```

**Implementation escondida:**

- expandir planos;
- executar templates;
- projetar resposta direta com `AnswerProjector`;
- anexar `direct_answer` ao `EvidenceBlock`;
- aplicar timeout;
- descartar falhas parciais;
- agregar evidence;
- registrar trace.

**Benefício:** melhora testabilidade e torna explícito onde aplicar budget, cancelamento e observabilidade.

### Prioridade 3 — Harden Answer Capability

**Problema:** a camada `AnswerCapability` já corrige o erro mais grave, mas ainda depende de heurísticas lexicais e de manutenção manual nas queries.

**Melhorias recomendadas:**

- validar em teste que toda query registrada declara `MEASURES` e `DIMENSIONS` coerentes com suas colunas;
- registrar métricas `answer_project_present`, `answer_plan_measure`, `answer_plan_dimension`, `answer_plan_operation`;
- limitar ou reordenar o resumo complementar quando `ProjectedAnswer` existir;
- melhorar a seleção de template primário para reduzir fan-out ruidoso;
- tratar operações específicas como `top_and_bottom`, `list_all`, `ranking_by_period` e `single_entity_lookup`.

**Benefício:** mantém a resposta direta como fonte principal e reduz a chance de o LLM ser puxado por estatística genérica.

### Prioridade 4 — Criar Module temporal dedicado

**Problema:** parsing temporal já cresceu em `IntentResolver`. Ele é valioso, mas pode virar um subdomínio próprio.

**Interface sugerida:**

```python
date_range = temporal_resolver.resolve(text, today=date.today())
```

**Contrato:**

- `date_from`;
- `date_to`;
- `period_grain`;
- `period_source`;
- `confidence`;
- `original_text`.

**Benefício:** concentra a complexidade de datas em um seam pequeno, testável e reutilizável por planner/templates.

### Prioridade 5 — Migrar mensagens para append-only

**Problema:** JSONB crescente tem custo linear e lock por conversa.

**Solução proposta:**

- manter `conversation_state` para metadados;
- criar `conversation_messages`;
- escrever mensagens append-only;
- paginar histórico;
- manter Adapter in-memory compatível com a mesma Interface.

**Benefício:** melhora concorrência e performance sem alterar callers.

### Prioridade 6 — Racionalizar instruções ao LLM

**Problema:** `analytical_system_prompt` e `narrator` podem duplicar regras de cobertura/evidência.

**Solução proposta:**

- deixar `analytical_system_prompt` responsável por identidade, estrutura e regras analíticas;
- deixar `narrator` responsável apenas por chamar provider e registrar resultado;
- mover coverage note para metadata/bloco próprio ou removê-lo se evidence já estiver no prompt.

**Benefício:** prompt mais previsível, menor custo de tokens, menor risco de instruções conflitantes.

### Prioridade 7 — Seams de providers e budgets

**Problema:** providers externos têm comportamentos específicos e custos variáveis.

**Melhorias:**

- tornar budget por modelo configurável;
- adicionar timeout e retry limitado;
- logar `finish_reason`, model e token usage em nível controlado;
- manter teste de regressão para `gpt-5*` com `max_completion_tokens` mínimo.

### Prioridade 8 — Métricas e SLOs

Criar métricas por etapa:

- `intent_latency_ms`;
- `memory_latency_ms`;
- `analytics_latency_ms`;
- `orchestrate_latency_ms`;
- `llm_latency_ms`;
- `reply_chars`;
- `evidence_confidence`;
- `analytics_result_count`;
- `answer_project_present`;
- `answer_plan_measure`;
- `answer_plan_dimension`;
- `vector_hit_count`;
- `prompt_tokens`;
- `completion_tokens`.

SLOs sugeridos:

- p95 chat sem analytics;
- p95 chat com analytics;
- p95 tempo até primeiro chunk em streaming;
- taxa de respostas sem evidence em perguntas analíticas;
- taxa de `finish_reason=length`.

## 5. Diagramas de Sequência em Texto (Mermaid)

### 5.1 Arquitetura macro

```mermaid
flowchart TB
    API[api Module] --> Runtime[runtime Module]
    API --> Memory[memory Module]
    API --> Broker[broker Module]
    Runtime --> Contracts[contracts Module]
    Broker --> Contracts
    Memory --> Contracts
    Broker --> Answer[Answer Capability]
    Broker --> MySQL[(MySQL)]
    Memory --> Postgres[(Postgres)]
    Runtime --> Provider[LLMProvider Adapter]
    Memory --> Embedding[Embedding Adapter Opcional]
```

### 5.2 Turno de chat com analytics

```mermaid
sequenceDiagram
    participant API as ChatAPI
    participant SM as SessionManager
    participant IR as IntentResolver
    participant MEM as MemoryRetrievalPipeline
    participant ANA as AnalyticsPipeline
    participant AP as AnswerProjector
    participant ORCH as CognitiveOrchestrator
    participant NAR as CognitiveNarrator

    API->>SM: append user message
    API->>IR: resolve(user_message, policy_request)
    IR-->>API: CognitivePlan
    API->>MEM: collect_blocks(session, query)
    MEM-->>API: ContextBlock[]
    API->>ANA: run(plan, query)
    ANA->>AP: project_answer(results)
    AP-->>ANA: ProjectedAnswer
    ANA-->>API: EvidenceBlock
    API->>ORCH: finalize_prompt(plan, evidence, memory)
    ORCH-->>API: prompt_text
    API->>NAR: narrate(orchestration)
    NAR-->>API: NarrationResult
    API->>SM: append assistant message
```

### 5.3 Caminho alternativo sem analytics

```mermaid
sequenceDiagram
    participant API as ChatAPI
    participant IR as IntentResolver
    participant MEM as MemoryRetrievalPipeline
    participant ORCH as CognitiveOrchestrator
    participant NAR as CognitiveNarrator

    API->>IR: resolve
    IR-->>API: needs_analytics=false
    API->>MEM: collect_blocks
    MEM-->>API: memory blocks
    API-->>API: skip analytics
    API->>ORCH: finalize_prompt(evidence=None)
    API->>NAR: narrate
```

### 5.4 Degradação sem infraestrutura externa

```mermaid
sequenceDiagram
    participant APP as Lifespan
    participant MY as MySQL
    participant PG as Postgres
    participant LLM as LLM
    participant API as ChatAPI

    APP->>MY: tentar pool
    MY-->>APP: indisponível
    APP->>PG: tentar pool
    PG-->>APP: indisponível
    APP->>LLM: verificar API key
    LLM-->>APP: NullLLMProvider se ausente
    API-->>API: usar memória local e sem analytics
```

### 5.5 Memory Augmentation opcional

```mermaid
sequenceDiagram
    participant PIPE as MemoryRetrievalPipeline
    participant SEM as SemanticRetriever
    participant VEC as VectorRetriever
    participant EPI as EpisodicRetriever

    PIPE->>SEM: lexical retrieval
    alt ORION_EMBEDDING_MODE=retrieve
        PIPE->>VEC: vector retrieval
    else off/index_only
        PIPE-->>PIPE: skip vector
    end
    PIPE->>EPI: recent turns
    PIPE-->>PIPE: dedupe + compress
```

### 5.6 Analytics com falhas parciais

```mermaid
sequenceDiagram
    participant ANA as AnalyticsPipeline
    participant EXE as AnalyticsExecutor
    participant AP as AnswerProjector
    participant AGG as EvidenceAggregator

    ANA->>EXE: execute plan 1
    ANA->>EXE: execute plan 2
    ANA->>EXE: execute plan N
    EXE-->>ANA: results + exceptions
    ANA-->>ANA: discard exceptions
    alt any valid result
        ANA->>AP: project direct answer
        AP-->>ANA: ProjectedAnswer | None
        ANA->>AGG: aggregate(valid_results)
        AGG-->>ANA: EvidenceBlock
        ANA-->>ANA: prepend direct answer if present
    else none valid
        ANA-->>ANA: evidence=None
    end
```

### 5.7 Answer Capability

```mermaid
sequenceDiagram
    participant Q as QueryTemplate
    participant C as AnswerCapability
    participant P as AnswerProjector
    participant E as EvidenceBlock
    participant L as LLM

    Q->>C: MEASURES + DIMENSIONS
    P->>C: infer measure/dimension/operation
    P-->>E: direct_answer summary + rows
    E-->>L: resposta direta antes da estatística complementar
```

### 5.8 Provider LLM constrained model

```mermaid
sequenceDiagram
    participant NAR as CognitiveNarrator
    participant OAI as OpenAIProvider
    participant API as OpenAI_API

    NAR->>OAI: chat(messages)
    OAI-->>OAI: choose max_completion_tokens for constrained model
    OAI->>API: chat.completions.create
    API-->>OAI: choices + usage + finish_reason
    OAI-->>NAR: LLMResponse
```

## Conclusão

O Orion tem um núcleo promissor porque seus contratos já apontam para um runtime analítico governado por evidência, atenção e proveniência. O principal trabalho arquitetural agora não é adicionar mais camadas, mas **aprofundar módulos existentes**:

1. transformar `routes/chat.py` em uma Interface de aplicação menor;
2. tornar analytics um Module profundo;
3. fortalecer `AnswerCapability` como contrato obrigatório de query;
4. isolar interpretação temporal;
5. trocar persistência JSONB crescente por append-only;
6. manter Memory Augmentation opcional e simples;
7. tornar provider/LLM budgets observáveis e configuráveis.

Essa direção aumenta **Leverage** para callers e testes, e aumenta **Locality** para manutenção: bugs de chat ficam no Module de turno, bugs de analytics no Module analítico, bugs de resposta por métrica ficam no `AnswerProjector`, bugs temporais no temporal resolver, e bugs de provider no Adapter externo.
