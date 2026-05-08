# 🎯 ORQUESTRAÇÃO UNIFICADA: Memória + Dados Reais

**Problema**: Dois caminhos separados (Analítico vs Memória) que precisam funcionar **juntos** numa única resposta.

**Solução**: Criar um **UnifiedOrchestrator** que une tudo com regras explícitas.

---

## 📊 O PROBLEMA VISUAL

### Hoje (Separado)

```
Caminho Analítico:                 Caminho Memória:
Query ──→ MySQL ──→ Dados    vs    Query ──→ MemoryComposer ──→ Histórico
            ↓                                    ↓
        DataPipeline                    Blocos MEMORY/USER/ASSISTANT
            ↓                                    ↓
    AnalyticalContextBuilder              Blocos soltos
            ↓
      Blocos DATA/SYSTEM

❌ NÃO sabem um do outro
❌ BudgetAllocator roda 2x?
❌ Qual é a ordem no prompt?
❌ Como escolher query? (Decision Engine?)
```

### Amanhã (Unificado)

```
┌─────────────────────────────────────────────┐
│ UnifiedOrchestrator                         │
├─────────────────────────────────────────────┤
│ 1. Decision Engine                          │
│    Pergunta → QUAL query? (faturamento?)   │
│                                             │
│ 2. Paralelo:                                │
│    ├─ Analytics Path:                       │
│    │  Query específica → MySQL → Pipeline   │
│    └─ Memory Path:                          │
│       MemoryComposer.compose()              │
│                                             │
│ 3. Merge Inteligente:                       │
│    Blocks = [SYSTEM, MEMORY, DATA, USER]   │
│    ↓ Com ordem + prioridades definidas     │
│                                             │
│ 4. Um só BudgetAllocator:                   │
│    Aloca tokens respeitando prioridades     │
│                                             │
│ 5. Resultado:                               │
│    Prompt = [System + Memory + Data]       │
│    ✅ Unificado, auditável, determinístico │
└─────────────────────────────────────────────┘
```

---

## 🏗️ ARQUITETURA UNIFICADA

### Componentes

```
src/orion_mcp_v3/
├── decision/                          ⭐ NOVO
│   └── decision_engine.py            # pergunta → query_id
│
├── broker/
│   ├── executor.py                   # ✅ Query → MySQL
│   ├── data_pipeline.py              # ✅ Rows → Estruturado
│   └── unifier.py                    ⭐ NOVO: une Analytics + Memory
│
├── memory/
│   ├── composer.py                   # ✅ Turnos → Blocos
│   └── retriever.py                  ⭐ NOVO: busca memoria relevante
│
├── runtime/
│   ├── context_builder.py            ⭐ NOVO: UnifiedContextBuilder
│   └── orchestrator.py               ⭐ NOVO: UnifiedOrchestrator
│
└── config/
    └── decision_rules.py             ⭐ NOVO: heurísticas de query
```

---

## 🔧 COMPONENTE 1: Decision Engine

### Arquivo

```
src/orion_mcp_v3/decision/decision_engine.py
```

### Código

```python
"""
Decision Engine: Pergunta → Qual query executar?

Responsabilidade ÚNICA: Mapear pergunta natural → query_id
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class QueryCategory(Enum):
    """Categorias de queries disponíveis."""
    FATURAMENTO = "faturamento"
    QUALIDADE = "qualidade"
    PERFORMANCE = "performance"
    MIX = "mix"  # cross-selling
    TRENDS = "trends"
    NONE = "none"  # Sem query (só usar memory)


@dataclass(frozen=True)
class DecisionResult:
    """Resultado da decisão."""
    category: QueryCategory
    query_id: str | None  # "ticket_medio", "retrabalho", etc
    confidence: float  # 0.0-1.0
    reason: str
    use_memory: bool  # Incluir memory curta?


class DecisionEngine:
    """
    Decide qual query rodar baseado em heurísticas.
    
    Sem LLM - determinístico - auditável.
    """
    
    # Mapa: padrão regex → (categoria, query_id)
    INTENT_MAP = {
        r"(ticket|valor.*m[ée]dio|receita|faturamento)": (
            QueryCategory.FATURAMENTO,
            "ticket_medio"
        ),
        r"(retrabalho|qualidade|reaberta)": (
            QueryCategory.QUALIDADE,
            "taxa_retrabalho"
        ),
        r"(ranking|performance|vendedor|melhor)": (
            QueryCategory.PERFORMANCE,
            "performance_vendedor"
        ),
        r"(combo|cross-sell|juntos|pair)": (
            QueryCategory.MIX,
            "cross_selling"
        ),
        r"(trend|sazon|crescimento|padr[ãa]o)": (
            QueryCategory.TRENDS,
            "sazonalidade"
        ),
    }
    
    def decide(
        self,
        user_query: str,
        previous_intent: str | None = None
    ) -> DecisionResult:
        """
        Decide baseado em:
        1. Match com padrões regex
        2. Continuação de intent anterior (para "e o...?")
        3. Fallback: só memory
        """
        
        query_lower = user_query.lower().strip()
        
        # Padrão 1: Continuação ("e o...?", "e a...?")
        if re.match(r"^(e\s+o|e\s+a|t[ãa]o|ent[ãa]o|al[ém]m)\b", query_lower):
            if previous_intent:
                return DecisionResult(
                    category=QueryCategory[previous_intent.upper()],
                    query_id=self._get_query_for_intent(previous_intent),
                    confidence=0.95,
                    reason=f"Continuação de {previous_intent}",
                    use_memory=True
                )
        
        # Padrão 2: Match com patterns
        for pattern, (category, query_id) in self.INTENT_MAP.items():
            if re.search(pattern, query_lower):
                return DecisionResult(
                    category=category,
                    query_id=query_id,
                    confidence=0.85,
                    reason=f"Matched pattern: {pattern}",
                    use_memory=True
                )
        
        # Padrão 3: Fallback (só memory, sem query)
        return DecisionResult(
            category=QueryCategory.NONE,
            query_id=None,
            confidence=0.0,
            reason="Pergunta genérica ou não reconhecida",
            use_memory=True  # Sempre usar memory
        )
    
    def _get_query_for_intent(self, intent: str) -> str | None:
        """Retorna query_id para intenção."""
        mapping = {
            "faturamento": "ticket_medio",
            "qualidade": "taxa_retrabalho",
            "performance": "performance_vendedor",
            "mix": "cross_selling",
            "trends": "sazonalidade"
        }
        return mapping.get(intent.lower())
```

---

## 🔧 COMPONENTE 2: Memory Retriever

### Arquivo

```
src/orion_mcp_v3/memory/retriever.py
```

### Código

```python
"""
Memory Retriever: Busca memory relevante para a pergunta.

Diferente do MemoryComposer - esse busca DADOS persistidos,
não apenas o histórico literal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MemoryRetrievalResult:
    """Resultado da busca de memory."""
    category: str  # "FATURAMENTO", "QUALIDADE", etc
    recent_insights: list[str]  # ["Crescimento +12%", ...]
    key_metrics: dict[str, Any]  # {"ticket": 1450, ...}
    last_update: str  # ISO timestamp
    confidence: float  # 0.0-1.0


class MemoryRetriever:
    """
    Busca memory curta/longa relevante para a pergunta.
    
    Integra com Redis + PostgreSQL conforme necessário.
    """
    
    def __init__(self, redis_client, postgres_client):
        self.redis = redis_client
        self.postgres = postgres_client
    
    async def retrieve(
        self,
        user_id: str,
        category: str,  # "FATURAMENTO"
        query_text: str
    ) -> MemoryRetrievalResult | None:
        """
        Busca memory associada a uma categoria.
        
        Ordem de prioridade:
        1. Redis (memory curta, fresquíssima)
        2. PostgreSQL (memory consolidada)
        3. None (sem memoria)
        """
        
        # 1. Tenta Redis (cache hot)
        redis_key = f"memory:{user_id}:{category}"
        cached = await self.redis.hget(redis_key)
        
        if cached:
            import json
            data = json.loads(cached)
            return MemoryRetrievalResult(
                category=category,
                recent_insights=data.get("key_insights", []),
                key_metrics=data.get("key_metrics", {}),
                last_update=data.get("last_update", "unknown"),
                confidence=0.95  # Redis é bem recente
            )
        
        # 2. PostgreSQL (memory consolidada)
        row = await self.postgres.select(
            """
            SELECT category, key_insights, key_metrics, last_updated
            FROM memory_essence
            WHERE user_id = %s AND category = %s
            """,
            params=[user_id, category]
        )
        
        if row:
            import json
            data = row[0]
            return MemoryRetrievalResult(
                category=category,
                recent_insights=json.loads(data.get("key_insights", "[]")),
                key_metrics=json.loads(data.get("key_metrics", "{}")),
                last_update=data.get("last_updated", "unknown"),
                confidence=0.75  # PostgreSQL é mais antiga
            )
        
        # 3. Sem memory
        return None
```

---

## 🔧 COMPONENTE 3: Unifier (Analytics + Memory)

### Arquivo

```
src/orion_mcp_v3/broker/unifier.py
```

### Código

```python
"""
Unifier: Junta resultado analítico com memory.

Cria JSON estruturado com:
- Analytics data
- Memory insights
- Metadata
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json


@dataclass
class UnifiedDataOutput:
    """Resultado unificado (dados + memory)."""
    
    # Do Analytics
    sql_executed: str
    rows_count: int
    schema: dict[str, str]
    summary: dict[str, Any]
    sample: list[dict]
    insights_from_data: list[str]
    
    # Do Memory
    memory_category: str | None
    memory_insights: list[str] | None
    memory_metrics: dict[str, Any] | None
    
    # Merged
    combined_insights: list[str]
    recommended_focus: str | None


class AnalyticsMemoryUnifier:
    """
    Junta resultado do AnalyticsExecutor + MemoryRetriever.
    """
    
    async def unify(
        self,
        analytics_result: Any,  # AnalyticsResult
        pipeline_output: dict[str, Any],
        memory_result: Any | None  # MemoryRetrievalResult
    ) -> UnifiedDataOutput:
        """
        Merge inteligente: dados reais + memory.
        
        Regras:
        1. Dados reais são "verdade"
        2. Memory é "contexto histórico"
        3. Combinar insights
        4. Detectar conflitos
        """
        
        # Parse memory
        memory_insights = []
        memory_metrics = {}
        memory_category = None
        
        if memory_result:
            memory_insights = memory_result.recent_insights
            memory_metrics = memory_result.key_metrics
            memory_category = memory_result.category
        
        # Combinar insights
        combined = list(set(
            pipeline_output.get("insights", []) +
            memory_insights
        ))
        
        # Detectar focus (recomendação para LLM)
        recommended_focus = self._recommend_focus(
            pipeline_output.get("summary", {}),
            memory_metrics
        )
        
        return UnifiedDataOutput(
            sql_executed=analytics_result.sql,
            rows_count=analytics_result.row_count,
            schema=pipeline_output.get("schema", {}),
            summary=pipeline_output.get("summary", {}),
            sample=pipeline_output.get("sample", []),
            insights_from_data=pipeline_output.get("insights", []),
            memory_category=memory_category,
            memory_insights=memory_insights,
            memory_metrics=memory_metrics,
            combined_insights=combined,
            recommended_focus=recommended_focus
        )
    
    def _recommend_focus(self, summary: dict, memory_metrics: dict) -> str | None:
        """
        Recomenda onde o LLM deve focar.
        
        Ex: "Dados mostram +12%, memory mostra padrão histórico de +3-5%: investigar causa"
        """
        if not summary or not memory_metrics:
            return None
        
        # Exemplo: comparar metric atual vs historical
        # Este é um exemplo simplificado
        return None  # TODO: implementar lógica


def unified_output_to_json(output: UnifiedDataOutput) -> str:
    """Serializa UnifiedDataOutput para JSON limpo."""
    
    return json.dumps({
        "analytics": {
            "sql": output.sql_executed,
            "rows": output.rows_count,
            "schema": output.schema,
            "summary": output.summary,
            "sample": output.sample
        },
        "memory": {
            "category": output.memory_category,
            "insights": output.memory_insights,
            "metrics": output.memory_metrics
        },
        "combined": {
            "insights": output.combined_insights,
            "focus": output.recommended_focus
        }
    }, default=str)
```

---

## 🔧 COMPONENTE 4: UnifiedContextBuilder

### Arquivo

```
src/orion_mcp_v3/runtime/unified_context_builder.py
```

### Código

```python
"""
UnifiedContextBuilder: Monta blocos finais a partir de dados + memory.

Responsabilidade ÚNICA: Organizar blocos na ordem correta com prioridades.
"""

from __future__ import annotations

from typing import Any
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.broker.unifier import UnifiedDataOutput
import json


class UnifiedContextBuilder:
    """
    Monta blocos de contexto num ordem bem definida:
    1. SYSTEM: instruções do modelo
    2. MEMORY: histórico relevante
    3. DATA: resumo + insights dos dados reais
    4. USER: a pergunta atual
    """
    
    async def build(
        self,
        user_query: str,
        unified_data: UnifiedDataOutput,
        decision_result: Any,  # DecisionResult
        user_id: str | None = None,
        token_budget: int = 4000
    ) -> list[ContextBlock]:
        """
        Monta blocos prontos para LLM.
        
        Ordem (importante!):
        1. SYSTEM (role:mentor/narrator)
        2. MEMORY (contexto histórico)
        3. DATA (evidência tabular)
        4. USER (pergunta atual)
        """
        
        blocks = []
        
        # 1. SYSTEM: Instruções
        system_content = self._build_system_prompt(decision_result)
        blocks.append(ContextBlock(
            role=ContextRole.SYSTEM,
            source=ContextSource.BROKER,
            content=system_content,
            token_estimate=300
        ))
        
        # 2. MEMORY: Histórico + contexto anterior
        if unified_data.memory_insights or unified_data.memory_metrics:
            memory_content = self._build_memory_block(unified_data)
            blocks.append(ContextBlock(
                role=ContextRole.CONTEXT,
                source=ContextSource.MEMORY,
                content=memory_content,
                token_estimate=len(memory_content) // 4
            ))
        
        # 3. DATA: Dados reais + insights
        data_content = self._build_data_block(unified_data)
        blocks.append(ContextBlock(
            role=ContextRole.DATA,
            source=ContextSource.BROKER,
            content=data_content,
            token_estimate=len(data_content) // 4
        ))
        
        # 4. USER: Pergunta
        blocks.append(ContextBlock(
            role=ContextRole.USER,
            source=ContextSource.USER,
            content=user_query,
            token_estimate=len(user_query) // 4
        ))
        
        # Allocate budget
        from orion_mcp_v3.runtime.budget_allocator import BudgetAllocator
        allocator = BudgetAllocator()
        allocated = await allocator.allocate(blocks, token_budget)
        
        return allocated
    
    def _build_system_prompt(self, decision: Any) -> str:
        """Prompt de sistema."""
        intent = decision.category.value
        return f"""Você é um analista de negócios.
Análise solicitada: {intent}
Dados disponíveis: dados reais + contexto histórico
Abordagem: sintetize os dados, compare com histórico, recomende ações.
Responda em português, seja conciso e acionável."""
    
    def _build_memory_block(self, unified: UnifiedDataOutput) -> str:
        """Memory: histórico + contexto."""
        return json.dumps({
            "source": "memory_curta",
            "category": unified.memory_category,
            "insights": unified.memory_insights,
            "key_metrics": unified.memory_metrics,
            "note": "Contexto histórico do usuário"
        }, default=str, ensure_ascii=False, indent=2)
    
    def _build_data_block(self, unified: UnifiedDataOutput) -> str:
        """Data: resultado da query + processamento."""
        return json.dumps({
            "source": "mysql_analytics",
            "sql_executed": unified.sql_executed,
            "metadata": {
                "rows_returned": unified.rows_count,
                "schema": unified.schema
            },
            "summary": unified.summary,
            "insights": unified.insights_from_data,
            "sample": unified.sample,
            "combined_insights": unified.combined_insights,
            "recommended_focus": unified.recommended_focus
        }, default=str, ensure_ascii=False, indent=2)
```

---

## 🔧 COMPONENTE 5: UnifiedOrchestrator

### Arquivo

```
src/orion_mcp_v3/runtime/orchestrator.py
```

### Código

```python
"""
UnifiedOrchestrator: Coordena TUDO num turno.

Fluxo:
1. Decision (qual query?)
2. Analytics (executar em paralelo com Memory)
3. Merge
4. Context Builder
5. Return blocos prontos
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from orion_mcp_v3.decision.decision_engine import DecisionEngine, QueryCategory
from orion_mcp_v3.broker.executor import AnalyticsExecutor
from orion_mcp_v3.broker.data_pipeline import DataPipeline
from orion_mcp_v3.broker.unifier import AnalyticsMemoryUnifier, UnifiedDataOutput
from orion_mcp_v3.memory.retriever import MemoryRetriever
from orion_mcp_v3.runtime.unified_context_builder import UnifiedContextBuilder
from orion_mcp_v3.contracts.context_block import ContextBlock


@dataclass
class OrchestrationResult:
    """Resultado de um turno completo."""
    context_blocks: list[ContextBlock]
    unified_data: UnifiedDataOutput
    decision_result: Any
    sql_executed: str | None
    memory_used: bool


class UnifiedOrchestrator:
    """
    Orquestra um turno COMPLETO:
    Query → Decision → [Analytics + Memory] → Merge → Context → Blocos
    """
    
    def __init__(
        self,
        mysql_client,
        postgres_client,
        redis_client,
        allowlist
    ):
        self.decision_engine = DecisionEngine()
        self.analytics_executor = AnalyticsExecutor(mysql_client, allowlist)
        self.data_pipeline = DataPipeline()
        self.memory_retriever = MemoryRetriever(redis_client, postgres_client)
        self.unifier = AnalyticsMemoryUnifier()
        self.context_builder = UnifiedContextBuilder()
    
    async def process_turn(
        self,
        user_query: str,
        user_id: str,
        previous_intent: str | None = None,
        token_budget: int = 4000
    ) -> OrchestrationResult:
        """
        Turno COMPLETO:
        1. Decidir qual query
        2. Executar Analytics EM PARALELO com Memory
        3. Merge
        4. Context Builder
        5. Retornar blocos
        """
        
        # Step 1: Decision
        decision = self.decision_engine.decide(
            user_query,
            previous_intent=previous_intent
        )
        
        # Step 2: Paralelo
        analytics_task = None
        memory_task = None
        
        # Analytics (se houver query)
        if decision.query_id:
            analytics_task = self._run_analytics(decision.query_id)
        
        # Memory (sempre, se usar_memory=True)
        if decision.use_memory:
            memory_task = self._run_memory(
                user_id,
                decision.category.value
            )
        
        # Aguardar ambos
        analytics_result = None
        pipeline_output = None
        memory_result = None
        
        if analytics_task or memory_task:
            results = await asyncio.gather(
                analytics_task if analytics_task else asyncio.sleep(0),
                memory_task if memory_task else asyncio.sleep(0),
                return_exceptions=True
            )
            
            if analytics_task:
                analytics_result, pipeline_output = results[0]
            if memory_task:
                memory_result = results[1]
        
        # Step 3: Merge
        if analytics_result and pipeline_output:
            unified_data = await self.unifier.unify(
                analytics_result,
                pipeline_output,
                memory_result
            )
        elif memory_result:
            # Só memory, sem analytics
            unified_data = UnifiedDataOutput(
                sql_executed=None,
                rows_count=0,
                schema={},
                summary={},
                sample=[],
                insights_from_data=[],
                memory_category=memory_result.category,
                memory_insights=memory_result.recent_insights,
                memory_metrics=memory_result.key_metrics,
                combined_insights=memory_result.recent_insights,
                recommended_focus=None
            )
        else:
            # Nenhum dado
            unified_data = UnifiedDataOutput(
                sql_executed=None,
                rows_count=0,
                schema={},
                summary={},
                sample=[],
                insights_from_data=[],
                memory_category=None,
                memory_insights=[],
                memory_metrics={},
                combined_insights=[],
                recommended_focus=None
            )
        
        # Step 4: Context Builder
        context_blocks = await self.context_builder.build(
            user_query,
            unified_data,
            decision,
            user_id=user_id,
            token_budget=token_budget
        )
        
        # Step 5: Return
        return OrchestrationResult(
            context_blocks=context_blocks,
            unified_data=unified_data,
            decision_result=decision,
            sql_executed=analytics_result.sql if analytics_result else None,
            memory_used=bool(memory_result)
        )
    
    async def _run_analytics(self, query_id: str) -> tuple:
        """Executa analytics (pode falhar, tudo bem)."""
        try:
            result = await self.analytics_executor.execute(
                query_text=f"query:{query_id}",  # Sinal especial para executor
                intent_slug=query_id
            )
            pipeline_output = await self.data_pipeline.process(result)
            return result, pipeline_output
        except Exception as e:
            print(f"⚠️ Analytics failed: {e}")
            return None, None
    
    async def _run_memory(self, user_id: str, category: str):
        """Recupera memory (pode falhar, tudo bem)."""
        try:
            result = await self.memory_retriever.retrieve(
                user_id,
                category,
                query_text=""  # dummy
            )
            return result
        except Exception as e:
            print(f"⚠️ Memory retrieval failed: {e}")
            return None
```

---

## 📊 FLUXO VISUAL COMPLETO

```
User: "qual é o ticket médio dos últimos 3 meses?"
                        ↓
        ┌───────────────────────────────────┐
        │ 1. Decision Engine                │
        │    "ticket médio" → FATURAMENTO   │
        │    query_id = "ticket_medio"      │
        └───────────┬───────────────────────┘
                    ↓
        ┌─────────────────────────────────────────┐
        │ 2. Execução Paralela                    │
        ├─────────────────────────────────────────┤
        │ Task A: Analytics                       │
        │ ├─ AnalyticsExecutor.execute()         │
        │ │  (query_id → SQL → MySQL)             │
        │ ├─ DataPipeline.process()               │
        │ │  (rows → schema + summary + sample)   │
        │ └─ Result: {sql, rows, schema, ...}    │
        │                                         │
        │ Task B: Memory                          │
        │ ├─ MemoryRetriever.retrieve()           │
        │ │  (user_id + FATURAMENTO → Redis/PG)  │
        │ └─ Result: {insights, metrics}          │
        └─────────────────────────────────────────┘
                    ↓
        ┌───────────────────────────────┐
        │ 3. AnalyticsMemoryUnifier     │
        │    Merge Analytics + Memory   │
        │    Resultado: UnifiedDataOutput│
        └─────────────────────────────────┘
                    ↓
        ┌─────────────────────────────────────────┐
        │ 4. UnifiedContextBuilder                │
        │    Monta blocos na ordem:               │
        │    1. SYSTEM (instruções)               │
        │    2. MEMORY (contexto histórico)       │
        │    3. DATA (dados reais + insights)     │
        │    4. USER (pergunta)                   │
        └─────────────────────────────────────────┘
                    ↓
        ┌───────────────────────────────┐
        │ 5. BudgetAllocator            │
        │    Aloca tokens respeitando:  │
        │    - Reserva: SYSTEM          │
        │    - Prioridade: DATA > MEMORY│
        │    - Resultado: blocos < 4000 │
        └───────────────────────────────┘
                    ↓
        Return: [SYSTEM, MEMORY, DATA, USER]
                    ↓
        → FastAPI endpoint /chat
        → LLM recebe prompt estruturado
        → Resposta: "Ticket médio foi R$ 1.450..."
```

---

## 🎯 DECISÃO: Qual Query?

O **AnalyticsExecutor** precisa de uma ligeira modificação para aceitar `query_id`:

```python
# Em broker/executor.py

async def execute(
    self,
    query_text: str | None = None,
    query_id: str | None = None,  # ⭐ NOVO
    ...
) -> AnalyticsResult:
    """
    Dois modos:
    A) query_text: "últimos 3 meses" (Planner + Compiler)
    B) query_id: "ticket_medio" (direto do config)
    """
    
    if query_id:
        # Modo B: Usar query pré-definida
        sql = self._get_query_sql(query_id)
        rows = await self.mysql_client.select(sql)
        return AnalyticsResult(
            plan=SemanticQueryPlan(
                intent_slug=query_id,
                strategy=RetrievalStrategy.BROKER_FANOUT,
                target_collections=(),
                hints={}
            ),
            sql=sql,
            rows=rows,
            row_count=len(rows)
        )
    
    elif query_text:
        # Modo A: Planner + Compiler (original)
        plan = plan_from_natural_language(query_text, ...)
        compiled = compile_select(plan, self.allowlist)
        rows = await self.mysql_client.select(compiled.sql)
        return AnalyticsResult(...)
    
    else:
        raise ValueError("Precisa query_text ou query_id")

def _get_query_sql(self, query_id: str) -> str:
    """
    Retorna SQL pré-definida para query_id.
    
    Queries devem estar em config/predefined_queries.py
    """
    from orion_mcp_v3.config.predefined_queries import QUERIES
    return QUERIES[query_id]
```

---

## ✅ CHECKLIST: IMPLEMENTAR TUDO

### Fase: Decision + Memory + Unified

- [ ] **decision/decision_engine.py** (30 min)
- [ ] **memory/retriever.py** (20 min)
- [ ] **broker/unifier.py** (20 min)
- [ ] **runtime/unified_context_builder.py** (30 min)
- [ ] **runtime/orchestrator.py** (40 min)
- [ ] **config/predefined_queries.py** (criar queries-id)
- [ ] **Modificar broker/executor.py** (adicionar query_id mode)
- [ ] **Testes integrados** (40 min)

**Total**: ~3-4 horas

---

## 🚀 COMO COMEÇAR

### Passo 1: Definir Queries Pré-definidas

```python
# src/orion_mcp_v3/config/predefined_queries.py

QUERIES = {
    "ticket_medio": """
        SELECT 
            DATE_TRUNC('month', data_venda) AS mes,
            AVG(valor) AS ticket_medio,
            COUNT(*) AS qtd_vendas
        FROM vendas
        WHERE data_venda >= DATE_SUB(NOW(), INTERVAL 3 MONTH)
        GROUP BY DATE_TRUNC('month', data_venda)
        ORDER BY mes DESC
    """,
    
    "taxa_retrabalho": """
        SELECT 
            DATE_TRUNC('month', data_criacao) AS mes,
            SUM(CASE WHEN reaberta THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS taxa_retrabalho,
            COUNT(*) AS total_os
        FROM os
        WHERE data_criacao >= DATE_SUB(NOW(), INTERVAL 3 MONTH)
        GROUP BY DATE_TRUNC('month', data_criacao)
        ORDER BY mes DESC
    """,
    
    # ... mais queries
}
```

### Passo 2: Criar Decision Engine

Copie `decision/decision_engine.py` do código acima.

### Passo 3: Criar Unified Orchestrator

Integre os 5 componentes.

### Passo 4: FastAPI

```python
# src/orion_mcp_v3/routes/chat.py

@app.post("/api/v1/chat")
async def chat(request: ChatRequest):
    orchestrator = UnifiedOrchestrator(
        mysql_client,
        postgres_client,
        redis_client,
        allowlist
    )
    
    result = await orchestrator.process_turn(
        user_query=request.message,
        user_id=request.user_id,
        previous_intent=request.previous_intent
    )
    
    # LLM recebe blocos
    prompt = build_prompt_from_blocks(result.context_blocks)
    reply = await llm.complete(prompt)
    
    return {
        "reply": reply,
        "metadata": {
            "decision": result.decision_result.category.value,
            "sql_executed": result.sql_executed,
            "memory_used": result.memory_used
        }
    }
```

---

## 📊 RESULTADO FINAL

**Antes**: Dois caminhos separados, sem orquestração.  
**Depois**: Um sistema unificado que:

✅ Decide qual query executar  
✅ Busca memory relevante em paralelo  
✅ Mescla dados reais + contexto histórico  
✅ Monta contexto na ordem correta  
✅ Aloca tokens inteligentemente  
✅ Tudo determinístico + auditável  

**User gets**: Resposta baseada em dados REAIS + memória CONSOLIDADA
