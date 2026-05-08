# 🔧 INTEGRAÇÃO MYSQL - PLANO DETALHADO

**Objetivo**: Conectar o que JÁ EXISTE (connection_hub, broker) com MySQL  
**Status**: Connection hub ✅, Broker MVP ✅, Falta: Executor + Pipeline + Orchestrator

---

## 📦 ARQUITETURA ATUAL

```
OrionMCP V3 (Atual)
├── connection_hub/ ✅ (MySQL, PostgreSQL, Redis pools)
├── runtime/ ✅ (BudgetAllocator, AttentionPolicy, ContextState)
├── contracts/ ✅ (ContextBlock, QueryPlan, Digest)
├── memory/ ✅ (Composer, Repositories)
└── broker/ ✅ (Planner, SQL Compiler, Aggregators, Samplers)

❌ FALTA: Executor (orquestra tudo)
❌ FALTA: Orchestrator (turno completo)
❌ FALTA: API HTTP
```

---

## 🔄 FLUXO SEM EXECUTOR (Hoje)

```
Query Text ──→ Planner ──→ SemanticQueryPlan
                                ↓
                            SQL Compiler
                                ↓
                            CompiledSql
                                ↓
                                ❌ PARADO (sem executor)
```

## 🔄 FLUXO COM EXECUTOR (Novo)

```
Query Text ──→ Planner ──→ SemanticQueryPlan
                                ↓
                            SQL Compiler ──→ CompiledSql
                                                ↓
                            ✅ AnalyticsExecutor
                                                ↓
                            MySQL (via connection_hub)
                                                ↓
                            AnalyticsResult (rows)
                                                ↓
                            DataPipeline (schema, summary, sample)
                                                ↓
                            ContextBuilder (montar blocos)
                                                ↓
                            LLM (narração)
```

---

## 🎯 PASSO 1: AnalyticsExecutor (20 min)

### Arquivo a criar

```
src/orion_mcp_v3/broker/executor.py
```

### Código

```python
"""
Analytics Executor (Fase 1.5).
Orquestra: Planner → SQL Compiler → MySQL.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orion_mcp_v3.connection_hub.abstract import AbstractDatastoreClient
from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan
from orion_mcp_v3.broker.planner import plan_from_natural_language
from orion_mcp_v3.broker.sql_compiler import compile_select, SqlAllowlist, CompiledSql


@dataclass(frozen=True)
class AnalyticsResult:
    """Resultado de uma query executada."""
    
    plan: SemanticQueryPlan
    sql: str
    rows: list[dict[str, Any]]
    row_count: int


class AnalyticsExecutor:
    """
    Orquestrador: Query Text → MySQL Rows.
    
    1. Text → Plan (Planner)
    2. Plan → SQL (SQL Compiler)
    3. SQL → Rows (MySQL)
    """
    
    def __init__(
        self,
        mysql_client: AbstractDatastoreClient,
        allowlist: SqlAllowlist,
        default_limit: int = 1000
    ):
        """
        Args:
            mysql_client: MysqlDatastoreClient (de connection_hub)
            allowlist: Tabelas/colunas permitidas
            default_limit: LIMIT padrão se não especificado
        """
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
        Executa uma query em linguagem natural.
        
        Args:
            query_text: "últimos 3 meses faturamento"
            intent_slug: tipo de análise
            correlation_id: ID de rastreamento
        
        Returns:
            AnalyticsResult com rows do MySQL
        """
        
        # Step 1: Planner (já existe em broker/planner.py)
        plan = plan_from_natural_language(
            query_text,
            intent_slug=intent_slug,
            correlation_id=correlation_id
        )
        
        # Step 2: SQL Compiler (já existe em broker/sql_compiler.py)
        compiled = compile_select(
            plan,
            self.allowlist,
            default_limit=self.default_limit
        )
        
        # Step 3: MySQL Execute (via connection_hub)
        rows = await self.mysql_client.select(
            compiled.sql,
            params=compiled.params
        )
        
        # Step 4: Resultado
        return AnalyticsResult(
            plan=plan,
            sql=compiled.sql,
            rows=rows,
            row_count=len(rows)
        )
```

### Integração com Connection Hub

```python
# Em seu código de startup:

from orion_mcp_v3.connection_hub import MysqlDatastoreClient
from orion_mcp_v3.broker.executor import AnalyticsExecutor
from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST

# Pool MySQL (já criado em connection_hub)
mysql_pool = await asyncmy.create_pool(
    host=os.getenv("MYSQL_HOST"),
    port=int(os.getenv("MYSQL_PORT", 3306)),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    db=os.getenv("MYSQL_DATABASE"),
    minsize=5,
    maxsize=20
)

# Cliente MySQL
mysql_client = MysqlDatastoreClient(mysql_pool)

# Executor
executor = AnalyticsExecutor(
    mysql_client,
    allowlist=ANALYTICS_ALLOWLIST
)

# Usar
result = await executor.execute("últimos 3 meses")
print(f"Rows: {result.row_count}")
print(f"SQL: {result.sql}")
```

---

## 🎯 PASSO 2: SqlAllowlist Config (10 min)

### Arquivo a criar

```
src/orion_mcp_v3/config/allowlists.py
```

### Código (CUSTOMIZE PARA SEU SCHEMA)

```python
"""
Allowlist de tabelas/colunas permitidas para queries MySQL.

Restringe acesso apenas ao que o LLM pode questionar.
Previne SQL injection.
"""

from orion_mcp_v3.broker.sql_compiler import SqlAllowlist


ANALYTICS_ALLOWLIST = SqlAllowlist(
    # Tabelas permitidas
    tables=frozenset([
        "vendas",
        "os",  # ordens_servico
        "servicos",
        "funcionarios",
        "concessionarias",
        "clientes",  # se tiver
        "venda_metas"  # se tiver
    ]),
    
    # Colunas por tabela
    columns_by_table={
        "vendas": frozenset([
            "id",
            "os_id",
            "concessionaria_id",
            "vendedor_id",
            "servico_id",
            "valor_venda_real_servico_a",
            "valor_venda_real_servico_b",
            "data_venda",
            "status",
            "created_at"
        ]),
        
        "os": frozenset([
            "id",
            "concessionaria_id",
            "vendedor_id",
            "status",
            "data_criacao",
            "data_finalizacao",
            "reaberta",
            "created_at"
        ]),
        
        "servicos": frozenset([
            "id",
            "nome",
            "servico_categoria_id",
            "preco_custo",
            "descricao"
        ]),
        
        "funcionarios": frozenset([
            "id",
            "nome",
            "tipo_funcionario",
            "concessionaria_id",
            "data_admissao",
            "ativo"
        ]),
        
        "concessionarias": frozenset([
            "id",
            "nome",
            "localizacao",
            "ativo"
        ]),
        
        "venda_metas": frozenset([
            "id",
            "concessionaria_id",
            "vendedor_id",
            "periodo",
            "meta_valor",
            "realizado_valor"
        ])
    }
)


# CUSTOMIZAR PARA SEU SCHEMA:
# 1. Listar TODAS as tabelas de analytics
# 2. Para cada tabela, listar colunas "seguras"
# 3. NÃO INCLUIR: cpf, email, passwords, dados sensíveis
# 4. NÃO INCLUIR: colunas internas de sistema

"""
Exemplo de schema completo que você deveria checar:

SHOW TABLES;  # Ver todas

Para cada tabela:
DESCRIBE tabela;  # Ver colunas

Depois preencher acima.
"""
```

---

## 🎯 PASSO 3: DataPipeline Atualizado (30 min)

### Arquivo a atualizar/criar

```
src/orion_mcp_v3/broker/data_pipeline.py
```

### Código

```python
"""
Data Pipeline: AnalyticsResult → ContextBlocks.

Processa: schema inference → summary → insights → sample
"""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime
from typing import Any

from orion_mcp_v3.broker.executor import AnalyticsResult
from orion_mcp_v3.runtime.provenance import CoverageInfo


class DataPipeline:
    """
    Transforma AnalyticsResult em estrutura pronta para contexto.
    """
    
    async def process(self, result: AnalyticsResult) -> dict[str, Any]:
        """
        1. Infer schema dos rows
        2. Build summary (agregações)
        3. Extract insights (padrões automáticos)
        4. Build sample (amostra)
        
        Returns:
            Dict com tudo estruturado
        """
        
        if not result.rows:
            return {
                "query_text": result.plan.intent_slug,
                "sql": result.sql,
                "row_count": 0,
                "schema": {},
                "summary": {},
                "insights": ["Nenhum resultado encontrado"],
                "sample": [],
                "coverage": CoverageInfo(
                    total_rows=0,
                    sample_rows=0,
                    schema_fields=0
                )
            }
        
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
    
    def _infer_schema(self, rows: list[dict]) -> dict[str, str]:
        """Detecta tipos de coluna automaticamente."""
        if not rows:
            return {}
        
        schema = {}
        first_row = rows[0]
        
        for col_name, col_value in first_row.items():
            if isinstance(col_value, bool):
                col_type = "boolean"
            elif isinstance(col_value, int):
                col_type = "integer"
            elif isinstance(col_value, float):
                col_type = "float"
            elif isinstance(col_value, datetime):
                col_type = "timestamp"
            elif isinstance(col_value, str):
                col_type = "string"
            else:
                col_type = "unknown"
            
            schema[col_name] = col_type
        
        return schema
    
    def _build_summary(self, rows: list[dict], schema: dict[str, str]) -> dict[str, Any]:
        """Agregações por coluna (não por linha)."""
        summary = {}
        
        for col_name, col_type in schema.items():
            # Extrair valores dessa coluna
            values = [r.get(col_name) for r in rows if col_name in r and r[col_name] is not None]
            
            if not values:
                continue
            
            if col_type in ("integer", "float"):
                # Estatísticas numéricas
                summary[col_name] = {
                    "type": "numeric",
                    "count": len(values),
                    "media": round(statistics.mean(values), 2),
                    "min": min(values),
                    "max": max(values),
                    "desvio_padrao": round(statistics.stdev(values), 2) if len(values) > 1 else 0
                }
            
            elif col_type == "string":
                # Contagem de valores únicos + top valores
                counter = Counter(values)
                summary[col_name] = {
                    "type": "string",
                    "count": len(values),
                    "unique": len(counter),
                    "top_5": dict(counter.most_common(5))
                }
            
            elif col_type == "timestamp":
                # Range de datas
                summary[col_name] = {
                    "type": "timestamp",
                    "count": len(values),
                    "earliest": min(values),
                    "latest": max(values)
                }
        
        return summary
    
    def _extract_insights(self, rows: list[dict], summary: dict[str, Any]) -> list[str]:
        """Detecta padrões/anomalias automáticas."""
        insights = []
        
        # Padrão 1: Alta variância em colunas numéricas
        for col_name, stats in summary.items():
            if stats.get("type") == "numeric":
                media = stats.get("media", 0)
                desvio = stats.get("desvio_padrao", 0)
                
                if media > 0 and desvio > media * 2:
                    insights.append(f"⚠️ {col_name}: alta variância (desvio {desvio:.2f})")
        
        # Padrão 2: Distribuição enviesada (poucas categorias)
        for col_name, stats in summary.items():
            if stats.get("type") == "string":
                total = stats.get("count", 0)
                unique = stats.get("unique", 0)
                
                if total > 0 and unique < total * 0.1:  # < 10% de valores únicos
                    insights.append(f"📊 {col_name}: distribuição concentrada ({unique} valores únicos em {total})")
        
        # Padrão 3: Intervalo de datas largo
        for col_name, stats in summary.items():
            if stats.get("type") == "timestamp":
                earliest = stats.get("earliest")
                latest = stats.get("latest")
                if earliest and latest:
                    delta_days = (latest - earliest).days
                    if delta_days > 365:
                        insights.append(f"📅 {col_name}: dados de {delta_days} dias")
        
        return insights if insights else ["Sem anomalias detectadas"]
    
    def _build_sample(self, rows: list[dict]) -> list[dict]:
        """Amostra: head (2) + tail (2) + outliers (1)."""
        if len(rows) <= 5:
            return rows
        
        # Head: primeiras 2
        head = rows[:2]
        
        # Tail: últimas 2
        tail = rows[-2:]
        
        # Outliers: por primeira coluna numérica
        outliers = []
        first_row = rows[0]
        numeric_cols = [k for k, v in first_row.items() if isinstance(v, (int, float))]
        
        if numeric_cols:
            col_name = numeric_cols[0]
            # Ordenar por essa coluna e pegar o maior (outlier)
            sorted_rows = sorted(rows, key=lambda r: r.get(col_name, 0), reverse=True)
            outliers = sorted_rows[:1]  # Apenas o maior
        
        # Combinar (evitar duplicatas)
        sample_dict = {}
        for i, row in enumerate(head + tail + outliers):
            # Use índice para evitar duplicata com dict
            key = f"__{i}"
            if row not in sample_dict.values():
                sample_dict[key] = row
        
        return list(sample_dict.values())[:5]  # Max 5 linhas na amostra
```

### Teste

```python
# tests/test_data_pipeline_integrated.py

import pytest
from orion_mcp_v3.broker.executor import AnalyticsResult, AnalyticsExecutor
from orion_mcp_v3.broker.data_pipeline import DataPipeline
from orion_mcp_v3.contracts.query_plan import SemanticQueryPlan, RetrievalStrategy


@pytest.mark.asyncio
async def test_pipeline_with_mock_result():
    """Testa pipeline com dados fictícios."""
    
    # Mock AnalyticsResult
    mock_rows = [
        {"id": 1, "valor": 1000, "data": "2025-01-01"},
        {"id": 2, "valor": 2000, "data": "2025-01-02"},
        {"id": 3, "valor": 3000, "data": "2025-01-03"},
    ]
    
    plan = SemanticQueryPlan(
        intent_slug="test",
        strategy=RetrievalStrategy.BROKER_FANOUT,
        target_collections=(),
        hints={}
    )
    
    result = AnalyticsResult(
        plan=plan,
        sql="SELECT * FROM test",
        rows=mock_rows,
        row_count=3
    )
    
    # Pipeline
    pipeline = DataPipeline()
    output = await pipeline.process(result)
    
    # Asserts
    assert output["row_count"] == 3
    assert "schema" in output
    assert "valor" in output["schema"]
    assert output["schema"]["valor"] == "integer"
    assert len(output["sample"]) > 0
    assert len(output["insights"]) > 0
```

---

## 🎯 PASSO 4: Teste Integrado (20 min)

### Arquivo

```
tests/test_executor_pipeline_integrated.py
```

### Código

```python
import pytest
import asyncmy

from orion_mcp_v3.connection_hub import MysqlDatastoreClient
from orion_mcp_v3.broker.executor import AnalyticsExecutor
from orion_mcp_v3.broker.data_pipeline import DataPipeline
from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST


@pytest.mark.asyncio
async def test_executor_and_pipeline_integrated():
    """
    Teste integrado:
    Query → Planner → SQL Compiler → MySQL → Pipeline
    """
    
    # Setup MySQL (usar dados de teste reais)
    mysql_pool = await asyncmy.create_pool(
        host="localhost",
        port=3306,
        user="test_user",
        password="test_pass",
        db="test_db",
        minsize=1,
        maxsize=5
    )
    
    try:
        mysql_client = MysqlDatastoreClient(mysql_pool)
        executor = AnalyticsExecutor(
            mysql_client,
            allowlist=ANALYTICS_ALLOWLIST
        )
        
        # Executar
        result = await executor.execute("últimos 3 meses")
        
        # Validar result
        assert result.sql is not None
        assert "SELECT" in result.sql.upper()
        assert result.row_count >= 0
        
        # Pipeline
        if result.row_count > 0:
            pipeline = DataPipeline()
            output = await pipeline.process(result)
            
            assert "schema" in output
            assert "summary" in output
            assert "sample" in output
            assert "insights" in output
            
            print(f"✅ Query sucedeu: {result.row_count} rows")
            print(f"   SQL: {result.sql}")
            print(f"   Schema: {list(output['schema'].keys())}")
    
    finally:
        mysql_pool.close()
        await mysql_pool.wait_closed()
```

---

## 📋 CHECKLIST RÁPIDO

### Passo 1: AnalyticsExecutor ✅
- [ ] Criar `src/orion_mcp_v3/broker/executor.py`
- [ ] Importar Planner e SQL Compiler
- [ ] Implementar classe AnalyticsExecutor
- [ ] Testar com mock data

### Passo 2: SqlAllowlist ✅
- [ ] Criar `src/orion_mcp_v3/config/allowlists.py`
- [ ] Customizar para seu schema MySQL
- [ ] Validar que tabelas/colunas estão corretas

### Passo 3: DataPipeline ✅
- [ ] Criar `src/orion_mcp_v3/broker/data_pipeline.py`
- [ ] Implementar schema inference
- [ ] Implementar summary builder
- [ ] Implementar insights extractor
- [ ] Implementar sampler

### Passo 4: Testes ✅
- [ ] Teste de executor com mock data
- [ ] Teste de pipeline
- [ ] Teste integrado (Executor + Pipeline)

---

## 🚀 COMO COMEÇAR AGORA

1. **Criar arquivo**: `executor.py` (copie código acima)
2. **Criar arquivo**: `allowlists.py` (customize seu schema)
3. **Criar/atualizar**: `data_pipeline.py` (copie código)
4. **Criar teste**: `test_executor_pipeline_integrated.py`
5. **Rodar teste**: `pytest tests/test_executor_pipeline_integrated.py -v`
6. **Debugar**: Verificar SQL gerado, dados retornados, schema

---

## ✨ RESULTADO

Após estes 4 passos:

```
Query em português → SQL correto → MySQL → Dados processados
                                              schema + summary + sample + insights
```

Pronto para próximo passo: **ContextBuilder** (integrar com memory + LLM)
