# Relatório Técnico — Orion MCP v3
## Análise de Log de Pipeline e Estrutura do Projeto
**Gerado em:** 2026-06-07  
**Log analisado:** `analytics_pipeline_20260605T210004Z.jsonl` (95 eventos, 3 conversações)  
**Projeto:** `orion_mcp_v3` — Plataforma analítica cognitiva para rede de concessionárias

---

## 1. Diagnóstico de Problemas (Bugs, Gargalos e Erros)

### 1.1 `intent_interpret` rejeita "fechamento gerencial" com `unsupported_operation` (CRÍTICO)

**Log (linhas 3 e 50):**
```json
{ "etapa": "intent_interpret", "fase": "post",
  "dados": { "accepted": false, "rejected_reason": "unsupported_operation",
             "operation": null, "metric": null, "dimension": null }}
```

**Ocorrência:** Em **todas as 3 conversações** que contêm pedido de fechamento gerencial, o `intent_interpret` rejeita o parse direto. O pipeline **não falha** porque o `query_select` (downstream) absorve o pedido via LLM e escala para `collection_slug: fechamento_gerencial_por_mes` — mas são **2 chamadas LLM feitas onde 1 bastaria**.

**Arquivo responsável:** `src/orion_mcp_v3/runtime/analytical_intent_interpreter.py`  
**Causa raiz:** O interpreter tenta mapear a utterance a uma tupla `(operation, metric, dimension)` isolada. Expressões compostas como *"fechamento gerencial"* não têm binding direto nesse modelo de extração; o regex catalog (`heuristic_signal_catalog.py`) não cobre o padrão, então cai em `unsupported_operation`.

**Correção aplicada:** `AnalyticalIntentContract` passou a suportar `operation="collection"` e `collection_slug`. O `analytical_intent_interpreter.py` reconhece coleções registradas antes da chamada LLM, e o `analytical_intent_validator.py` valida `collection_slug` contra `QueryCapabilityCatalog.collection_card()`, removendo a rejeição `unsupported_operation` para `fechamento_gerencial_por_mes`.

---

### 1.2 `answer_present` rejeita com `unsupported_template` em coleções (MÉDIO)

**Log (linhas 7 e 54):**
```json
{ "etapa": "answer_present", "fase": "post",
  "dados": { "accepted": false, "rejected_reason": "unsupported_template" }}
```

**Ocorrência:** Novamente em **todas as conversações de fechamento**. O estágio `answer_present` tenta aplicar lógica de template individual a uma seleção do tipo `collection`, que não possui `template_slug`. A etapa descarta o resultado e o pipeline prossegue sem o `answer_present`.

**Arquivo responsável:** `src/orion_mcp_v3/runtime/answer_presentation_interpreter.py`  
**Causa raiz:** O interpretador de apresentação não tem branch para `selection_kind == "collection"`, somente para `selection_kind == "template"`.

**Correção aplicada:** `answer_presentation_interpreter.py` agora retorna apresentação padrão para `selection_kind == "collection"` sem chamar LLM, e `AnswerPresentationValidator` valida a coleção pelo catálogo em vez de buscar `entry_for_template(None)`.

---

### 1.3 `analytics_execute[3]` — `fechamento_producao_produto` retorna 0 linhas em agosto/2025 (BAIXO-MÉDIO)

**Log (linha 29):**
```json
{ "etapa": "analytics_execute[3]", "fase": "post",
  "dados": { "template_slug": "fechamento_producao_produto",
             "row_count": 0, "first_row_keys": [], "first_row_sample": {} }}
```

**Ocorrência:** Na conversação `1af10bdb` (agosto/2025), o template `fechamento_producao_produto` retorna conjunto vazio — sem tratamento explícito de fallback nem sinalização no `analytics_merge`. O merge simplesmente omite a seção do fechamento sem alertar o usuário.

**Arquivo responsável:** `src/orion_mcp_v3/broker/evidence_aggregator.py` e `analytics_merge` dentro de `data_pipeline.py`  
**Causa raiz:** Agosto/2025 pode não ter OS do tipo 11 (venda de materiais/produtos) no banco. O problema real é a ausência de uma flag explícita de "seção ausente" no evidence summary e na resposta narrativa.

---

### 1.4 `analytics_execute[6]` — `fechamento_faturamento_tipo_venda_produtos` retorna 0 linhas em agosto/2025 (BAIXO-MÉDIO)

**Log (linha 32):**
```json
{ "etapa": "analytics_execute[6]", "fase": "post",
  "dados": { "template_slug": "fechamento_faturamento_tipo_venda_produtos",
             "row_count": 0, "first_row_keys": [], "first_row_sample": {} }}
```

Mesmo padrão do item 1.3. Correlacionado: ambos templates dependem de `os_tipo_id = 11` que estava ausente em agosto/2025.

---

### 1.5 `fechamento_parcelamento_cartao` — `first_row_sample` com total `"0.00"` em datas fora do período (MÉDIO)

**Log (linha 33):**
```json
{ "first_row_sample": { "periodo": "2025-03", "parcelas": "1X",
                         "quant_parcelas": 1, "quantidade": 1, "total": "0.00" }}
```

**Causa raiz:** A SQL do `fechamento_parcelamento_cartao` usa `DATE_FORMAT(cx.data_pagamento, ...)` no GROUP BY mas a cláusula WHERE filtra `os.data_pagamento`. Caixas onde o `cx.data_pagamento` difere do `os.data_pagamento` podem ser incluídas com totais zerados ou de períodos errados (linha com `periodo: 2025-03` aparece num fechamento de agosto/2025).

**Arquivo responsável:** `src/orion_mcp_v3/broker/queries/fechamento_parcelamento_cartao.py` e o `.sql` correspondente em `docs/queries/fechamento_gerencial_por_mes/ParcelamentoCartao.sql`

---

### 1.6 `confidence` do `cognitive_plan` fixo em 0.57 em todas as iterações (MÉDIO)

**Log (linhas 9, 56):**
```json
{ "cognitive_plan": { "confidence": 0.57, "metrics": [], "entities": [] }}
```

O plano cognitivo nunca tem `metrics` nem `entities` preenchidos para pedidos de fechamento. A confiança não evolui entre a primeira e segunda chamada na mesma sessão, mesmo com contexto de memória injetado (`memory_block_count: 1`).

**Arquivo responsável:** `src/orion_mcp_v3/runtime/intent_resolver.py`

---

### 1.7 `context_isolation` não está dropando blocos entre sessões distintas (OBSERVAÇÃO)

**Log (linhas 40 e 87):**
```json
{ "etapa": "context_isolation",
  "dados": { "dropped_vector": 0, "dropped_analytical_memory": 0,
             "reason": "analytical_continuity" }}
```

As conversações `1af10bdb` e `affd42dd` são IDs distintos (conversas separadas), mas o `context_isolation` mantém o bloco de memória em ambas sem drop. Correto enquanto as perguntas são analíticas do mesmo domínio, mas pode vazar contexto se a próxima query for de domínio diferente.

**Arquivo responsável:** `src/orion_mcp_v3/runtime/analytical_context_policy.py`

---

## 2. Otimização e Redução de Tempo de Execução (Performance)

### 2.1 9 Queries SQL do fechamento precisam de paralelismo mensurável (CRÍTICO)

O pipeline expande 9 templates do `fechamento_gerencial_por_mes`:

```
analytics_execute[0] → [1] → [2] → [3] → ... → [8]
```

Cada execute lança um `pre` antes do `post` — mas a ordem sequencial dos `post` no JSONL antigo era **inconclusiva**, porque o pipeline registra os resultados depois do `asyncio.gather`, em ordem de índice. Sem timestamps e duração por execução, o log não permitia distinguir execução serial de execução paralela finalizada e serializada para logging.

**Estimativa de impacto:** Com ~1.185 chars de SQL cada, e assumindo 50ms por query em MySQL, 9 queries sequenciais = ~450ms vs ~100ms em paralelo.

**Arquivo responsável:** `src/orion_mcp_v3/api/routes/chat.py` (`_run_analytics`). O `AnalyticsExecutor` executa um plano/template individual.

**Correção aplicada:** foram adicionados testes de regressão que provam fanout concorrente (`max_active > 1`) para `fechamento_gerencial_por_mes` e preservação dos resultados válidos quando uma query falha. O trace agora possui `timestamp_utc`, `timestamp_ms` e `duration_ms` por `analytics_execute[N] post`, inclusive em erro.

---

### 2.2 Dupla chamada LLM por request de fechamento (CRÍTICO)

Por causa do bug 1.1 (`intent_interpret` rejeita → `query_select` usa LLM), cada request de fechamento consome **2 chamadas LLM** quando poderia consumir 1:

| Etapa | LLM chamado? |
|---|---|
| `intent_interpret` | ✅ (rejeita mas consome tokens) |
| `query_select` | ✅ (necessário e correto) |
| `answer_present` | ✅ (rejeita mas consome tokens) |

Total: 3 chamadas LLM onde 1 seria suficiente para pedidos de coleção reconhecida.

---

### 2.3 `analytics_merge` consome todos os dados antes de checar `answer_project` (MÉDIO)

**Log (linhas 36 e 83):**
```json
{ "etapa": "answer_project", "fase": "post", "dados": { "presente": false }}
```

O `answer_project` retorna `presente: false` **depois** que o merge já processou 175 linhas. A sequência correta seria checar se há um projector registrado **antes** do merge completo, economizando processamento desnecessário quando o projector não existe.

---

### 2.4 `cognitive_orchestrate` empacota 5 blocos mas 2 são `fusion_kind: none` (BAIXO)

**Log (linhas 43 e 90):**
```json
{ "packed_block_count": 5,
  "fusion_kind_counts": { "reasoning_result": 1, "system_prompt": 1,
                          "none": 2, "evidence": 1 }}
```

2 dos 5 blocos têm `fusion_kind: none`, o que significa que ocupam espaço no prompt sem rótulo semântico, possivelmente aumentando o tamanho do prompt sem valor estrutural claro.

---

### 2.5 `summary_chars` cresce linearmente com o número de concessionárias (MÉDIO)

| Conversação | `row_count` | `summary_chars` |
|---|---|---|
| agosto/2025 | 175 | 3.403 |
| setembro/2025 | 174 | 3.771 |

O summary serializa todas as linhas de todas as seções em texto plano. Com 50–60 concessionárias e crescimento da rede, esse bloco pode atingir o limite do context window.

---

## 3. Sugestões de Solução e Plano de Ação

### Fix 3.1 — Adicionar reconhecimento de `collection` no `intent_interpreter`

Em `analytical_intent_interpreter.py`, adicionar detecção precoce de padrões de coleção antes de tentar o parse granular:

```python
# analytical_intent_interpreter.py

COLLECTION_PATTERNS = {
    r"fechamento\s+gerencial": "fechamento_gerencial_por_mes",
    r"relatório\s+mensal\s+completo": "fechamento_gerencial_por_mes",
}

def interpret(self, utterance: str, ...) -> InterpretResult:
    # Fast-path: detecta coleção antes do LLM
    for pattern, collection_slug in COLLECTION_PATTERNS.items():
        if re.search(pattern, utterance, re.IGNORECASE):
            return InterpretResult(
                accepted=True,
                operation="collection",
                collection_slug=collection_slug,
                metric=None,
                dimension=None,
            )
    # fallback ao LLM existente
    return self._llm_interpret(utterance, ...)
```

**Ganho:** Elimina 1 chamada LLM desnecessária por request de fechamento.

---

### Fix 3.2 — Branch `collection` no `answer_presentation_interpreter`

Em `answer_presentation_interpreter.py`:

```python
def interpret(self, selection: QuerySelection, ...) -> PresentationResult:
    if selection.selection_kind == "collection":
        # Coleções não têm template individual — usar apresentação padrão
        return PresentationResult(
            accepted=True,
            result_scope=ResultScope(mode="all", limit=None),
            sort=SortSpec(field="", direction="desc"),
            confidence=selection.confidence,
            reason="collection_default_presentation",
        )
    # lógica de template existente...
```

**Ganho:** Elimina a rejeição `unsupported_template` e o custo de uma chamada LLM rejeitada.

---

### Fix 3.3 — Paralelizar `analytics_execute` no fanout de coleção

No código atual, o fanout da coleção fica em `_run_analytics` dentro de `api/routes/chat.py`, não em `executor.py`. Garantir que esse ponto continue usando `asyncio.gather` e medir cada execução:

```python
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
    # tratar exceções individuais sem abortar a coleção inteira,
    # registrando duration_ms em cada analytics_execute[N].post
    return [r for r, _duration_ms in results if not isinstance(r, Exception)]
```

**Ganho estimado:** Redução de ~450ms → ~100ms por fechamento (9 queries paralelas vs. sequenciais).

---

### Fix 3.4 — Correção do `fechamento_parcelamento_cartao` — alinhamento de datas

No SQL do `ParcelamentoCartao.sql`, alinhar o `GROUP BY` e o `WHERE` para usar `os.data_pagamento` consistentemente:

```sql
-- ANTES (problemático): agrupa por cx.data_pagamento
GROUP BY cx.quant_parcelas, DATE_FORMAT(cx.data_pagamento, '%%Y-%%m')

-- DEPOIS (correto): agrupa por os.data_pagamento
GROUP BY cx.quant_parcelas, DATE_FORMAT(os.data_pagamento, '%%Y-%%m')
```

E no SELECT, substituir `DATE_FORMAT(cx.data_pagamento, ...)` por `DATE_FORMAT(os.data_pagamento, ...)` para que o campo `periodo` reflita a data da OS, não do lançamento de caixa.

---

### Fix 3.5 — Sinalizar seções ausentes no evidence summary

Em `evidence_aggregator.py` ou `analytics_merge`, emitir uma flag explícita quando um template retorna 0 linhas:

```python
def merge_results(self, results: list[TemplateResult]) -> MergedEvidence:
    summary_sections = []
    missing_sections = []
    
    for result in results:
        if result.row_count == 0:
            missing_sections.append(result.template_slug)
            # não omite silenciosamente — adiciona nota ao summary
            summary_sections.append(
                f"## {result.label}\n_Sem dados para o período informado._\n"
            )
        else:
            summary_sections.append(self._format_section(result))
    
    return MergedEvidence(
        summary="\n".join(summary_sections),
        missing_sections=missing_sections,
        ...
    )
```

---

### Fix 3.6 — Checar `answer_project` antes do `analytics_merge` completo

Reordenar o pipeline em `data_pipeline.py`:

```python
# ANTES
results = execute_all_templates(plans)
merged = analytics_merge(results)
projected = answer_project(merged)  # presente: false → processamento desperdiçado

# DEPOIS
projector = answer_project.resolve(selection)
if projector:
    results = execute_all_templates(plans)
    merged = analytics_merge(results)
    output = projector.apply(merged)
else:
    results = execute_all_templates(plans)
    output = analytics_merge(results)
```

---

## 4. Melhorias Arquiteturais e Boas Práticas

### 4.1 Introduzir um `CollectionRouter` dedicado

Atualmente o pipeline trata "coleção" como um caso especial espalhado em vários estágios (`query_select`, `answer_present`, `analytics_expand`). Proposta: criar um módulo `CollectionRouter` que centraliza a detecção e despacho:

```
src/orion_mcp_v3/broker/collection_router.py
```

```python
class CollectionRouter:
    """Detecta e despacha requests de coleção sem passar pelo pipeline de template."""
    
    def matches(self, selection: QuerySelection) -> bool:
        return selection.selection_kind == "collection"
    
    def dispatch(self, selection, params) -> CollectionResult:
        collection = self.catalog.get(selection.collection_slug)
        return collection.execute_parallel(params)
```

Isso elimina os bugs 1.1 e 1.2 de forma estrutural.

---

### 4.2 Separar `confidence` do `cognitive_plan` em duas dimensões

O campo `confidence: 0.57` fixo sugere que o sistema não diferencia confiança de **parse** (entendeu o que o usuário pediu?) de confiança de **dados** (os dados são completos?). Proposta de split no contrato:

```python
# contracts/cognitive_plan.py
@dataclass
class CognitivePlan:
    intent_confidence: float      # confiança no parse da intenção
    data_coverage_confidence: float  # confiança na cobertura dos dados
    ...
```

---

### 4.3 Implementar cache de resultado de coleção com TTL Redis

Fechamentos gerenciais para meses encerrados são determinísticos. Implementar cache em Redis:

```python
# broker/collection_router.py
CACHE_KEY = "collection:{slug}:{date_from}:{date_to}:{bu_id}"
TTL_CLOSED_MONTH = 3600 * 24  # 24h para meses encerrados
TTL_CURRENT_MONTH = 300       # 5min para mês corrente

async def dispatch_with_cache(self, selection, params) -> CollectionResult:
    is_closed = params["date_to"] < today_first_day()
    ttl = TTL_CLOSED_MONTH if is_closed else TTL_CURRENT_MONTH
    
    cached = await self.redis.get(cache_key)
    if cached:
        return CollectionResult.from_cache(cached)
    
    result = await self.dispatch(selection, params)
    await self.redis.setex(cache_key, ttl, result.to_cache())
    return result
```

**Ganho:** Eliminação das 9 queries SQL + 3 chamadas LLM para fechamentos de meses já encerrados.

---

### 4.4 Adicionar `operation: "collection"` ao catálogo de operações do `intent_interpreter`

Em `config/allowlists.py`, adicionar `"collection"` às operações permitidas para que o `intent_interpret` possa aceitar diretamente esse tipo:

```python
ALLOWED_OPERATIONS = {
    "ranking_desc", "ranking_asc", "top_and_bottom", 
    "list", "timeseries", "collection",  # ← adicionar
}
```

---

### 4.5 Padronizar nomenclatura de migração — conflito de prefixo `003`

**Estrutura observada:**
```
infra/postgres/migrations/
  003_conversation_external_id.sql
  003_memory_embeddings.sql   ← mesmo prefixo!
```

Dois arquivos com prefixo `003` causam ambiguidade na ordem de aplicação. Renomear:
```
003_conversation_external_id.sql → 003_conversation_external_id.sql
003_memory_embeddings.sql        → 003b_memory_embeddings.sql  (ou 004_)
```
E ajustar `scripts/apply_migrations.py` para ordenar por nome com suporte a sufixo `a`/`b`.

---

### 4.6 Mover `email_html_renderer.py` e `email_sender.py` da raiz de `api/` para `api/email/`

**Estrutura atual:**
```
api/
  email_html_renderer.py   ← raiz de api/
  email_sender.py          ← raiz de api/
  email/
    html_renderer.py       ← duplicata mais organizada
    sender.py
```

Há duplicação entre `api/email_html_renderer.py` e `api/email/html_renderer.py`. Remover os arquivos da raiz e usar apenas o subpacote `api/email/`, atualizando imports em `main.py` e `routes/chat.py`.

---

### 4.7 Adicionar métricas de latência por etapa no `analytics_pipeline_trace.py`

O log registra `pre` e `post` de cada etapa. Adicionar `timestamp_utc`, `timestamp_ms` e `duration_ms` nos eventos de execução analítica permite calcular a latência de cada estágio e identificar o template mais lento:

```python
# runtime/analytics_pipeline_trace.py
import time

def log_event(self, etapa: str, fase: str, dados: dict):
    now = datetime.now(timezone.utc)
    self._sink.write({
        "canal": "analytics_pipeline",
        "etapa": etapa,
        "fase": fase,
        "timestamp_utc": now.isoformat(),
        "timestamp_ms": int(time.time() * 1000),
        "conversation_id": self.conversation_id,
        "dados": dados,
    })
```

**Correção aplicada:** todo evento do trace inclui `timestamp_utc` e `timestamp_ms`; eventos `analytics_execute[N] post` incluem `duration_ms` em sucesso e erro.

---

## Resumo Executivo de Prioridades

| # | Problema | Severidade | Esforço | Ação |
|---|---|---|---|---|
| 1 | Dupla rejeição LLM (intent + answer_present) para coleções | 🔴 Alto | Baixo | Fix 3.1 + 3.2 |
| 2 | 9 queries SQL sequenciais no fechamento | 🔴 Alto | Médio | Fix 3.3 |
| 3 | Período errado em `fechamento_parcelamento_cartao` | 🟡 Médio | Baixo | Fix 3.4 |
| 4 | Seções com 0 linhas omitidas silenciosamente | 🟡 Médio | Baixo | Fix 3.5 |
| 5 | `answer_project` checado após merge completo | 🟡 Médio | Baixo | Fix 3.6 |
| 6 | Cache Redis para fechamentos de meses encerrados | 🟢 Melhoria | Médio | Item 4.3 |
| 7 | Conflito de prefixo `003` nas migrações | 🟡 Médio | Trivial | Item 4.5 |
| 8 | Timestamps ausentes no trace | 🟢 Melhoria | Trivial | Item 4.7 |
