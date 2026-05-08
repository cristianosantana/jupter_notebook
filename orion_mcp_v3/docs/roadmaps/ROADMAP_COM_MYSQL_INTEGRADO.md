# 🚀 ROADMAP EXECUTÁVEL - OrionMCP V3 Com MySQL

**Status**: Fases 0-1 completas, integrando acesso MySQL  
**Alinhamento**: Respostas devem ser baseadas em dados do MySQL  
**Connection Hub**: Já implementado (asyncmy, MySQL async)

---

## Novo princípio arquitetural

O pipeline analítico **deixa de entregar apenas dados brutos** (`raw SQL rows`) e passa a entregar **evidências cognitivas compactadas**: cada camada reduz cardinalidade e aumenta densidade informativa até algo consumível pelo runtime LLM com **provenance** e **coverage** explícitos.

Objetivo cognitivo:

```text
query engine  →  evidence extraction engine
```

---

## 📋 VISÃO GERAL

O OrionMCP V3 precisa responder **perguntas sobre dados no MySQL**.

```
User Query → Decision Engine → Planner (SemanticQueryPlan / intenção analítica)
          → SQL Compiler (safe)
          → MySQL Executor
          → Analytical Reduction Layer (aggregators → samplers → reducers)
          → EvidenceBuilder → AnalyticalDigest (evidence-oriented)
          → Context Fusion (analytics + memory → ContextBlocks)
          → BudgetAllocator
          → LLM Narrator
```

---

# ✅ FASES COMPLETADAS

## FASE 0 — FUNDAÇÃO SEMÂNTICA ✅

- ✅ ContextBlock, ContextRole, ContextSource
- ✅ ProvenanceAnchor, CoverageInfo
- ✅ RuntimeEventType, RuntimeEvent
- ✅ SemanticQueryPlan, RetrievalStrategy

## FASE 1 — RUNTIME MÍNIMO ✅

- ✅ ContextState
- ✅ AttentionPolicy (CONVERSATIONAL, ANALYTICAL, PLANNING)
- ✅ BudgetAllocator MVP (reserve essencial, corta excesso)
- ✅ Testes validados

## FASE 2 — MEMÓRIA CONVERSACIONAL ✅

- ✅ Repository literal (conversation_state PostgreSQL)
- ✅ MemoryComposer MVP
- ✅ Redis cache para summaries

## FASE 3 — BROKER ANALÍTICO (PARCIAL) ✅

- ✅ Planner MVP (heurísticas PT/EN para agregação)
- ✅ SQL Compiler MVP (SELECT only, allowlist, safe)
- ✅ Aggregators (group_by, time_series, top_n)
- ✅ Samplers (recent_sampler, outlier_sampler)
- ✅ AnalyticalDigest (summary, volume, sample, coverage)

---

# 🔴 FASES A IMPLEMENTAR

---

# 🚀 FASE 0.5 — CONNECTION HUB (PRÉ-REQUISITO)

## Objetivo

Preparar acesso seguro ao MySQL com pools de conexão.

## Status

✅ **JÁ IMPLEMENTADO**

### O Que Existe

```
src/orion_mcp_v3/connection_hub/
├── abstract.py          # AbstractDatastoreClient (interface)
├── mysql_backend.py     # MysqlDatastoreClient (asyncmy)
├── postgres_backend.py  # PostgresDatastoreClient
├── redis_backend.py     # RedisDatastoreClient
├── pools.py             # Pool creation
└── README.md
```

### MysqlDatastoreClient (Implementado)

```python
class MysqlDatastoreClient:
    async def select(query, params) → List[Dict]
    async def insert(query, params) → int
    async def update(query, params) → int
    async def delete(query, params) → int
    async def close()
```

### Como Usar

```python
from orion_mcp_v3.connection_hub import MysqlDatastoreClient

client = MysqlDatastoreClient(mysql_pool)

# SELECT
rows = await client.select(
    "SELECT * FROM vendas WHERE date > %s LIMIT 100",
    params=["2025-01-01"]
)

# INSERT
affected = await client.insert(
    "INSERT INTO logs (msg) VALUES (%s)",
    params=["query executed"]
)
```

### ✅ Não precisa fazer mais nada aqui

---

# 🚀 FASE 1.5 — ANALYTICS EXECUTOR (NOVO)

## Objetivo

Orquestrador que une **Planner + SQL Compiler + MySQL Executor**.

Responsabilidade única: executar um plano analítico contra MySQL.

---

## 📦 Tarefa 1.5.1 — AnalyticsExecutor

### Arquivo

```
src/orion_mcp_v3/broker/executor.py
```

### Implementar

```python
class AnalyticsExecutor:
    """
    Orquestra: Query Text → Planner → SQL Compiler → MySQL Execute
    """
    
    def __init__(
        self,
        mysql_client: MysqlDatastoreClient,
        allowlist: SqlAllowlist,
        default_limit: int = 1000
    ):
        self.mysql_client = mysql_client
        self.allowlist = allowlist
        self.default_limit = default_limit
    
    async def execute(
        self,
        query_text: str,
        intent_slug: str = "analytics.generic",
        correlation_id: str | None = None
    ) -> AnalyticsResult:
        """
        1. parse query_text → plan (Planner)
        2. compile plan → SQL (SQL Compiler)
        3. execute SQL → rows (MySQL)
        4. return result
        """
        # Step 1: Planner
        plan = plan_from_natural_language(
            query_text,
            intent_slug=intent_slug,
            correlation_id=correlation_id
        )
        
        # Step 2: SQL Compiler
        compiled = compile_select(plan, self.allowlist)
        
        # Step 3: MySQL
        rows = await self.mysql_client.select(
            compiled.sql,
            params=compiled.params
        )
        
        # Step 4: Result
        return AnalyticsResult(
            plan=plan,
            sql=compiled.sql,
            rows=rows,
            row_count=len(rows)
        )
```

### Retorna

```python
@dataclass
class AnalyticsResult:
    plan: SemanticQueryPlan
    sql: str  # SQL executado
    rows: List[Dict[str, Any]]  # Resultados
    row_count: int
```

---

## 📦 Tarefa 1.5.2 — SqlAllowlist Configuração

### Arquivo

```
src/orion_mcp_v3/config/allowlists.py
```

### Implementar

Definir tabelas e colunas permitidas:

```python
ANALYTICS_ALLOWLIST = SqlAllowlist(
    tables=frozenset([
        "vendas",
        "clientes",
        "os",  # ordens_servico
        "servicos",
        "funcionarios",
        "concessionarias"
    ]),
    columns_by_table={
        "vendas": frozenset([
            "id", "os_id", "concessionaria_id", "vendedor_id",
            "servico_id", "valor", "data_venda", "status"
        ]),
        "os": frozenset([
            "id", "concessionaria_id", "vendedor_id",
            "status", "data_criacao", "reaberta"
        ]),
        "servicos": frozenset([
            "id", "nome", "categoria_id", "preco_custo",
            "descricao"
        ]),
        # ... mais tabelas
    }
)
```

---

## 📦 Tarefa 1.5.3 — Teste AnalyticsExecutor

### Arquivo

```
tests/test_analytics_executor.py
```

### Testar

```python
async def test_execute_simple_query():
    executor = AnalyticsExecutor(mysql_client, allowlist)
    
    result = await executor.execute(
        "últimos 3 meses faturamento",
        intent_slug="analytics.temporal"
    )
    
    assert result.row_count > 0
    assert "sql" in str(result.sql)
```

---

## Analytical Reduction Layer

**Problema cognitivo:** `raw SQL result != analytical evidence`. Linhas devolvidas pelo MySQL não são, por si só, evidência analítica — são material bruto que precisa de **redução**, **amostragem** e **interpretação estruturada** antes de alimentar o LLM.

Pipeline explícito (a implementar / consolidar no broker):

```text
SQL rows
  ↓
aggregators        → group by, séries temporais, ranking, comparações, normalização de métricas
  ↓
samplers           → linhas recentes, outliers, amostras representativas, estratificação, redução de cardinalidade
  ↓
reducers           → dados agregados → insights semânticos (crescimento, queda, tendência, sazonalidade, anomalia, mudança de comportamento)
  ↓
EvidenceBuilder    → reducers + samples → EvidenceBlock (+ digest agregado)
  ↓
AnalyticalDigest     → contexto analítico orientado a evidência (não apenas “resumo de linhas”)
```

### Estrutura alvo em `broker/`

```text
broker/
├── planner.py
├── sql_compiler.py
├── executor.py
├── aggregators.py
├── samplers.py
├── reducers.py
├── evidence_builder.py
├── policies.py
├── data_pipeline.py      # pode orquestrar ou delegar à camada acima
└── chunking.py           # existente
```

### `aggregators.py`

- Agrupamentos (`group_by`), agregação temporal, ranking, comparações, normalização de métricas.

### `samplers.py`

- Linhas recentes, amostragem de anomalias, amostras representativas, amostragem estratificada, redução de cardinalidade.

### `reducers.py`

- Transformar **dados agregados** em **insights semânticos** (crescimento, queda, tendência, sazonalidade, anomalia, mudança de comportamento).

### `evidence_builder.py`

- Combinar saídas de reducers + samples em **`EvidenceBlock`** (e feeds para **`AnalyticalDigest`**) com **confidence**, **provenance**, **coverage**, **summary**, **supporting_data**.

### Contrato sugerido: `EvidenceBlock` (contracts)

Campos orientativos:

- `summary`, `insights`, `metrics`
- `provenance`, `coverage`, `confidence`
- `sample_refs` (referências às amostras / chunks suporte)

### `AnalyticalDigest` — papel conceptual (alteração)

- **Antes (mentalidade simples):** digest = resumo final dos números.
- **Depois:** digest = **contexto analítico orientado a evidência** — agrega digestível o que reducers + builder declararam, sempre ancorado em provenance/coverage.

### Provenance Anchoring (digest / map-reduce analítico)

Cada insight deve poder explicar:

- **origem** (qual execução SQL / qual plano semântico),
- **chunks** ou subconjuntos de dados que o suportam,
- **coverage** (quanto dos dados entrou na conta),
- **aggregation logic** (que agregação ou reducer produziu o insight).

### BudgetAllocator e camada de evidência

Os **reducers** e o **EvidenceBuilder** devem, numa evolução próxima, calcular ou expor metadados utilizáveis pelo orçamento:

- **information_density**
- **cognitive_weight**
- **estimated_token_cost**

para integração futura com **BudgetAllocator** (competição por tokens entre blocos de analytics e de memória).

---

## Analytical Reasoning Pipeline

Fluxo lógico end-to-end:

```text
User Intent
    ↓
Planner (SemanticQueryPlan — intenção analítica estruturada; ver nota abaixo)
    ↓
SemanticQueryPlan
    ↓
SQL Execution
    ↓
Aggregation
    ↓
Sampling
    ↓
Reduction
    ↓
EvidenceBuilder
    ↓
AnalyticalDigest
```

### Planner: não devolve SQL

O **Planner** devolve **intenção analítica estruturada** (`SemanticQueryPlan` + hints), não texto SQL. O compilador + executor geram SQL a partir desse plano.

Exemplo ilustrativo de *forma* de intenção (ilustrativo; o contrato real é `SemanticQueryPlan` / hints):

```json
{
  "intent": "trend_analysis",
  "metric": "ticket_medio",
  "group_by": "month",
  "comparison": "previous_period"
}
```

---

## ✅ RESULTADO FASE 1.5

Você terá:

```text
Caminho funcional: pergunta → planer → compilador → mysql → resultado
```

---

# 🚀 FASE 2.5 — DATA PIPELINE (REVISADO)

## Objetivo

Melhorar pipeline para trabalhar com dados REAIS do MySQL e, em paralelo, **encaixar** a **Analytical Reduction Layer** (aggregators → samplers → reducers → `EvidenceBuilder` → `AnalyticalDigest`), evitando o salto perigoso **SQL → digest** sem agregação e redução explícitas.

---

## 📦 Tarefa 2.5.1 — Schema-Aware DataPipeline

### Arquivo

```
src/orion_mcp_v3/broker/data_pipeline.py
```

### Implementar

Atualizar para trabalhar com `AnalyticsResult`:

```python
class DataPipeline:
    """
    MySQL rows → ContextBlocks (schema, summary, sample)
    """
    
    async def process(
        self,
        result: AnalyticsResult
    ) -> dict[str, Any]:
        """
        1. infer_schema(rows) → coltype info
        2. build_summary(rows) → agregação por coluna
        3. extract_insights(rows) → anomalias, patterns
        4. build_sample(rows) → top, bottom, outliers
        """
        
        schema = self._infer_schema(result.rows)
        summary = self._build_summary(result.rows, schema)
        insights = self._extract_insights(result.rows, summary)
        sample = self._build_sample(result.rows)
        
        return {
            "query_text": result.plan.intent_slug,
            "sql": result.sql,
            "row_count": result.row_count,
            "schema": schema,
            "summary": summary,
            "insights": insights,
            "sample": sample,
            "coverage": CoverageInfo(
                total_rows=result.row_count,
                sample_rows=len(sample),
                schema_fields=len(schema)
            )
        }
    
    def _infer_schema(self, rows: List[Dict]) -> Dict[str, str]:
        """Detectar tipos de colunas"""
        if not rows:
            return {}
        
        schema = {}
        first = rows[0]
        for col, val in first.items():
            if isinstance(val, (int, float)):
                schema[col] = "numeric"
            elif isinstance(val, bool):
                schema[col] = "boolean"
            elif isinstance(val, str):
                schema[col] = "string"
            elif isinstance(val, datetime):
                schema[col] = "timestamp"
            else:
                schema[col] = "unknown"
        
        return schema
    
    def _build_summary(self, rows, schema) → Dict:
        """Agregações por coluna (não por linha)"""
        summary = {}
        for col, typ in schema.items():
            values = [r[col] for r in rows if col in r]
            
            if typ == "numeric":
                summary[col] = {
                    "media": statistics.mean(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values)
                }
            elif typ == "string":
                from collections import Counter
                counts = Counter(values)
                summary[col] = {
                    "unique": len(counts),
                    "top_5": counts.most_common(5)
                }
            elif typ == "timestamp":
                summary[col] = {
                    "earliest": min(values),
                    "latest": max(values)
                }
        
        return summary
    
    def _extract_insights(self, rows, summary) → List[str]:
        """Detectar padrões automáticos"""
        insights = []
        
        for col, stats in summary.items():
            if "max" in stats and "min" in stats:
                variance = stats["max"] - stats["min"]
                if variance > stats.get("media", 1) * 2:
                    insights.append(f"⚠️ {col}: alta variância ({variance})")
        
        return insights
    
    def _build_sample(self, rows) → List[Dict]:
        """Amostra: head + tail + outliers"""
        if len(rows) <= 5:
            return rows
        
        head = rows[:2]
        tail = rows[-2:]
        
        # Outlier por primeira coluna numérica
        numeric_cols = [k for k, v in rows[0].items() 
                       if isinstance(v, (int, float))]
        if numeric_cols:
            col = numeric_cols[0]
            outliers = sorted(rows, 
                            key=lambda r: r.get(col, 0), 
                            reverse=True)[0:1]
        else:
            outliers = []
        
        return head + tail + outliers
```

---

## 📦 Tarefa 2.5.2 — Testes DataPipeline Real

### Arquivo

```
tests/test_data_pipeline_real.py
```

### Testar

```python
async def test_pipeline_with_real_mysql_data():
    executor = AnalyticsExecutor(mysql_client, allowlist)
    result = await executor.execute("últimos 3 meses")
    
    pipeline = DataPipeline()
    output = await pipeline.process(result)
    
    assert output["row_count"] > 0
    assert "schema" in output
    assert "summary" in output
    assert len(output["sample"]) > 0
```

---

## ✅ RESULTADO FASE 2.5

Você terá:

```text
MySQL rows → Processados com schema inference
           → Summary automático
           → Insights detectados
           → Sample extraído
```

---

## Context Fusion Layer (analytics + memory)

**Estado:** especificado no roadmap; implementação pode ser incremental.

- Tanto **analytics** (digest / EvidenceBlocks) como **memory** conversacional devem convergir para **`ContextBlock`** formais.
- A **fusão** ocorre **antes** do **BudgetAllocator**: um único conjunto de blocos compete pelo orçamento de tokens.
- Evoluções futuras: **deduplicação** entre fontes, **resolução de conflitos** já previstas no runtime mínimo, priorização por relevância / densidade.

---

# 🚀 FASE 3.5 — CONTEXT BUILDER PARA DADOS REAIS

## Objetivo

Montar ContextBlocks a partir de dados MySQL + memory.

---

## 📦 Tarefa 3.5.1 — AnalyticalContextBuilder

### Arquivo

```
src/orion_mcp_v3/runtime/context_builder.py
```

### Implementar

```python
class AnalyticalContextBuilder:
    """
    Converte dados MySQL para ContextBlocks.
    Integra memory curta.
    """
    
    async def build(
        self,
        pipeline_output: dict,
        memory_curta: dict | None = None,
        user_id: str | None = None,
        token_budget: int = 4000
    ) -> List[ContextBlock]:
        """
        Monta blocos de contexto para enviar ao LLM.
        """
        
        blocks = []
        
        # 1. SYSTEM role: hints sobre análise
        system_block = ContextBlock(
            role=ContextRole.SYSTEM,
            source=ContextSource.BROKER,
            content=f"""
You are an analytics narrator.
Data schema: {pipeline_output['schema']}
Row count: {pipeline_output['row_count']}
Do NOT compute; summarize the provided data.
""",
            token_estimate=200
        )
        blocks.append(system_block)
        
        # 2. DATA role: resumo + amostra
        data_content = json.dumps({
            "summary": pipeline_output["summary"],
            "sample": pipeline_output["sample"],
            "insights": pipeline_output["insights"]
        })
        
        data_block = ContextBlock(
            role=ContextRole.DATA,
            source=ContextSource.BROKER,
            content=data_content,
            token_estimate=len(data_content) // 4
        )
        blocks.append(data_block)
        
        # 3. MEMORY role (se houver memory curta)
        if memory_curta:
            memory_content = json.dumps(memory_curta)
            memory_block = ContextBlock(
                role=ContextRole.CONTEXT,
                source=ContextSource.MEMORY,
                content=memory_content,
                token_estimate=len(memory_content) // 4
            )
            blocks.append(memory_block)
        
        # 4. Alocar budget
        allocator = BudgetAllocator()
        allocated = await allocator.allocate(blocks, token_budget)
        
        return allocated
```

---

## 📦 Tarefa 3.5.2 — Teste ContextBuilder

```python
async def test_context_builder_with_mysql_data():
    # Get data from MySQL
    executor = AnalyticsExecutor(mysql_client, allowlist)
    result = await executor.execute("últimos 3 meses")
    
    # Process
    pipeline = DataPipeline()
    pipeline_output = await pipeline.process(result)
    
    # Build context
    builder = AnalyticalContextBuilder()
    blocks = await builder.build(
        pipeline_output,
        memory_curta={"insights": ["Crescimento +12%"]},
        token_budget=4000
    )
    
    assert len(blocks) >= 2  # SYSTEM + DATA
    assert blocks[0].role == ContextRole.SYSTEM
    assert blocks[1].role == ContextRole.DATA
```

---

## ✅ RESULTADO FASE 3.5

Você terá:

```text
MySQL dados → Pipeline processado → ContextBlocks montados
           → Prontos para LLM
           → Com memory integrada
           → Dentro do budget
```

---

# 🚀 FASE 4 — ORCHESTRATION FINAL

## Objetivo

Integrar tudo num turno completo: pergunta → resposta.

---

## 📦 Tarefa 4.1 — OrchestrationFlowWithMySQL

### Arquivo

```
src/orion_mcp_v3/runtime/orchestration.py
```

### Implementar

```python
class OrchestrationFlow:
    """
    Turno completo com MySQL.
    """
    
    def __init__(
        self,
        mysql_client: MysqlDatastoreClient,
        postgres_client: PostgresDatastoreClient,
        redis_client: RedisDatastoreClient,
        allowlist: SqlAllowlist
    ):
        self.executor = AnalyticsExecutor(mysql_client, allowlist)
        self.pipeline = DataPipeline()
        self.context_builder = AnalyticalContextBuilder()
        self.memory_composer = MemoryComposer(postgres_client, redis_client)
    
    async def process_turn(
        self,
        user_query: str,
        user_id: str,
        session_id: str,
        token_budget: int = 4000
    ) -> dict:
        """
        1. Analisar query
        2. Buscar dados MySQL
        3. Processar pipeline
        4. Integrar memory
        5. Montar contexto
        6. Preparar para LLM
        """
        
        # 1. Executor (query → MySQL)
        result = await self.executor.execute(
            user_query,
            correlation_id=session_id
        )
        
        # 2. Pipeline (MySQL rows → estruturado)
        pipeline_output = await self.pipeline.process(result)
        
        # 3. Memory (buscar memory curta)
        memory_curta = await self.memory_composer.get_memory(
            user_id,
            intent=self._infer_intent(user_query)
        )
        
        # 4. Context Builder (montar blocos)
        context_blocks = await self.context_builder.build(
            pipeline_output,
            memory_curta=memory_curta,
            user_id=user_id,
            token_budget=token_budget
        )
        
        # 5. Salvar em PostgreSQL
        await self.memory_composer.append_turn(
            session_id,
            user_query,
            pipeline_output
        )
        
        # 6. Return para next step (LLM)
        return {
            "context_blocks": context_blocks,
            "pipeline_output": pipeline_output,
            "sql_executed": result.sql,
            "row_count": result.row_count
        }
    
    def _infer_intent(self, query: str) -> str:
        """Detectar intent de query"""
        q_lower = query.lower()
        if any(w in q_lower for w in ["ticket", "faturamento", "receita"]):
            return "FATURAMENTO"
        elif any(w in q_lower for w in ["retrabalho", "qualidade"]):
            return "QUALIDADE"
        else:
            return "GENERIC"
```

---

## 📦 Tarefa 4.2 — FastAPI Endpoint

### Arquivo

```
src/orion_mcp_v3/routes/chat.py
```

### Implementar

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.post("/api/v1/chat")
async def chat(request: ChatRequest):
    """
    POST /api/v1/chat
    {
        "message": "qual é o ticket de janeiro?",
        "user_id": "conc_001",
        "session_id": "uuid..."
    }
    """
    
    try:
        # Orchestration (tudo incluindo MySQL)
        flow_result = await orchestration.process_turn(
            user_query=request.message,
            user_id=request.user_id,
            session_id=request.session_id
        )
        
        # LLM Narrator (recebe context blocks)
        # ... chamar LLM aqui ...
        
        return {
            "reply": "...",
            "metadata": {
                "sql_executed": flow_result["sql_executed"],
                "row_count": flow_result["row_count"]
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

---

## ✅ RESULTADO FASE 4

```text
Fluxo completo: Query → MySQL → Context → LLM → Resposta
Integrado e funcionando.
```

---

# 📊 COMPARAÇÃO: Antes vs Depois

## SEM MySQL (Maestro v2)

```
❌ Query → LLM processa dados brutos
❌ Sem agregações específicas
❌ LLM inventa respostas
❌ Sem segurança SQL
```

## COM MySQL (OrionMCP v3)

```
✅ Query → Planner (intenção analítica) → SQL Compiler → MySQL
✅ Analytical Reduction Layer: aggregators → samplers → reducers → EvidenceBuilder → digest orientado a evidência
✅ Dados agregados + sampled + reduzidos semanticamente (não só "rows → resumo")
✅ LLM só narra a partir de evidência estruturada
✅ SQL seguro (allowlist + parameterizado)
✅ Memory integrada + Context Fusion (competição por budget)
✅ Provenance / coverage ancoráveis a cada insight
```

---

# 🎯 CHECKLIST DE IMPLEMENTAÇÃO

### FASE 1.5 — Analytics Executor

- [ ] AnalyticsExecutor (executor.py)
- [ ] SqlAllowlist config (allowlists.py)
- [ ] Testes AnalyticsExecutor
- [ ] Documentação de uso

### FASE 2.5 — Data Pipeline Real

- [ ] Schema-aware DataPipeline (melhorado)
- [ ] Testes DataPipeline com MySQL real
- [ ] Integração com AnalyticsResult
- [ ] `reducers.py` + `evidence_builder.py` + `policies.py` (ou equivalente) conforme **Analytical Reduction Layer**
- [ ] Contrato `EvidenceBlock` + provenance anchoring nos insights

### FASE 3.5 — Context Builder para Dados

- [ ] AnalyticalContextBuilder
- [ ] Integração com BudgetAllocator
- [ ] Testes E2E

### FASE 4 — Orchestration Final

- [ ] OrchestrationFlow completo
- [ ] FastAPI endpoint /api/v1/chat
- [ ] Testes de turno completo
- [ ] Documentação

---

# 🔗 FLUXO VISUAL

```
┌─────────────────────────────────────────────────────────────┐
│ User: "qual é o ticket de janeiro?"                        │
└────────┬────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ OrchestrationFlow.process_turn()                            │
├─────────────────────────────────────────────────────────────┤
│ 1. AnalyticsExecutor                                        │
│    ├─ Planner: "janeiro" → hints {time_grain: month}      │
│    ├─ SQL Compiler: hints → SELECT from vendas ...         │
│    └─ MySQL: execute + retorna rows                        │
│                                                             │
│ 2. Analytical Reduction Layer (+ DataPipeline orquestrando) │
│    ├─ aggregators → group_by / temporal / ranking …        │
│    ├─ samplers → recent / outliers / estratificação        │
│    ├─ reducers → insights semânticos                       │
│    ├─ EvidenceBuilder → EvidenceBlock                      │
│    └─ AnalyticalDigest (evidence-oriented)                  │
│                                                             │
│ 3. MemoryComposer                                           │
│    └─ get_memory(conc_001, FATURAMENTO)                   │
│       (previous insights, key_metrics)                     │
│                                                             │
│ 4. Context Fusion + AnalyticalContextBuilder                │
│    ├─ fundir blocos analytics + memory                     │
│    ├─ SYSTEM / DATA / MEMORY ContextBlocks                 │
│    └─ BudgetAllocator (tokens; density / cost futuros)     │
│                                                             │
│ 5. Save to PostgreSQL                                      │
│    └─ conversation_state + memory_embeddings               │
└────────┬────────────────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────────────────────────┐
│ LLM Narrator (próximo passo)                                │
│ Recebe: context_blocks (estruturado)                       │
│ Retorna: resposta acionável                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Futura evolução

```text
analytics pipeline → evidence reasoning engine
```

O salto perigoso cognitivamente é **`SQL rows → digest`** sem camadas intermediárias de **aggregation → sampling → reduction → evidence**. Este roadmap passa a explicitar essa **Analytical Reduction Layer** para evitar esse salto.

---

# 🏁 PRÓXIMOS PASSOS REAIS

1. **Implementar Fase 1.5** (AnalyticsExecutor + allowlist)
2. **Testar com dados reais** do seu MySQL
3. **Implementar Fase 2.5** (DataPipeline melhorado)
4. **Integrar memory** (Fase 3.5)
5. **Endpoint HTTP** (Fase 4)
6. **Deploy e validação**

---

**Status**: Pronto para começar Fase 1.5  
**Tempo estimado**: 2-3 semanas (incluindo testes)  
**Primeira entrega**: Chat funcional respondendo do MySQL
