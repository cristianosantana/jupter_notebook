# 📋 PLANO DESCRITIVO: Orion MCP v2

**Status**: Pronto para Implementação  
**Data**: 30 de Março de 2026  
**Escopo**: Maestro de Agentes → Orion MCP v2 (Produção)  
**Arquitetura**: Data-Driven + Decision Determinístico + Memory Warming Automático

---

## 🎯 VISÃO GERAL

```
Fórmula: Sistema = Estado Persistido + Decision Engine + Data Pipeline + LLM Renderer + Memory Warming
```

### **Que Problema Resolve?**

| Problema | Solução Orion MCP v2 |
|----------|-------------------|
| ❌ Dados brutos → LLM (inseguro, caro) | ✅ Data Pipeline: summary + insights |
| ❌ LLM governa decisão (impredizível) | ✅ Decision Engine determinístico |
| ❌ Estado em memória (perde ao restart) | ✅ Estado em PostgreSQL (persistido) |
| ❌ Cache sempre miss (lento) | ✅ Memory Warming noturno (cache pronto) |
| ❌ Intenção não identificada | ✅ SessionIntentAnalyzer (categoriza) |
| ❌ Sem histórico de contexto | ✅ Memory Curta no Redis (30 dias) |

---

## 📂 ESTRUTURA DE ARQUIVOS (FINALIZADA)

```
orion_mcp_v2/
├── .env                                    ← Variáveis de ambiente
├── .env.example                            ← Template
├── requirements.txt                        ← Dependencies
├── pyproject.toml                          ← Project metadata
├── docker-compose.yml                      ← Dev stack (PostgreSQL, Redis, MySQL mock)
│
├── run_server.py                           ← Entry point (uvicorn)
├── run_celery_worker.py                    ← Entry point (Celery worker)
│
├── src/orion_mcp/
│   ├── __init__.py
│   ├── main.py                             ← FastAPI app
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py                     ← Pydantic Settings (todas as vars)
│   │
│   ├── route/                              ← API REST Layer
│   │   ├── __init__.py
│   │   ├── dependencies.py                 ← get_current_user, etc.
│   │   └── chat.py                         ← POST /api/v1/chat, /api/v1/chat/stream
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── orchestrator/                   ← Orquestra turno (state → decision → action)
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py             ← Main: run_turn(session_id, message)
│   │   │   ├── action_executor.py          ← Executa ação (fetch data, call LLM)
│   │   │   └── state_manager.py            ← Load/save state do PostgreSQL
│   │   │
│   │   ├── decision/                       ← Decide ação (não LLM!)
│   │   │   ├── __init__.py
│   │   │   ├── engine.py                   ← DecisionEngine: decide_action()
│   │   │   ├── strategy.py                 ← Estratégias de decisão (regex, heurística)
│   │   │   └── intent_classifier.py        ← Classificar intenção (categoria)
│   │   │
│   │   ├── data_engine/                    ← Data Pipeline
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py                 ← run_pipeline(rows) → {summary, insights, sample}
│   │   │   ├── summary.py                  ← build_summary(rows) → agregado
│   │   │   ├── sampler.py                  ← sample_rows(rows, limit=5)
│   │   │   ├── schema.py                   ← infer_schema(rows)
│   │   │   └── insights.py                 ← extract_insights(rows) → determinístico
│   │   │
│   │   ├── context/                        ← Montar contexto para LLM
│   │   │   ├── __init__.py
│   │   │   ├── builder.py                  ← ContextBuilder: build(question, data, memory)
│   │   │   ├── formatter.py                ← Formatar JSON respeitando budget
│   │   │   └── budget.py                   ← TokenBudget: controlar tokens
│   │   │
│   │   ├── strategy.py                     ← Strategy pattern (como Orion)
│   │   └── exceptions.py                   ← Custom exceptions
│   │
│   ├── skill/                              ← Skills (instruções + contexto)
│   │   ├── __init__.py
│   │   ├── loader.py                       ← SkillLoader: load YAML → Skill object
│   │   ├── registry.py                     ← SkillRegistry: cache em memória
│   │   ├── models.py                       ← Pydantic Skill, SkillModel
│   │   ├── router.py                       ← ⭐ Decision Engine (SKILL ROUTING)
│   │   └── skills/                         ← Skills em YAML
│   │       ├── faturamento_analyzer.yaml
│   │       ├── qualidade_analyzer.yaml
│   │       ├── performance_analyzer.yaml
│   │       ├── session_intent_analyzer.yaml ← ⭐ Novo (categorizar intenções)
│   │       └── memory_consolidator.yaml    ← ⭐ Novo (consolidar sessões)
│   │
│   ├── llm_provider/                       ← LLM Layer
│   │   ├── __init__.py
│   │   ├── base.py                         ← BaseLLMProvider (abstração)
│   │   ├── openai_provider.py              ← OpenAI implementation
│   │   ├── model_config.py                 ← Model configs, token limits
│   │   └── client.py                       ← LLM client wrapper
│   │
│   ├── state/                              ← Estado de sessão
│   │   ├── __init__.py
│   │   ├── models.py                       ← Pydantic: ConversationState, Message
│   │   ├── repository.py                   ← StateRepository: load/save/delete
│   │   ├── transitions.py                  ← State transitions (se usar máquina estados)
│   │   └── types.py                        ← Enums: MessageRole, StateStatus
│   │
│   ├── db/                                 ← Database Layer
│   │   ├── __init__.py
│   │   ├── config.py                       ← DB configs, pools
│   │   ├── mysql/
│   │   │   ├── __init__.py
│   │   │   ├── pool.py                     ← MySQLPool: connection pooling
│   │   │   ├── query_executor.py           ← Executar queries
│   │   │   ├── query_catalog.py            ← Carregar queries SQL
│   │   │   └── queries/                    ← 30 queries em arquivos
│   │   │       ├── ticket_medio.sql
│   │   │       ├── retrabalho.sql
│   │   │       └── ...
│   │   └── postgres/
│   │       ├── __init__.py
│   │       ├── pool.py                     ← PostgresPool: connection pooling
│   │       ├── migrations/
│   │       │   ├── 001_conversation_state.sql
│   │       │   ├── 002_memory_curta.sql    ← ⭐ Novo (guardar memory)
│   │       │   └── 003_memory_analytics.sql ← ⭐ Novo (analytics)
│   │       └── schema.py                   ← SQLAlchemy ORM models
│   │
│   ├── cache/                              ← Redis Cache
│   │   ├── __init__.py
│   │   ├── redis_client.py                 ← RedisClient: wrapper
│   │   ├── keys.py                         ← Key patterns
│   │   └── serializer.py                   ← JSON serialization
│   │
│   ├── memory/                             ← Memory Warming + Consolidation
│   │   ├── __init__.py
│   │   ├── consolidator.py                 ← MemoryConsolidator: consolidate_user()
│   │   ├── summarizer.py                   ← Summarizer: summarize_sessions()
│   │   ├── categorizer.py                  ← ⭐ IntentCategorizer (categorizar sessões)
│   │   ├── memory_builder.py               ← MemoryBuilder: build_memory_curta()
│   │   └── models.py                       ← Pydantic: MemoryCurta, Intent
│   │
│   ├── tasks/                              ← Celery Tasks
│   │   ├── __init__.py
│   │   ├── consolidate_memory.py           ← @celery.task: consolidate_memory_for_user()
│   │   └── tasks_config.py                 ← Task retries, routing
│   │
│   ├── scheduler/                          ← Job Scheduling (Celery Beat)
│   │   ├── __init__.py
│   │   └── jobs.py                         ← CeleryBeat: schedular 03:00 AM
│   │
│   ├── common/                             ← Utilidades
│   │   ├── __init__.py
│   │   ├── logger.py                       ← Logger estruturado (JSON)
│   │   ├── exceptions.py                   ← Custom exceptions
│   │   ├── types.py                        ← Type hints comuns
│   │   ├── utils.py                        ← Funções auxiliares
│   │   └── constants.py                    ← Constantes
│   │
│   └── observability/
│       ├── __init__.py
│       ├── metrics.py                      ← Prometheus metrics
│       ├── tracing.py                      ← Distributed tracing (opcional)
│       └── health.py                       ← Health check endpoints
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                         ← Pytest fixtures
│   ├── test_orchestrator.py
│   ├── test_decision_engine.py
│   ├── test_data_pipeline.py
│   ├── test_memory_consolidation.py
│   └── ...
│
├── docs/
│   ├── ARCHITECTURE.md                     ← Arquitetura completa
│   ├── API.md                              ← Endpoints HTTP
│   ├── MEMORY_WARMING.md                   ← Cache warming detalhado
│   ├── DECISION_FLOW.md                    ← Decisões + fluxos
│   └── TROUBLESHOOTING.md                  ← FAQ + debugging
│
├── scripts/
│   ├── init_db.py                          ← Criar tabelas PostgreSQL
│   ├── load_queries.py                     ← Carregar queries MySQL
│   ├── test_consolidation.py               ← Testar cache warming manualmente
│   └── cleanup.py                          ← Limpar dados antigos
│
└── docker/
    ├── docker-compose.yml                  ← Prod stack
    ├── app/Dockerfile
    └── postgres/init.sql
```

---

## 🔧 RESPONSABILIDADE POR MÓDULO

| Módulo | Responsabilidade |
|--------|------------------|
| **route/chat.py** | Receber request HTTP, validar, delegar a orchestrator |
| **orchestrator.py** | Orquestrar turno: load state → decide → execute → save |
| **decision/engine.py** | Decidir ação (query_id, params) com heurística |
| **decision/router.py (SKILL)** | Determinar qual skill usar baseado em intenção |
| **data_engine/pipeline.py** | Processar dados: summary + insights + sample |
| **context/builder.py** | Montar JSON/prompt com orçamento de tokens |
| **llm_provider/openai_provider.py** | Chamar OpenAI API, receber resposta |
| **state/repository.py** | Load/save conversation_state em PostgreSQL |
| **db/mysql/query_executor.py** | Executar query MySQL, retornar rows |
| **cache/redis_client.py** | Get/set/delete no Redis |
| **memory/consolidator.py** | Consolidar sessões antigas em memory curta |
| **memory/categorizer.py** | Categorizar sessões por INTENÇÃO |
| **tasks/consolidate_memory.py** | Celery task: rodiar consolidação |
| **scheduler/jobs.py** | Agendar consolidação para 03:00 AM |

---

## 🔄 FLUXO: TURNO DIURNO (User → Response)

```
1. [HTTP POST /api/v1/chat]
   user: "qual ticket médio?"
   session_id: "sess-xxx"
   
2. [route/chat.py → orchestrator.run_turn()]
   Input: session_id, message
   
3. [orchestrator.state_manager.load()]
   ├─ Load conversation_state de PostgreSQL
   └─ Output: {messages, last_data, user_id, ...}
   
4. [decision/engine.decide_action()]
   ├─ Input: message, state
   ├─ Heurística: "ticket" → intent = FATURAMENTO
   ├─ Skill Router: intent → skill_id = "faturamento_analyzer"
   ├─ Determinar query_id = "ticket_medio_conc"
   └─ Output: Action(type="query", query_id, params, skill_id)
   
5. [action_executor.execute_action()]
   ├─ [db/mysql/query_executor.execute(query_id, params)]
   │  └─ Retorna: rows (lista de dicts)
   │
   ├─ [data_engine/pipeline.run(rows)]
   │  ├─ summary = build_summary(rows)
   │  ├─ insights = extract_insights(rows)
   │  ├─ sample = sample_rows(rows, limit=5)
   │  └─ Retorna: {summary, insights, sample, row_count}
   │
   └─ Output: data_output
   
6. [cache/redis_client.get(memory_curta)]
   ├─ key = f"memory:{user_id}:{category}:latest"
   └─ Output: memory_curta (ou None)
   
7. [context/builder.build()]
   ├─ Input: question, data_output, memory_curta, state
   ├─ Montar JSON com:
   │  ├─ question
   │  ├─ user_memory (se existe)
   │  ├─ current_data (summary + insights)
   │  ├─ sample (primeiras 5 linhas)
   │  └─ context (session, últimas perguntas)
   ├─ Respeitar TOKEN_BUDGET
   └─ Output: context (structured dict)
   
8. [llm_provider/openai_provider.call()]
   ├─ Input: context (JSON estruturado)
   ├─ Skill: carregar skill ("faturamento_analyzer")
   ├─ System prompt: skill.template com placeholders
   ├─ User prompt: context JSON
   ├─ Call OpenAI API
   └─ Output: response (string)
   
9. [orchestrator.update_state()]
   ├─ Novo message: {role: "user", content: question}
   ├─ Novo message: {role: "assistant", content: response}
   ├─ Atualizar last_data, last_query_signature
   └─ Save to PostgreSQL
   
10. [route/chat.py → return response]
    └─ JSON: {reply, session_id, metadata}
```

---

## 🌙 FLUXO: CACHE WARMING (03:00 AM - Noturno)

```
TRIGGER: Celery Beat (03:00 AM UTC)
  ↓
[scheduler/jobs.py → consolidate_memory_task.apply_async()]
  │ Para cada user (conc_001 ... conc_060):
  │
  ├─ [tasks/consolidate_memory.py → consolidate_memory_for_user(user_id)]
  │  (Task Celery)
  │
  ├─ Step 1: Load Sessions (últimos 30 dias)
  │  └─ [db/postgres → SELECT * FROM conversation_state WHERE user_id=... AND created_at > NOW()-30days]
  │     Output: sessions = [sess1, sess2, ...]
  │
  ├─ Step 2: Categorize by Intent
  │  ├─ [memory/categorizer.categorize_sessions(sessions)]
  │  │  Para cada sessão:
  │  │  ├─ Extract mensagens user
  │  │  ├─ Call skill "session_intent_analyzer"
  │  │  ├─ LLM categoriza: FATURAMENTO, QUALIDADE, PERFORMANCE, ...
  │  │  └─ Output: {session_id, intents=[...]}
  │  │
  │  └─ Group by intent:
  │     intents_grouped = {
  │       FATURAMENTO: [sess1, sess2, ...],
  │       QUALIDADE: [sess3, sess4, ...],
  │       ...
  │     }
  │
  ├─ Step 3: Consolidate per Intent
  │  └─ Para cada intent category:
  │     ├─ [memory/summarizer.summarize_sessions(sessions_group)]
  │     │  ├─ Extrair todas perguntas/respostas
  │     │  ├─ Call skill "memory_consolidator"
  │     │  ├─ LLM resume: "Top insights de FATURAMENTO últimos 30 dias"
  │     │  └─ Output: consolidated_summary
  │     │
  │     ├─ [memory/memory_builder.build_memory_curta()]
  │     │  ├─ Estrutura:
  │     │  │  {
  │     │  │    "user_id": "conc_001",
  │     │  │    "category": "FATURAMENTO",
  │     │  │    "consolidated_at": "2026-03-30T03:00:00Z",
  │     │  │    "summary": consolidated_summary,
  │     │  │    "key_metrics": {
  │     │  │      "ticket_medio": 1450,
  │     │  │      "faturamento_total": 210250,
  │     │  │      "top_servico": "Cerâmica"
  │     │  │    },
  │     │  │    "recent_questions": [
  │     │  │      "qual ticket médio?",
  │     │  │      "qual top serviço?"
  │     │  │    ],
  │     │  │    "last_results": {
  │     │  │      "query_id": "ticket_medio_conc",
  │     │  │      "data_summary": {...},
  │     │  │      "timestamp": "2026-03-29T18:30:00Z"
  │     │  │    }
  │     │  │  }
  │     │  └─ Output: memory_curta (dict)
  │     │
  │     └─ [cache/redis_client.hset()]
  │        key = f"memory:{user_id}"
  │        field = category (FATURAMENTO, QUALIDADE, ...)
  │        value = JSON(memory_curta)
  │        TTL = 7 days
  │
  ├─ Step 4: Cleanup Old Sessions
  │  ├─ [db/postgres → DELETE FROM conversation_state WHERE user_id=... AND created_at < NOW()-30days]
  │  └─ Log: "Deleted X old sessions"
  │
  └─ On Error (Retry):
     ├─ Try 1: fail → retry after 5min
     ├─ Try 2: fail → retry after 15min
     ├─ Try 3: fail → log to dead_letter_queue
     └─ Admin notificado
     
END: 06:00 AM
  └─ Todos 50-60 users têm memory curta pronta em Redis ✅
```

---

## 📊 ESTRUTURA POSTGRESQL (Estado)

```sql
-- Tabela 1: Conversation State
CREATE TABLE conversation_state (
    session_id UUID PRIMARY KEY,
    user_id VARCHAR(20) NOT NULL,
    messages JSONB NOT NULL,  -- Array de messages
    last_data JSONB,          -- Último resultado (summary)
    last_query_signature VARCHAR(255),
    state_status VARCHAR(20), -- active, completed, archived
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
);

-- Tabela 2: Memory Curta Analytics (Backup)
CREATE TABLE memory_curta_analytics (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(20) NOT NULL,
    category VARCHAR(50) NOT NULL,  -- FATURAMENTO, QUALIDADE, ...
    summary JSONB NOT NULL,         -- Memory consolidada
    consolidated_at TIMESTAMP,
    ttl_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    INDEX idx_user_id_category (user_id, category),
    INDEX idx_expires_at (ttl_expires_at)
);

-- Tabela 3: Memory Warming Job Log
CREATE TABLE memory_consolidation_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(20) NOT NULL,
    job_id VARCHAR(100),        -- Celery task ID
    status VARCHAR(20),         -- success, failed, retrying
    error_message TEXT,
    sessions_processed INT,
    consolidated_at TIMESTAMP,
    next_retry_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_user_id (user_id),
    INDEX idx_status (status)
);
```

---

## 🔴 ESTRUTURA REDIS (Memory Curta)

```
# Hash Redis (mais eficiente)
HGETALL memory:conc_001

field1: "FATURAMENTO" → value (JSON)
{
  "user_id": "conc_001",
  "category": "FATURAMENTO",
  "consolidated_at": "2026-03-30T03:00:00Z",
  "summary": "Faturamento MoM +12%, Cerâmica lidera com 35%...",
  "key_metrics": {
    "ticket_medio": 1450,
    "faturamento_total": 210250,
    "top_servico": "Cerâmica"
  },
  "recent_questions": [
    "qual ticket médio?",
    "qual top serviço?"
  ],
  "last_results": {
    "query_id": "ticket_medio_conc",
    "data_summary": {...},
    "timestamp": "2026-03-29T18:30:00Z"
  }
}

field2: "QUALIDADE" → value (JSON)
{...}

field3: "PERFORMANCE" → value (JSON)
{...}

TTL: 7 days (EXPIRE memory:conc_001 604800)
```

---

## 🎬 SKILLS EM YAML

### **1. faturamento_analyzer.yaml**
```yaml
name: faturamento_analyzer
model: gpt-5-mini
max_tokens: 500
temperature: 0.5

system_prompt: |
  Você é um analisador de faturamento especializado em concessionárias.
  Interprete os dados apresentados e forneça insights sobre:
  - Evolução de faturamento
  - Mix de serviços
  - Ticket médio
  - Margens
  
  Dados: {data_summary}
  Insights: {insights}
  Amostra: {sample}
  
  Responda a pergunta: {question}
```

### **2. session_intent_analyzer.yaml** (⭐ NOVO)
```yaml
name: session_intent_analyzer
model: gpt-5-mini
max_tokens: 200
temperature: 0.3

system_prompt: |
  Você categoriza intenções de conversa em categorias de negócio.
  
  Categorias válidas:
  - FATURAMENTO (ticket, receita, margem, serviços)
  - QUALIDADE (retrabalho, taxa, defeitos)
  - PERFORMANCE (vendedores, metas, ranking)
  - OPERACIONAL (processos, eficiência)
  - ESTRATEGICO (planejamento, cenários)
  
  Análise a conversa e retorne JSON:
  {
    "primary_intent": "FATURAMENTO",
    "secondary_intents": ["PERFORMANCE"],
    "confidence": 0.95
  }
  
  Conversa: {conversation_text}
```

### **3. memory_consolidator.yaml** (⭐ NOVO)
```yaml
name: memory_consolidator
model: gpt-5-mini
max_tokens: 300
temperature: 0.4

system_prompt: |
  Você consolida sessões de conversa em uma memória curta para rápido contexto.
  
  Extraia:
  1. Top 3-5 insights principais
  2. Métricas-chave mencionadas
  3. Perguntas mais frequentes
  4. Padrões de comportamento
  
  Retorne JSON estruturado, conciso, sem dados redundantes.
  
  Sessões: {sessions_json}
```

---

## ⚙️ ARQUIVOS .env

```bash
# ===== APP =====
APP_NAME=orion_mcp_v2
APP_ENV=development|production
DEBUG=false
LOG_LEVEL=INFO

# ===== DATABASE: PostgreSQL =====
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=orion
POSTGRES_PASSWORD=secret123
POSTGRES_DATABASE=orion_mcp

# ===== DATABASE: MySQL =====
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=analytics
MYSQL_PASSWORD=secret456
MYSQL_DATABASE=dealership

# ===== REDIS =====
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# ===== LLM =====
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-mini
OPENAI_MAX_TOKENS=4000

# ===== CELERY =====
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2
CELERY_TIMEZONE=UTC

# ===== MEMORY WARMING =====
CONSOLIDATION_HOUR=3
CONSOLIDATION_MINUTE=0
CONSOLIDATION_BATCH_SIZE=5
MEMORY_CURTA_TTL_DAYS=7

# ===== LOGGING =====
LOG_FORMAT=json
LOG_OUTPUT=stdout|file
LOG_FILE_PATH=/var/log/orion_mcp.log
```

---

## 🧪 RESPONSABILIDADE ÚNICA POR ARQUIVO

| Arquivo | Função | Linhas Max |
|---------|--------|-----------|
| settings.py | Load env vars via Pydantic | 100 |
| chat.py | HTTP handler (request → orchestrator) | 80 |
| orchestrator.py | Orquestra turno (load → decide → execute) | 120 |
| engine.py (decision) | Decide ação baseado em message + state | 100 |
| router.py (skill) | Roteia para skill baseado em intenção | 80 |
| pipeline.py (data) | Run pipeline (summary + insights + sample) | 150 |
| builder.py (context) | Montar contexto respeitando budget | 120 |
| openai_provider.py | Call OpenAI API | 100 |
| repository.py (state) | Load/save state PostgreSQL | 120 |
| query_executor.py (mysql) | Execute query, retorna rows | 100 |
| redis_client.py | Get/set/delete Redis | 100 |
| consolidator.py (memory) | Consolidar sessões antigas | 150 |
| categorizer.py | Categorizar sessões por intent | 120 |
| consolidate_memory.py (task) | Celery task wrapper | 80 |
| jobs.py (scheduler) | Agendar consolidação | 60 |

---

## 📈 FLUXO DECISÃO (Decision Engine)

```
Message: "qual ticket médio?"
  ↓
[Heurística Regex]
  ├─ "ticket|valor.*medio|receita" → intent = FATURAMENTO
  ├─ "retrabalho|reaberta|defeito" → intent = QUALIDADE
  ├─ "vendedor|ranking|meta|performance" → intent = PERFORMANCE
  └─ Else → intent = OPERACIONAL
  ↓
[Skill Router]
  intent FATURAMENTO → skill_id = "faturamento_analyzer"
  intent QUALIDADE → skill_id = "qualidade_analyzer"
  intent PERFORMANCE → skill_id = "performance_analyzer"
  ↓
[Query Mapping]
  intent FATURAMENTO + "ticket" → query_id = "ticket_medio_conc"
  intent FATURAMENTO + "top" → query_id = "faturamento_servico"
  intent QUALIDADE → query_id = "taxa_retrabalho"
  intent PERFORMANCE → query_id = "performance_vendedor"
  ↓
[Action]
  {type: "query", query_id, params, skill_id}
```

---

## ✅ CHECKLIST DE IMPLEMENTAÇÃO (4-6 Semanas)

### **SEMANA 1: Setup + Infraestrutura**

- [ ] Criar estrutura de pastas (src/orion_mcp/*)
- [ ] Implementar settings.py (Pydantic)
- [ ] Setup PostgreSQL + migrations
- [ ] Setup Redis + key patterns
- [ ] Implementar connection pools (MySQL + Postgres)
- [ ] Docker-compose.yml (dev stack)
- [ ] Logger estruturado (JSON)

**Deliverable**: `docker-compose up` → todos services rodando

---

### **SEMANA 2: Data Layer + Data Engine**

- [ ] Implementar db/mysql/query_executor.py
- [ ] Carregar 30 queries em arquivos SQL
- [ ] Implementar data_engine/pipeline.py
  - [ ] summary.py (aggregação)
  - [ ] insights.py (determinístico)
  - [ ] sampler.py (amostragem)
  - [ ] schema.py (inferência)
- [ ] Testes unitários

**Deliverable**: `pipeline = run_data_pipeline(rows)` funcional

---

### **SEMANA 3: Decision + Orchestration**

- [ ] Implementar decision/engine.py (heurística)
- [ ] Implementar skill/router.py (skill routing)
- [ ] Implementar state/repository.py (Postgres)
- [ ] Implementar orchestrator.py (main loop)
- [ ] Implementar action_executor.py
- [ ] Testes E2E turno simples

**Deliverable**: Turno completo: message → response

---

### **SEMANA 4: LLM + Context + Skills**

- [ ] Implementar llm_provider/openai_provider.py
- [ ] Implementar context/builder.py (com budget)
- [ ] Skill loader + registry
- [ ] Skills em YAML (faturamento, qualidade, performance)
- [ ] Testes com LLM real

**Deliverable**: API /chat funcional

---

### **SEMANA 5: Memory Warming**

- [ ] Implementar memory/categorizer.py (SessionIntentAnalyzer)
- [ ] Implementar memory/summarizer.py
- [ ] Implementar memory/consolidator.py
- [ ] Implementar memory/memory_builder.py
- [ ] Implementar cache/redis_client.py
- [ ] Implementar tasks/consolidate_memory.py (Celery task)
- [ ] Implementar scheduler/jobs.py (Celery Beat)

**Deliverable**: Cache warming manual testável

---

### **SEMANA 6: Testing + Docs + Deploy**

- [ ] Testes de consolidação noturna
- [ ] Testes de retry automático
- [ ] Documentação completa
- [ ] Prometheus metrics
- [ ] Health check endpoints
- [ ] Docker image + docker-compose prod

**Deliverable**: Sistema pronto para produção

---

## 🔐 SEGURANÇA

| Aspecto | Implementação |
|---------|---------------|
| **SQL Injection** | Query catalog pré-definido, params via placeholders |
| **Data Leak** | Data pipeline summariza, LLM nunca vê dados brutos |
| **User Isolation** | State sempre carregado por user_id autenticado |
| **Rate Limiting** | Redis counter por user/minuto |
| **Audit** | Todos queries logados em memory_consolidation_log |

---

## 📊 MÉTRICAS

Coletar via Prometheus:
```
- orchestrator_turn_duration_seconds (turno completo)
- data_pipeline_duration_seconds (processamento)
- llm_call_duration_seconds (chamada OpenAI)
- consolidation_job_duration_seconds
- consolidation_job_success_rate
- redis_memory_bytes
- postgres_connections_active
- mysql_query_count_total
```

---

## 🚀 DEPLOY (Docker)

```dockerfile
# Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src/ src/
CMD ["python", "run_server.py"]
```

```yaml
# docker-compose prod
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment: ["APP_ENV=production", ...]
    depends_on: [postgres, redis, mysql]
    
  celery_worker:
    build: .
    command: python run_celery_worker.py
    depends_on: [redis, postgres, mysql]
    
  celery_beat:
    build: .
    command: celery -A src.orion_mcp.tasks beat --loglevel=info
    depends_on: [redis]
    
  postgres:
    image: postgres:15
    volumes: [postgres_data:/var/lib/postgresql/data]
    
  redis:
    image: redis:7
    
  mysql:
    image: mysql:8
```

---

## 📞 PRÓXIMOS PASSOS

1. **Review este plano** com time
2. **Confirmar timeline** (4-6 semanas)
3. **Iniciar Semana 1** (setup + infra)
4. **Weekly syncs** (segunda-feira)

---

## 📚 DOCUMENTAÇÃO A GERAR

- [ ] ARCHITECTURE.md (visão geral)
- [ ] API.md (endpoints HTTP)
- [ ] MEMORY_WARMING.md (cache warming detalhado)
- [ ] DECISION_FLOW.md (como funciona decision engine)
- [ ] TROUBLESHOOTING.md (FAQ + debugging)
- [ ] SKILL_DEVELOPMENT.md (como criar novo skill)
- [ ] DEPLOYMENT.md (como fazer deploy)

---

**Pronto para começar?** 🚀

Próximo passo: **Estruturar Semana 1** com detalhes técnicos (imports, estrutura exata de cada arquivo).

