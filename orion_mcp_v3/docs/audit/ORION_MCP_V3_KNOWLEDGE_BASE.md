# Base de Conhecimento Técnico — Orion MCP v3
## Extraído de histórico de conversas analíticas e logs de pipeline
**Versão:** 1.0 | **Fonte:** analytics_pipeline_20260605T210004Z.jsonl + orion_mcp_v3 structure

---

# KB-001: Pipeline de Fechamento Gerencial — Rejeições Silenciosas em Etapas de Interpretação

- **Contexto:** Orion MCP v3 — etapas `intent_interpret` e `answer_present` dentro do `analytics_pipeline`, ativadas por qualquer pedido de fechamento gerencial mensal.
- **Sintoma/Erro:** Para pedidos como *"fechamento gerencial de agosto de 2025"* ou *"fechamento gerencial de maio de 2026"*, o pipeline registra duas rejeições consecutivas:
  1. `intent_interpret` → `rejected_reason: unsupported_operation`
  2. `answer_present` → `rejected_reason: unsupported_template`
  O sistema **não falha visivelmente** — o fechamento é gerado corretamente — mas o custo oculto é 2–3 chamadas LLM a mais por request.
- **Causa Raiz:** O `analytical_intent_interpreter.py` tenta mapear a utterance a uma tupla `(operation, metric, dimension)` individual. A expressão "fechamento gerencial" não possui binding nesse modelo granular, resultando em `unsupported_operation`. Downstream, o `answer_presentation_interpreter.py` não possui branch para `selection_kind == "collection"`, somente para `selection_kind == "template"`.
- **Solução Técnica:** Implementada via contrato explícito de coleção, sem alterar `config/allowlists.py` (esse arquivo é allowlist SQL de tabelas/colunas).
  1. Adicionar detecção determinística de coleção em `analytical_intent_interpreter.py` antes da chamada LLM:
  ```python
  if "fechamento gerencial" matches a registered collection card:
      return AnalyticalIntentContract(
          accepted=True,
          operation="collection",
          collection_slug="fechamento_gerencial_por_mes",
      )
  ```
  2. Adicionar branch para `selection_kind == "collection"` em `answer_presentation_interpreter.py`:
  ```python
  if selection.selection_kind == "collection":
      return AnswerPresentationContract(
          result_scope={"mode": "all", "limit": None},
          reason="collection_default_presentation",
      )
  ```
  3. Adicionar `AnalyticalOperation.COLLECTION`, `collection_slug` em `AnalyticalIntentContract` e validação por `QueryCapabilityCatalog.collection_card()`.
- **Tags:** `[Performance, LLM-Cost, intent_interpreter, answer_present, collection, fechamento_gerencial]`

---

# KB-002: Fanout SQL do Fechamento Gerencial — Paralelismo Precisa Ser Testado e Mensurável

- **Contexto:** `src/orion_mcp_v3/api/routes/chat.py` — `_run_analytics` expande a coleção `fechamento_gerencial_por_mes` em 9 templates SQL e despacha a execução via `asyncio.gather`.
- **Sintoma/Erro:** O log original mostrava `analytics_execute[N] pre` e `post` em ordem de índice. Sem timestamps e duração por execução, essa ordem era inconclusiva: os `post` eram registrados depois do `gather`, também em ordem de índice, então o JSONL não permitia provar serialização nem paralelismo.
- **Causa Raiz:** Ausência de teste de regressão para concorrência real no fanout e ausência de campos temporais no `analytics_pipeline_trace.py`. O fanout atual pertence ao pipeline da rota, não ao `AnalyticsExecutor`, que executa um plano/template individual por chamada.
- **Solução Técnica:**
  ```python
  # api/routes/chat.py
  import asyncio

  async def _exec_one(plan):
      started = time.perf_counter()
      try:
          result = await execute_template_or_plan(plan)
          return result, elapsed_ms(started)
      except Exception as exc:
          return exc, elapsed_ms(started)

  async def execute_fanout(plans):
      tasks = [_exec_one(plan) for plan in plans]
      results = await asyncio.gather(*tasks, return_exceptions=True)
      log analytics_execute[N].post com duration_ms para sucesso e erro
      return somente os resultados válidos
  ```
  Adicionar também `timestamp_utc` e `timestamp_ms` a todo evento emitido por `analytics_pipeline_trace.py`. Proteger com testes que provam `max_active > 1` no fanout da coleção e que falha parcial em um template não descarta resultados válidos.
- **Tags:** `[Performance, Paralelismo, executor, MySQL, fechamento_gerencial, asyncio]`

---

# KB-003: `fechamento_parcelamento_cartao` — Linhas com Período Errado (Leak de Datas)

- **Contexto:** Template `fechamento_parcelamento_cartao` em `src/orion_mcp_v3/broker/queries/fechamento_parcelamento_cartao.py` e `docs/queries/fechamento_gerencial_por_mes/ParcelamentoCartao.sql`.
- **Sintoma/Erro:** Em fechamentos mensais, o `first_row_sample` retorna `"periodo": "2025-03"` quando o fechamento solicitado é de agosto/2025. Linhas de outros meses aparecem no resultado com `total: "0.00"`.
- **Causa Raiz:** A SQL filtra `os.data_pagamento` no WHERE mas agrupa e formata o período usando `cx.data_pagamento` (data de lançamento no caixa), que pode diferir da data de pagamento da OS. Isso faz o GROUP BY criar grupos para datas fora do período filtrado.
- **Solução Técnica:**
  ```sql
  -- ParcelamentoCartao.sql — substituir no SELECT e GROUP BY:

  -- ANTES (problemático):
  SELECT DATE_FORMAT(cx.data_pagamento, '%%Y-%%m') AS periodo, ...
  GROUP BY cx.quant_parcelas, DATE_FORMAT(cx.data_pagamento, '%%Y-%%m')

  -- DEPOIS (correto):
  SELECT DATE_FORMAT(os.data_pagamento, '%%Y-%%m') AS periodo, ...
  GROUP BY cx.quant_parcelas, DATE_FORMAT(os.data_pagamento, '%%Y-%%m')
  ```
  Adicionar também filtro no WHERE para o campo de caixa se necessário: `AND cx.data_pagamento >= %s AND cx.data_pagamento < DATE_ADD(%s, INTERVAL 1 DAY)`.
- **Tags:** `[Bug, SQL, data_pagamento, parcelamento_cartao, MySQL, fechamento_gerencial]`

---

# KB-004: Templates com Zero Linhas São Omitidos Silenciosamente do Fechamento

- **Contexto:** `src/orion_mcp_v3/broker/evidence_aggregator.py` — etapa `analytics_merge` do pipeline.
- **Sintoma/Erro:** Em agosto/2025, os templates `fechamento_producao_produto` e `fechamento_faturamento_tipo_venda_produtos` retornam `row_count: 0`. O fechamento gerado ao usuário omite essas seções sem informar que não havia dados. O usuário pode interpretar a ausência como dado não disponível ou como erro do sistema.
- **Causa Raiz:** O `analytics_merge` itera sobre os resultados e, quando `row_count == 0`, simplesmente não adiciona a seção ao summary. Não há flag de "seção ausente" propagada para a narrativa.
- **Solução Técnica:**
  Em `evidence_aggregator.py`:
  ```python
  def merge_results(self, results: list[TemplateResult]) -> MergedEvidence:
      summary_sections = []
      missing_sections = []

      for result in results:
          if result.row_count == 0:
              missing_sections.append(result.template_slug)
              summary_sections.append(
                  f"## {result.label}\n_Sem registros para o período solicitado._\n"
              )
          else:
              summary_sections.append(self._format_section(result))

      return MergedEvidence(
          summary="\n".join(summary_sections),
          missing_sections=missing_sections,
      )
  ```
  O `analytical_reasoner.py` deve incluir `missing_sections` nos `risks` do output para que o narrador mencione as seções ausentes.
- **Tags:** `[UX, analytics_merge, evidence_aggregator, zero_rows, fechamento_gerencial, transparência]`

---

# KB-005: Conflito de Prefixo Numérico nas Migrações PostgreSQL

- **Contexto:** `src/orion_mcp_v3/infra/postgres/migrations/` — dois arquivos com prefixo `003`.
- **Sintoma/Erro:** Dois arquivos coexistem com o mesmo prefixo:
  - `003_conversation_external_id.sql`
  - `003_memory_embeddings.sql`
  O script `scripts/apply_migrations.py` ordena por nome de arquivo. A ordem de aplicação entre esses dois é ambígua e pode variar por sistema operacional (ordering de `glob` ou `os.listdir`).
- **Causa Raiz:** Renomeação ou criação manual sem verificar o próximo índice livre.
- **Solução Técnica:**
  Renomear imediatamente:
  ```bash
  git mv 003_memory_embeddings.sql 003b_memory_embeddings.sql
  # ou
  git mv 003_memory_embeddings.sql 004_memory_embeddings.sql
  # ajustar 004_memory_curta.sql → 005_memory_curta.sql, etc.
  ```
  Em `scripts/apply_migrations.py`, adicionar validação na inicialização:
  ```python
  prefixes = [f.split("_")[0] for f in migration_files]
  if len(prefixes) != len(set(prefixes)):
      raise ValueError("Prefixos de migração duplicados detectados!")
  ```
- **Tags:** `[Infraestrutura, PostgreSQL, migrações, Bug, naming-convention]`

---

# KB-006: Como Funciona o Pipeline Analítico do Fechamento Gerencial (Referência)

- **Contexto:** Fluxo end-to-end do Orion MCP v3 para requests do tipo `fechamento_gerencial_por_mes`.
- **Sintoma/Erro:** N/A — entrada de referência arquitetural.
- **Causa Raiz:** N/A
- **Solução Técnica:** O pipeline percorre as seguintes etapas em ordem:

  ```
  1. intent_resolve        → classifica como "analytical"
  2. intent_interpret      → tenta parse granular (rejeita para coleções — ver KB-001)
  3. query_select          → seleciona collection_slug = "fechamento_gerencial_por_mes" via LLM
  4. answer_present        → tenta mapear apresentação (rejeita para coleções — ver KB-001)
  5. period_gate           → valida e propaga date_from / date_to
  6. memory_retrieve       → busca blocos de memória vetorial (pgvector)
  7. analytics_guard       → valida permissão e tipo de executor
  8. analytics_expand      → expande coleção em 9 query plans (fanout)
  9. semantic_plan         → compila planos semânticos
  10. analytics_execute[0–8] → executa 9 queries MySQL (idealmente em paralelo)
  11. analytics_merge       → agrega resultados em evidence summary
  12. answer_project        → projeta resultado customizado (ausente em coleções)
  13. analytics_outcome     → gera evidence_contract com confidence scores
  14. evidence_contract     → valida integridade do evidence
  15. context_isolation     → decide quais blocos de memória manter
  16. analytical_reasoner   → extrai facts, insights, risks do evidence
  17. cognitive_orchestrate → empacota prompt com evidence + system + memory
  18. narrate              → LLM gera resposta narrativa
  19. email_delivery        → (opcional) envia fechamento por e-mail
  ```

  **Templates executados no fechamento gerencial:**
  | Template | Dimensão principal | Métrica chave |
  |---|---|---|
  | `fechamento_faturamento_comissao_concessionaria_periodo` | concessionaria | total_comissao |
  | `fechamento_faturamento_comissao_tipo_os_concessionaria_periodo` | concessionaria | comissao_venda_normal |
  | `fechamento_producao_servico` | servico | total |
  | `fechamento_producao_produto` | produto | total |
  | `fechamento_faturamento_tipo_pagamento` | caixa_tipo | total_liquido |
  | `fechamento_faturamento_tipo_venda` | os_tipo | total |
  | `fechamento_faturamento_tipo_venda_produtos` | os_tipo (id=11) | total |
  | `fechamento_parcelamento_cartao` | parcelas | total |
  | `fechamento_taxas_cartao_credito` | empresa_nome | valor_taxa |

- **Tags:** `[Arquitetura, Pipeline, fechamento_gerencial, referência, analytics_pipeline]`

---

# KB-007: Confidence Score do `cognitive_plan` Não Evolui com Contexto de Memória

- **Contexto:** `src/orion_mcp_v3/runtime/intent_resolver.py` — campo `confidence` do `CognitivePlan`.
- **Sintoma/Erro:** O campo `confidence` permanece em `0.57` em todas as iterações, mesmo quando `memory_block_count: 1` indica que há contexto histórico injetado. `metrics: []` e `entities: []` também ficam vazios em pedidos de coleção.
- **Causa Raiz:** O `intent_resolver.py` calcula a confiança baseado nos sinais heurísticos da utterance (`heuristic_signal_catalog.py`) mas não incorpora o boost de confiança que deveria vir da memória recuperada. A memória é injetada no contexto do prompt, mas não retroalimenta o contrato cognitivo.
- **Solução Técnica:**
  Em `intent_resolver.py`, recalcular confidence após recuperação de memória:
  ```python
  def resolve_with_memory(self, utterance: str, memory_blocks: list) -> CognitivePlan:
      plan = self.resolve(utterance)
      if memory_blocks and plan.confidence < 0.8:
          # boost de confiança por contexto histórico confirmado
          memory_boost = min(0.15, len(memory_blocks) * 0.05)
          plan = replace(plan, confidence=min(1.0, plan.confidence + memory_boost))
      return plan
  ```
  Alternativamente, separar `intent_confidence` de `data_coverage_confidence` no contrato `CognitivePlan` para clareza semântica.
- **Tags:** `[Bug, intent_resolver, CognitivePlan, confidence, memory, contexto]`

---

# KB-008: Cache Redis para Fechamentos de Meses Encerrados

- **Contexto:** `src/orion_mcp_v3/broker/` — performance de fechamentos repetidos para meses já encerrados.
- **Sintoma/Erro:** Cada request de fechamento gerencial para um mês encerrado executa as 9 queries SQL + 3 chamadas LLM novamente, mesmo que os dados não possam ter mudado.
- **Causa Raiz:** Ausência de camada de cache para resultados determinísticos.
- **Solução Técnica:**
  Implementar cache em Redis com TTL diferenciado (infra disponível em `connection_hub/redis_backend.py`):
  ```python
  # broker/collection_router.py
  from datetime import date

  CACHE_KEY_TPL = "orion:collection:{slug}:{bu_id}:{date_from}:{date_to}"
  TTL_CLOSED_MONTH = 86400   # 24h para meses encerrados (imutáveis)
  TTL_CURRENT_MONTH = 300    # 5min para mês corrente

  async def dispatch_with_cache(self, slug, params, redis) -> CollectionResult:
      is_closed = date.fromisoformat(params["date_to"]) < date.today().replace(day=1)
      ttl = TTL_CLOSED_MONTH if is_closed else TTL_CURRENT_MONTH
      
      key = CACHE_KEY_TPL.format(slug=slug, bu_id=params["business_unit_id"],
                                  date_from=params["date_from"],
                                  date_to=params["date_to"])
      cached = await redis.get(key)
      if cached:
          return CollectionResult.from_json(cached)
      
      result = await self.dispatch(slug, params)
      await redis.setex(key, ttl, result.to_json())
      return result
  ```
  **Ganho esperado:** Eliminação de ~450ms de SQL + 1 chamada LLM por request de mês encerrado.
- **Tags:** `[Performance, Redis, Cache, fechamento_gerencial, meses_encerrados, TTL]`

---

# KB-009: Duplicação de Arquivos entre `api/` e `api/email/`

- **Contexto:** `src/orion_mcp_v3/api/` — organização do subpacote de e-mail.
- **Sintoma/Erro:** Dois pares de arquivos coexistem com funções sobrepostas:
  - `api/email_html_renderer.py` ↔ `api/email/html_renderer.py`
  - `api/email_sender.py` ↔ `api/email/sender.py`
  Não é claro qual versão é canônica. Imports divergentes em `main.py` e `routes/chat.py` podem usar versões diferentes sem ser detectado.
- **Causa Raiz:** Refatoração incompleta — os arquivos originais na raiz de `api/` não foram removidos quando o subpacote `api/email/` foi criado.
- **Solução Técnica:**
  ```bash
  # Verificar qual versão é usada em produção
  grep -r "email_html_renderer\|email_sender" src/orion_mcp_v3/api/main.py
  grep -r "email_html_renderer\|email_sender" src/orion_mcp_v3/api/routes/chat.py
  
  # Remover os arquivos da raiz (após confirmar que api/email/* é canônico)
  git rm src/orion_mcp_v3/api/email_html_renderer.py
  git rm src/orion_mcp_v3/api/email_sender.py
  
  # Atualizar imports para usar api.email.*
  ```
- **Tags:** `[Refatoração, Limpeza, api, email, duplicação, manutenibilidade]`

---

# KB-010: Trace do Pipeline sem Timestamps — Impossível Medir Latência por Etapa

- **Contexto:** `src/orion_mcp_v3/runtime/analytics_pipeline_trace.py` — sistema de logging estruturado do pipeline.
- **Sintoma/Erro:** O JSONL de trace contém `etapa`, `fase` e `dados`, mas **não inclui timestamp**. Isso torna impossível calcular quanto tempo cada etapa levou, identificar qual das 9 queries SQL é a mais lenta, ou construir dashboards de SLA.
- **Causa Raiz:** Campo `timestamp` não foi incluído no schema inicial do trace.
- **Solução Técnica:**
  ```python
  # runtime/analytics_pipeline_trace.py
  import time

  def _write_event(self, etapa: str, fase: str, dados: dict) -> None:
      event = {
          "canal": "analytics_pipeline",
          "etapa": etapa,
          "fase": fase,
          "timestamp_ms": int(time.time() * 1000),  # ← adicionar
          "conversation_id": self.conversation_id,
          "dados": dados,
      }
      self._sink.write(json.dumps(event, ensure_ascii=False) + "\n")
  ```
  Com isso, a latência de cada etapa pode ser calculada como:
  ```python
  latency_ms = post_event["timestamp_ms"] - pre_event["timestamp_ms"]
  ```
  Considerar também adicionar `elapsed_since_start_ms` para latência acumulada do pipeline.
- **Tags:** `[Observabilidade, Trace, analytics_pipeline_trace, Timestamps, SLA, Performance]`

---

# KB-011: Dados de Formas de Pagamento — Domínio do Faturamento (Janeiro–Abril 2026)

- **Contexto:** Consulta analítica sobre forma de pagamento dominante no período jan–abr/2026, respondida pelo pipeline Orion MCP v3.
- **Sintoma/Erro:** Pergunta recorrente de gestores: *"Qual forma de pagamento domina o faturamento?"*
- **Causa Raiz:** N/A — entrada de conhecimento de domínio.
- **Solução Técnica:** O template correto para esta análise é `fechamento_faturamento_tipo_pagamento` com `selected_metric: total_liquido` e `selected_dimension: caixa_tipo`. O pipeline retorna 8 tipos de pagamento ordenados por volume líquido.
  
  **Padrão histórico observado no faturamento da rede:**
  - **Cartão de Crédito** lidera consistentemente (~58–62% do total líquido)
  - **Concessionária** (repasse direto) é segundo (~16–21%)
  - **PIX** cresce — terceiro lugar (~9–14%)
  - **Depósito Bancário** quarto (~4–9%)
  - Parcelamento, Dinheiro e Permuta respondem pelo restante (<5% combinados)
  - Cheque: zerado em todos os períodos analisados

  O cartão de crédito com parcelamento em **10x** domina o volume parcelado (60–66% do total parcelado por valor).

- **Tags:** `[Domínio, Pagamento, Cartão, PIX, Faturamento, fechamento_gerencial, formas_pagamento]`

---

# KB-012: Fechamento Gerencial — Padrão de Dados por Mês (Referência de Benchmarks)

- **Contexto:** Dados reais extraídos do pipeline Orion MCP v3 para agosto/2025, setembro/2025 e maio/2026 da rede de concessionárias.
- **Sintoma/Erro:** N/A — entrada de benchmarks de domínio.
- **Causa Raiz:** N/A
- **Solução Técnica:** Benchmarks de referência para alertas e análises de anomalia:

  | Métrica | Ago/2025 | Set/2025 | Mai/2026 |
  |---|---|---|---|
  | Faturamento líquido total | R$ 2.718.654,99 | R$ 2.829.116,83 | ~R$ 2.694.796,56* |
  | Cartão de Crédito (%) | 58,11% | 62,05% | ~47,3%* |
  | Venda Normal (%) | 78,88% | 83,37% | ~63%* |
  | Parcelamento 10x (%) | 60,65% | 66,55% | ~56,7%* |
  | Concessionária líder | OSAKA | OSAKA | GWM BAMAQ |
  | Serviço líder | CLEAR COMFORT PARABRISA | PPF REGENERATIVO FULL | PPF REGENERATIVO FULL |
  | Produto líder (mat.) | — (sem dados) | PAINT PROTECTION 15M EUA | PAINT PROTECTION 15M EUA |

  *Valores de Mai/2026 parcialmente calculados a partir do log do embedding pipeline (cobertura 0,65).

- **Tags:** `[Domínio, Benchmarks, fechamento_gerencial, Sazonalidade, KPI, concessionaria]`
