# Relatório de Alinhamento Arquitetural

**Sistema:** Orion MCP v3 — plataforma de analytics conversacional com pipeline cognitivo  
**Data da auditoria:** 2026-05-05  
**Plano de referência:** composição de `docs/architecture/ORION_V3_MASTER_ARCHITECTURE.md`, `docs/execution/PLANO_EXECUCAO.md`, `docs/guides/ORDEM_IMPLEMENTAÇÃO.md`, `docs/roadmaps/ROADMAP_COM_MYSQL_INTEGRADO.md`  
**Escopo auditado:** código em `orion_mcp_v3/src/orion_mcp_v3/`, testes em `orion_mcp_v3/tests/`, evidência em `orion_mcp_v3/logs/*.jsonl`  
**Agente:** `agente_alinhamento_codigo` (protocolo `auditoria_completa`, 6 passes)

---

## 1. Sumário executivo

O código **implementa de forma substancial** o pipeline documentado **pergunta → intenção heurística → plano semântico → SQL compilado com allowlist → execução MySQL com parâmetros → evidência → redução/map-reduce → drift guard → memória episódica/semântica → fusão de contexto → agendamento → orçamento de tokens → renderização de prompt**. O teste de integração `tests/test_integration_ordem_ate_planner_cognitivo.py` gera **JSONL auditável** em `logs/`, e um ficheiro representativo (`integration_pipeline_20260511T095330Z.jsonl`) confirma **28 passos** até `cognitive_orchestrator` com **prompt_text** materializado — ou seja, o **fecho cognitivo local** (fusão + scheduler + allocator + `render_blocks_to_prompt`) **está presente e exercitado em runtime de integração**.

A documentação de **produto completo** (`ROADMAP_COM_MYSQL_INTEGRADO.md`) ainda lista **FastAPI `/api/v1/chat`** como não implementado; no **`src/`** não há aplicação HTTP — o binário de entrega é **biblioteca + testes + script de integração**. Isso **não contradiz** o pacote como *foundation*, mas é um **gap explícito** face ao roadmap “chat funcional exposto por API”.

O **narrador LLM** não aparece como cliente HTTP ou serviço OpenAI no pacote: há **contratos e texto de sistema** orientados a narrativa (`runtime/context_builder.py`, `protocols/summarizer.py`), mas o **passo final “chamar modelo e devolver resposta ao utilizador”** permanece **fora** do núcleo auditado — alinhado com um estágio em que o **prompt final** é o artefacto entregue ao “LLM externo ou camada de produto”.

Os **princípios de segurança SQL** estão **majoritariamente respeitados**: identificadores passam por validação de allowlist; valores são passados como **`%s`** com tupla de parâmetros em `MysqlDatastoreClient.select`. O compilador monta SQL com **f-string apenas sobre fragmentos já validados** (`_quote_ident`, tabelas/colunas allowlisted), o que é **distinto** de interpolar input livre do utilizador no SQL.

**Pontos mais críticos a endereçar:** (1) **produto HTTP + narrador** se o milestone for “copilot utilizável”; (2) **documentar/clarificar** que o `AnalyticsExecutor` é um **ponto de entrada legítimo** ao broker (não viola “único orquestrador” se o contrato de produto for “orquestrador = camada de turno HTTP”, ainda não existente); (3) **drift_guard** no log recomenda refresh sem canal obrigatório até ao utilizador — falta política de narração quando integrar LLM.

---

## 2. Score de alinhamento

| Componente (skill) | Score | Classificação | Notas |
|---------------------|-------|---------------|-------|
| planner (`broker/planner.py`) | 0.88 | Majoritariamente alinhado | Recebe `CognitivePlan`; hints ricos no log |
| semantic_query_compiler | 0.90 | Alinhado | `compile_semantic_query_plan` + merge de hints |
| sql_compiler (`broker/sql_compiler.py`) | 0.92 | Alinhado | Allowlist + binding; f-string só em IDs validados |
| executor (`broker/executor.py`) | 0.85 | Majoritariamente alinhado | `default_limit`; sem timeout explícito na classe |
| aggregator / samplers / reducers | 0.86 | Majoritariamente alinhado | Coberto por testes e pelo JSONL |
| evidence_builder | 0.88 | Majoritariamente alinhado | Provenance no evidence block |
| digest / map_reduce | 0.84 | Majoritariamente alinhado | Digest textual; ratio vs plano não centralizado |
| memory_episodic / semantic | 0.82 | Majoritariamente alinhado | Repositórios + composer; depende de Postgres/pgvector em deploy |
| context_fusion | 0.87 | Majoritariamente alinhado | Camadas + dedupe; ordem global documentada vs scheduler |
| budget_allocator / scheduler | 0.86 | Majoritariamente alinhado | `max_tokens` configurável no orchestrator |
| drift_guard | 0.80 | Majoritariamente alinhado | Sinal forte; falta ligação ao narrador |
| cognitive_orchestrator | 0.89 | Majoritariamente alinhado | Implementado; não é único entrypoint do repo |
| narrator (LLM) | 0.35 | Desalinhado vs produto completo | Prompt sim; chamada modelo ausente no `src` |
| API HTTP | 0.15 | Desalinhado vs roadmap MySQL Fase 4 | Apenas documentação |

**Score geral estimado (heurística da skill): ~0.78** — **Majoritariamente alinhado** com o **runtime cognitivo + dados**; **parcial** no **fecho de produto** (API + LLM).

---

## 3. Mapeamento (Passo 1 — cobertura vs plano)

| Esperado na documentação | Presente no código | Evidência |
|--------------------------|---------------------|-----------|
| Connection hub MySQL/PG/Redis | Sim | `connection_hub/` |
| SemanticQueryPlan + compiler | Sim | `contracts/query_plan.py`, `broker/semantic_query_compiler.py`, `sql_compiler.py` |
| AnalyticsExecutor | Sim | `broker/executor.py` |
| IntentResolver + CognitivePlan | Sim | `runtime/intent_resolver.py`, `contracts/cognitive_plan.py` |
| EvidenceBuilder + Digest | Sim | `broker/evidence_builder.py`, `contracts/digest.py` |
| Map-reduce / drift | Sim | `broker/map_reduce.py`, `runtime/drift_guard.py` |
| Memória episódica + semântica | Sim | `memory/episodic_retriever.py`, `semantic_retriever.py`, `composer.py` |
| ContextFusion + allocator + scheduler | Sim | `runtime/context_fusion.py`, `budget_allocator.py`, `scheduler.py` |
| CognitiveOrchestrator | Sim | `runtime/cognitive_orchestrator.py` |
| Narrador LLM | Parcial | Contratos/prompt; sem cliente LLM no pacote |
| FastAPI chat | Não no `src` | Roadmap ☐; apenas notas |

---

## 4. Princípios arquiteturais (Passo 2)

| Princípio | Status | Evidência |
|-----------|--------|-----------|
| SQL apenas via allowlist; sem interpolação de input livre | ✅ IMPLEMENTADO | `SqlAllowlist`, `_validate_table` / `_validate_columns`; `compile_select` |
| Valores via binding | ✅ IMPLEMENTADO | `MysqlDatastoreClient.select` → `cur.execute(query, args)` |
| Provenance / cobertura na evidência | ✅ IMPLEMENTADO | `EvidenceBlock.provenance`, `coverage` no JSONL |
| Contexto com orçamento de tokens | ✅ IMPLEMENTADO | `allocate(..., max_tokens=...)` em `CognitiveOrchestrator.finalize_prompt` |
| Memória episódica vs semântica separadas | ✅ IMPLEMENTADO | Dois retrievers + composer |
| Planner decide / executor executa | ⚠️ PARCIAL | `AnalyticsExecutor` também chama `IntentResolver` + `build_query_plan` — duplo caminho cognitivo possível se outro caller já passou plano |
| Orquestrador único ponto de entrada | ⚠️ PARCIAL | Vários entrypoints library-grade (`AnalyticsExecutor`, `CognitiveOrchestrator`, testes); ok para SDK, diverge do anti-padrão “só orchestrator” se interpretado literalmente |

---

## 5. Anti-padrões (Passo 3)

| ID | Severidade | Achado | Ficheiro / notas |
|----|------------|--------|------------------|
| AP1 | COSMÉTICO / falso positivo | `f"SELECT {select_list} FROM..."` em `sql_compiler.py` | Identificadores construídos após allowlist — **não** é equivalente a SQL dinâmico com texto do utilizador |
| AP2 | Não encontrado | `exec()` / `eval()` | — |
| AP3 | MODERADO | LLM sem evidência no contexto | No pacote não há LLM; quando integrar, **deve** receber `prompt_text` já com blocos DATA |
| AP4 | MODERADO | “Bypass” do orquestrador | `AnalyticsExecutor.execute` é pipeline direto texto→MySQL — aceitável como **camada broker**; documentar como entrypoint suportado |

---

## 6. Contratos de interface (Passo 4)

| Interface documental → código | Avaliação |
|-------------------------------|-----------|
| Planner ← `CognitivePlan` | ✅ Teste de integração exige planner cognitivo (`build_query_plan(cognitive, ...)`) |
| `SemanticQueryPlan` → `compile_select` / `compile_semantic_query_plan` | ✅ JSONL mostra `merged_hints_keys`, SQL e `param_count` |
| Executor → linhas + provenance downstream | ✅ Rows para evidence; provenance nas estruturas de evidência/agregação |
| Fusion → blocos únicos ordenados | ✅ `ContextFusionResult` + `layer_priority` no log |
| CognitiveOrchestrator → `CognitiveOrchestrationResult` | ✅ `prompt_text` + contagens no último passo do JSONL |

---

## 7. Coerência interna e testes (Passo 5)

- **Testes:** 23 ficheiros `test_*.py` cobrindo foundation, broker, memória, fusão, orchestrator, integração.
- **Logging estruturado:** `integration_pipeline_logger.py` + JSONL por corrida — **forte rastreabilidade** para auditoria.
- **Logs vs código:** Ordem dos passos no JSONL corresponde ao fluxo descrito no docstring de `test_integration_ordem_ate_planner_cognitivo.py` (até `run_done`).
- **Drift:** `prior_volume` vs `current_volume` no log — cenário de teste; política de produto ainda a definir quando integrar LLM.

---

## 8. Parâmetros configuráveis (levantamento resumido)

| Parâmetro | Onde | Impacto |
|-----------|------|---------|
| `max_tokens` | `CognitiveOrchestrator.finalize_prompt(default=4096)` | Alto — tamanho do prompt final |
| `MYSQL_URL` / `ORION_MYSQL_URL` | Integração / pools | Crítico para execução real |
| `default_limit` | `AnalyticsExecutor` | Médio — limite de linhas SQL |
| Allowlist em testes de integração | `_integration_sql_allowlist()` | Crítico — define superfície SQL |

*Não há ficheiro único `Settings` pydantic no `src` auditado; configuração dispersa por env e argumentos — **moderado** risco de drift de config entre ambientes.*

---

## 9. Impressões técnicas (Passo 6)

1. **Qualidade de engenharia:** Separação `contracts/` vs `runtime/` vs `broker/` está **clara**; testes de integração com MySQL real são **above average** para projetos de research/spike.

2. **Alinhamento com `ORDEM_IMPLEMENTAÇÃO.md`:** Itens até ~23 (`cognitive_orchestrator.py`) **existem**; a “ordem” do doc é também **ordem de dependência conceitual** — o código **não viola** ao ter executor e orchestrator em módulos separados.

3. **Distância até o plano “produto completo”:** Uma camada **HTTP + persistência de sessão de chat + LLM** (como em `ROADMAP_COM_MYSQL_INTEGRADO.md` Fase 4) **ainda não está no pacote** — gap **esperado** se o foco foi foundation.

4. **Logs:** O passo `cognitive_orchestrator` mostra **ordem final** `fusion:user_turn` → memória → evidence → digest no prompt renderizado; **duplicação textual** (user turn repetido com msg da memória) é visível — pode ser **intencional** (reforço) ou merecer **dedupe** na camada de render — **moderado**.

---

## 10. Plano de ação recomendado

| Prioridade | Ação | Esforço | Impacto |
|------------|------|---------|---------|
| 🔴 Alta | Implementar **serviço HTTP** (`/api/v1/chat`) conforme roadmap, chamando pipeline existente + LLM | Grande | Produto utilizável |
| 🔴 Alta | Integrar **cliente LLM** consumindo `CognitiveOrchestrationResult.prompt_text` + política de **drift** na resposta | Médio | Fecho narrativo |
| 🟡 Média | Centralizar **settings** (timeouts MySQL, default_limit, max_tokens por ambiente) | Médio | Operacionalização |
| 🟡 Média | Documentar **entrypoints** suportados: só library vs HTTP futuro | Baixo | Evitar violação percebida do “único orchestrator” |
| 🟢 Baixa | Opcional: **EXPLAIN** / cache de planos — após carga | Variável | Performance |

---

## 11. JSON de retorno (formato skill)

```json
{
  "agente_id": "agente_alinhamento_codigo",
  "pode_responder": true,
  "resumo_executivo": {
    "score_geral": 0.78,
    "classificacao": "Majoritariamente alinhado",
    "desvios_criticos": 0,
    "desvios_moderados": 3,
    "desvios_cosmeticos": 1,
    "componentes_ausentes": ["narrator_llm_service", "fastapi_chat_endpoint"],
    "componentes_alinhados": ["sql_compiler", "mysql_backend_params", "intent_resolver", "evidence_builder", "context_fusion", "cognitive_orchestrator"],
    "acao_mais_urgente": "Expor turno completo via API + chamada LLM com prompt já fundido"
  },
  "limitacoes_da_resposta": "Análise estática + logs de integração; comportamento em produção com tráfego real pode diferir.",
  "logs_referencia": ["orion_mcp_v3/logs/integration_pipeline_20260511T095330Z.jsonl"]
}
```

---

*Auditoria gerada conforme skill `agente_alinhamento_codigo` — documento Markdown estruturado (`gerar_documento: true`).*
