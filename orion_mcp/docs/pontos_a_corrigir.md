Com base na leitura de `orion_mcp/docs/orion_mcp_plano_implementacao.md` e no que existe em `orion_mcp/`, segue o **mapeamento por secção** (o YAML no topo do plano já marca todos os todos como `completed`, mas a **matriz textual** tem nuance).

---

### Secção 0 — Princípios obrigatórios  
**Em grande parte implementada** no código (`LLMProvider` só texto, `decide` puro, `ChatRequest` sem transcript, `build_context` por secções, tools + cache).  
**Verificação por testes:** só **parcialmente** alinhada ao plano (já detalhámos noutra resposta: faltam testes explícitos de “LLM sem persistência”, cache hit idempotente, tabela exaustiva de `decide`, etc.).

---

### Secção 1 — Árvore `/api` + `core/` + `infra/`  
**Implementada.** Há `api/`, `core/` (orchestrator, state, memory, context, decision, tools, llm, formatter), `infra/` (db, cache, queue, observability), `mcp_adapter/`.  
**Nota:** o plano fala em ficheiros sob `core/orchestrator/` com nomes tipo `decision_engine.py`; na prática a **Decision Engine** está em `core/decision/` — mesmo papel, layout ligeiramente diferente.

---

### Secção 2.1 — State engine  
**Implementada:** migração `conversation_state`, `State` Pydantic, `PostgresStateRepository` / memória, `StateManager`, `update_state` sem LLM em `transitions.py`.

---

### Secção 2.2 — Memory system OK
**Parcial / maioritariamente:** short-term (`short_memory` + `update_short_memory` sem LLM); long-term com `memory_embeddings` + pgvector + `retrieve_memory` com filtros metadata.  
**Em falta ou mais fraco vs plano:** índices **IVFFlat/HNSW** (só índices simples na migração); **worker Celery** é essencialmente **placeholder** (fila “para embed” não é um pipeline completo de indexação); `insert_memory_embedding` **não está ligado** ao fluxo do chat.

---

### Secção 2.3 — Tool system
**Implementada** na linha principal: `Tool`, args Pydantic, `tool_key`, cache Redis/memória, `summarize_tool_result`, timeout na tool.  
**Parcial:** não há **lint rule** “sem LLM dentro da tool”; testes de **cache hit → mesmo summary** e contract read-only **não** estão tão completos como a matriz descreve.

---

### Secção 2.4 — Decision engine
**Implementada:** `Action` fixa, quatro actions, `FORMAT_RESPONSE` sem novo LLM no ramo correspondente, testes em `test_decision_engine.py`.  
**Nota:** o orçamento de tool/LLM é aplicado sobretudo no **orquestrador + `RequestBudget`**, não “dentro” só da `DecisionEngine` como o diagrama do plano às vezes sugere.

---

### Secção 2.5 — Context builder
**Implementada:** `build_context` com as secções pedidas, truncagem e tetos em `Settings`.  
**Testes:** existem (`test_context_builder.py`), mas **não** cobrem explicitamente “proibição de JSON bruto” além do desenho por summaries.

---

### Secção 2.6 — LLM layer OK
**Parcial:** `LLMProvider.generate` + OpenAI/mock + `resolve_model` por estratégia; **streaming opcional** — **não** implementado.  
Tabela “reasoning / fast / embeddings” em `Settings` existe de forma **prática** (modelos + `embedding_model`), não como um mapa único documentado tipo tabela.

---

### Secção 2.7 — Formatter  
**Implementada:** `FormatRequest` + `format_response` sem `State`.

---

### Secção 2.8 — Orchestrator  
**Implementada** o fluxo `load → update_state → decide → tool → … → build_context → llm → format → update_short_memory → save_state`.  
O ficheiro `orchestrator.py` ainda tem **alguma** lógica (ex.: ramos de insights, memória longa, `_infer_format`) — não é só “fios” vazios, mas está **alinhado** ao que um orquestrador fino costuma ter.

---

### Secção 3 — Performance OK
**Parcial:** `max_llm_calls_per_request`, `max_tool_calls_per_request`, `BudgetExceeded`, `tool_timeout_seconds` + `wait_for` nas tools; `max_tokens` limitado na chamada LLM.  
**Fraco vs plano:** **fallback parcial** com flags no payload UI **não** está como descrito (só `force_refresh` em `flags` para outro fim); **“&lt; 3k tokens por chamada”** depende de `context_max_tokens` na config (pode ser violado se alguém subir muito esse valor).

---

### Secção 4 — Observabilidade  
**Parcial:** métricas Prometheus (`CHAT_*`), `/metrics`; OTEL com **setup** em `tracing.py` (ex.: consola), **sem** evidência clara de **spans por etapa** (`load_state`, `decide`, …) no orquestrador; **Grafana** via `docker-compose.observability.yml` existe como stack opcional; **`tokens_used`** nas métricas do chat costuma ficar **`null`** se não for preenchido a partir da API.

---

### Secções 5–7 — Stack, diferencial, roadmap  
**Stack (5):** conforme.  
**Diferencial vs v1 (6):** sobretudo **documentado** na matriz/plano, não é “código de migração” do `project_mcp_v1`.  
**Roadmap (7):** na prática o núcleo cobre **Fases 1–4** do quadro (linhas 307–313) de forma **sólida mas com lacunas** acima; **Fase 5** (OTEL rico, logs JSON por passo, dashboard Grafana “mínimo” com cache hit, etc.) está **só parcialmente** cumprida.

---

### Texto preventivo (1–14) + Skills  
**Grande parte endereçada** (Settings, CI, docs/TRACEABILITY, scripts de docs, MCP fora do hot path HTTP, write-through, etc.).  
**Pontos ainda fracos:** p.ex. **métricas de cache hit** no Prometheus como no plano; **MCP “handlers partilhados com o registry”** — o `mcp_adapter` chama a **mesma classe** stub, mas **não** delega ao `ToolRegistry`/cache HTTP de forma unificada.

---

## Resposta curta à pergunta “até que secção”

- **Até à Secção 2.8 (núcleo funcional):** **sim**, com **ressalvas** em 2.2 (vector avançado + worker), 2.3 (testes/guardas extras) e 2.6 (streaming).  
- **Secção 3:** **parcial**.  
- **Secção 4 + Fase 5 do roadmap:** **parcial**.  
- **Secções 5–7:** **documentação / posicionamento** mais do que “código novo”; o **roadmap completo até Fase 5 “verde” no sentido estrito do plano** **não** está todo fechado.

Os todos YAML no topo do ficheiro (linhas 5–43) dizem `completed` para *scaffolding* e entregas nomeadas; isso reflecte **gestão de projecto**, não equivalência 1:1 com **cada linha** da matriz de verificação.