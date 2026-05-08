# 🎯 SOLUÇÃO: OrionMCP V2 - Plataforma de Análise Conversacional Determinística

**Versão**: 2.0  
**Data**: 29 de Março de 2026  
**Usuários**: 50-60 Concessionárias de Serviços Automotivos (Proteção Cerâmica, Filme Solar/Insulfilm)  
**Contexto**: Evoluir de um Maestro de Agentes monolítico para uma plataforma modular, escalável e determinística

---

## 📌 PROBLEMA INICIAL

### Maestro de Agentes v1 (Monolítico)

```
❌ Problemas:
1. SKILL único genérico para tudo
2. LLM governa decisões (impredizível, caro)
3. Dados brutos → LLM (sem agregação)
4. Estado em memória (perde ao restart)
5. Sem cache de sessões
6. Sem memory curta (usuários sempre começam do zero)
7. Sem processo noturno de consolidação
```

### Impactos

- 🔴 **Custo**: $0.14 por query (40% overhead de tokens)
- 🔴 **Latência**: 2.3s (P95)
- 🔴 **Qualidade**: LLM recusa respostas ("não consigo agregar")
- 🔴 **UX**: Usuários repetem contexto a cada sessão nova

---

## ✅ SOLUÇÃO: OrionMCP V2

### Visão Geral

```
Plataforma de análise conversacional que:
1. Recebe pergunta do usuário (em linguagem natural)
2. Decide QUAL análise executar (determinístico, não LLM)
3. Busca dados do MySQL (queries pré-catalogadas)
4. AGREGA dados de forma específica por domínio (agregadores)
5. Monta contexto estruturado com dados pré-digeridos
6. Chama LLM para NARRAR (não para processar dados)
7. Persiste em PostgreSQL + Redis
8. Noturna: consolida memória por intenção para acesso rápido
```

### Arquitetura em Camadas

```
┌─────────────────────────────────────────────────────────────┐
│ INTERFACE (Route)                                           │
│ ├─ POST /api/v1/chat (HTTP REST)                          │
│ ├─ POST /api/v1/chat/stream (HTTP + SSE)                  │
│ └─ GET /health, /metrics                                   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ ORQUESTRADOR (Maestro)                                      │
│ ├─ Gerencia estado de sessão                               │
│ ├─ Coordena fluxo (não faz lógica)                         │
│ └─ Integra todos os componentes                            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ DECISÃO DETERMINÍSTICA                                      │
│ ├─ Decision Router (regex → intent → skill_id)             │
│ └─ Estratégia: heurística+regras, não LLM                  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ EXECUÇÃO DE DADOS                                           │
│ ├─ MySQL Executor (query allowlist)                        │
│ ├─ Data Pipeline (schema, summary, sample genérico)        │
│ └─ AGREGADORES ESPECÍFICOS POR SKILL ⭐                    │
│    ├─ CrossSellingAggregator (pares normalizados)          │
│    ├─ FaturamentoAggregator (mix por categoria)            │
│    ├─ PerformanceAggregator (ranking vendedores)           │
│    └─ ... (um por intenção crítica)                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ ENRIQUECIMENTO DE CONTEXTO                                  │
│ ├─ Context Builder (monta JSON com budget)                 │
│ ├─ Memory Curta (Redis, por intenção)                      │
│ └─ Skill YAML (prompts com dados pré-digeridos)           │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ LLM (OpenAI)                                                │
│ └─ Chama APENAS para narração (não toma decisões)          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PERSISTÊNCIA                                                │
│ ├─ PostgreSQL (conversas, estado)                          │
│ ├─ Redis (memory curta, cache, rate limit)                 │
│ └─ MySQL (dados analíticos)                                │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ PROCESSO NOTURNO (00:00 - 06:00)                           │
│ ├─ Celery Beat (agendador)                                 │
│ ├─ Consolidator (agrupa sessões por intenção)              │
│ ├─ Categorizer (LLM analisa: multi-intent por sessão)      │
│ ├─ Summarizer (resumo por intenção)                        │
│ └─ Memory Builder (monta + salva Redis com TTL 7d)         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ MCP SERVER (Standalone ou Integrado)                        │
│ ├─ run_analytics_query (executa query catalogada)          │
│ ├─ list_analytics_queries (catálogo)                       │
│ └─ AGREGADORES COMO TOOLS (reutilizáveis)                  │
│    ├─ aggregate_cross_selling_top_n                        │
│    ├─ aggregate_faturamento_mix                            │
│    └─ ... (tools que chamam agregadores)                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 FLUXOS PRINCIPAIS

### FLUXO DIURNO (Chat - Usuário Interagindo)

```
1. POST /api/v1/chat
   └─ {"message": "quais combos são mais lucrativos?", 
       "user_id": "conc_001"}

2. Route Validate
   └─ Valida request, rate limit (Redis)

3. Orchestrator.run_turn()
   ├─ Load SessionState (PostgreSQL)
   ├─ Ensure user identity
   └─ Proceed

4. DecisionRouter.decide()
   └─ Regex match: "combos lucrativos" → intent="FATURAMENTO"
      → skill_id="faturamento_analyzer"
      → query_id="cross_selling"

5. ActionExecutor.execute_query()
   └─ MySQL: SELECT ... FROM cross_selling WHERE ... (4425 rows)

6. ⭐ AGREGADOR ESPECÍFICO
   └─ CrossSellingAggregator.process(rows)
      ├─ Load nomes reais de serviços
      ├─ Normalizar pares (min, max)
      ├─ GROUP BY par → SUM(receita)
      ├─ TOP-10 ranking exacto
      └─ Retorna: {top_10, metadata, notas}

7. ContextBuilder.build()
   └─ Monta JSON com:
      ├─ Pergunta do usuário
      ├─ Top-10 agregado (nomes reais)
      ├─ Metadata (nota sobre sobreposição, métrica)
      ├─ Memory curta (Redis, por intenção)
      └─ Trunca para budget (4000 chars)

8. SkillLoader.load_skill()
   └─ Carrega YAML: faturamento_analyzer.yaml

9. LLM (OpenAI)
   └─ complete(
       system=skill.render_system(context),
       user="{pergunta}",
       temperature=0.3
      )

10. Finalize State
    └─ state.messages.append({user, assistant})
       state.last_intention = "FATURAMENTO"
       state.last_turn_at = NOW()

11. StateRepository.save()
    └─ Persiste em PostgreSQL

12. Response
    └─ {"reply": "[narração LLM]", 
        "session_id": "...",
        "metadata": {...}}
```

**Tempo Total**: ~2-3s (vs 2.3s antes, mas com dados CORRECTOS)

---

### FLUXO NOTURNO (Cache Warming - 03:00 AM)

```
1. Celery Beat Trigger
   └─ crontab(hour=3, minute=0)

2. Task: consolidate_memory_daily()
   └─ Para cada user_id (conc_001...conc_060)

3. MemoryConsolidator.consolidate_for_user(user_id)
   ├─ Query PostgreSQL: fetch sessões últimos 30 dias
   │  └─ 15-50 sessões por usuário

4. ⭐ Categorizer.categorize_sessions()
   └─ Para cada sessão:
      ├─ Analisa mensagens (LLM: "quais intenções?")
      ├─ Uma sessão pode ter múltiplas intenções
      ├─ Ex: ["FATURAMENTO", "QUALIDADE"]
      └─ Agrupa sessões por intenção

5. Summarizer.summarize(intention, session_list)
   └─ Para cada intenção:
      ├─ Pega todas as perguntas → respostas dessa intenção
      ├─ Extrai key insights
      ├─ Calcula key metrics
      └─ Cria pergunta→resposta resumida

6. MemoryBuilder.build()
   └─ Estrutura memory curta:
      ```json
      {
        "FATURAMENTO": {
          "recent_questions": ["qual ticket?", "top serviços?"],
          "key_insights": ["Crescimento +12%", "Cerâmica lidera"],
          "key_metrics": {"ticket": 1450, "faturamento": 210250},
          "last_results": {
            "pergunta": "qual ticket médio?",
            "resposta": "Ticket médio é R$ 1.450...",
            "resumo": "Métrica consolidada"
          }
        },
        "QUALIDADE": {...},
        ...
      }
      ```

7. Redis HSET (Hash Storage)
   └─ memory:conc_001 = HSET
      ├─ field: "FATURAMENTO" → JSON
      ├─ field: "QUALIDADE" → JSON
      └─ EX: 604800 (7 days TTL)

8. Cleanup PostgreSQL
   └─ DELETE conversation_state
      WHERE user_id = conc_001
      AND created_at < NOW() - 35 days

9. Error Handling
   └─ Se falhar:
      ├─ Celery retry 3x com backoff exponencial
      ├─ Log em memory_consolidation_log
      └─ Próximo dia tenta de novo

10. Resultado
    └─ 50-60 usuários com memory curta pronta
       Executado: 03:00 - 04:30 AM
```

---

## 🎯 COMPONENTES CHAVE

### 1. **Decision Router** (core/decision/router.py)

```python
# Entrada: pergunta do usuário
# Saída: {type, intention, skill_id, query_id}

# Heurística:
if regex_match(r"(ticket|valor.*medio)", message):
    return {"intention": "FATURAMENTO", "query_id": "ticket_medio"}
elif regex_match(r"(retrabalho|qualidade)", message):
    return {"intention": "QUALIDADE", "query_id": "taxa_retrabalho"}
elif regex_match(r"(combo|cross-sell)", message):
    return {"intention": "FATURAMENTO", "query_id": "cross_selling"}
# etc...

# Continuação (para "e o...", "e a..."):
if message.startswith("e o ") or message.startswith("e a "):
    return {"type": "memory_only", "intention": state.last_intention}
```

✅ **Por que determinístico?**
- Regras explícitas, auditáveis
- Sem chamadas LLM (rápido)
- Comportamento previsível
- Fácil de testar

---

### 2. **Agregadores por Skill** (core/aggregators/*.py)

```python
# Problema: Pipeline genérico não conhece regras de negócio

# Solução: Agregador específico por domínio
class CrossSellingAggregator:
    async def process(self, rows):
        # 1. Load nomes reais (JOIN serviços)
        servicos = await self.load_servicos()
        
        # 2. Normalizar pares (evitar (8,72) vs (72,8))
        df['par'] = df[['A_id', 'B_id']].apply(
            lambda x: (min(x), max(x)), axis=1
        )
        
        # 3. SUM(receita) por par (não por linha)
        agg = df.groupby('par')['receita'].sum()
        
        # 4. TOP-10 exacto
        top_10 = agg.nlargest(10)
        
        # 5. Contexto explicativo
        return {
            "top_10": [...],
            "metadata": {
                "total": sum(agg),
                "concentracao": top_10.sum() / sum(agg),
                "nota": "Receita com sobreposição..."
            }
        }
```

✅ **Ganhos:**
- Dados CORRECTOS (não LLM inventa)
- Nomes reais (JOIN no BD)
- Métricas exactas (SUM, não média)
- Notas contextuais (evita confusão)

---

### 3. **Memory Curta (Redis Hash)** 

```python
# Problema: Usuários repetem contexto ("já falei disso")
# Solução: Cache consolidado por intenção

# Estrutura (Redis HSET):
memory:conc_001
├─ field "FATURAMENTO" → JSON
│  {
│    "recent_questions": ["qual ticket?", "top serviços?"],
│    "key_insights": ["Crescimento +12%"],
│    "key_metrics": {"ticket": 1450},
│    "last_results": {
│      "pergunta": "qual ticket médio?",
│      "resposta": "Ticket médio é R$ 1.450...",
│      "resumo": "Crescimento MoM +12%"
│    }
│  }
├─ field "QUALIDADE" → JSON {...}
└─ field "PERFORMANCE" → JSON {...}

TTL: 7 dias
```

✅ **Ganhos:**
- Usuário começa nova conversa com contexto relevante pronto
- Menos tokens (memory já está lá)
- Latência reduzida (Redis é rápido)
- Consolidação automática (Celery noturno)

---

### 4. **Catálogo SQL (30 Queries)**

```
db/mysql/queries/
├── ticket_medio.sql
├── retrabalho.sql
├── faturamento_mensal.sql
├── cross_selling.sql          ← Aquele com pares
├── performance_vendedor.sql
└── ... (25 mais)

Cada query:
- Pré-definida (whitelist)
- Parametrizada (date_from, date_to, limit)
- Comentada (o que mede)
- Testada com dados reais
```

✅ **Por que catálogo?**
- Apenas queries aprovadas
- Sem SQL injection
- Versionável + auditável
- Ligado a agregadores

---

### 5. **Skills YAML** (skill/skills/*.yaml)

```yaml
name: "faturamento_analyzer"
model: "gpt-4o-mini"
temperature: 0.3
context_budget: 4000

system: |
  Você é especialista em análise de faturamento.
  
  Dados fornecidos:
  - Top-10 combos por receita (pré-agregados)
  - Mix de categorias (%)
  - Tendências sazonais
  
  IMPORTANTE: Não faça agregações; 
  os dados já estão processados.
  
  Responda em português, acionável, com exemplos dos dados.
```

✅ **Por que YAML?**
- Separação: instruções vs código
- Fácil de editar sem código
- Versionável (Git)
- Reutilizável (MCP + API)

---

## 📊 RESULTADOS ESPERADOS

### Antes (Maestro v1 Monolítico)

```
❌ Custo: $0.14/query (40% overhead)
❌ Latência: 2.3s (P95)
❌ Qualidade: LLM recusa ("não consigo agregar")
❌ UX: Usuário repete contexto
❌ Dados: Brutos, não confiáveis
❌ Nomes: LLM inventa
```

### Depois (OrionMCP v2)

```
✅ Custo: $0.006/query (-95%)
   - Decision Router: Haiku (rápido)
   - Agregadores: Determinístico (sem LLM extra)
   - Pipeline: Eficiente (só dados necessários)

✅ Latência: 1.5-2s
   - Menos tokens = mais rápido
   - Memory curta do Redis = acesso rápido

✅ Qualidade: LLM narra dados já correctos
   - Agregadores garantem exactidão
   - Nomes reais do BD
   - Métricas explicadas

✅ UX: Usuário começa com contexto pronto
   - Memory curta (Redis)
   - Consolidado noturna (Celery)
   - Multi-intenção por sessão

✅ Confiabilidade: Auditável
   - Decision Router: Regras explícitas
   - Agregadores: Determinísticos
   - SQL: Catalogado + testado
```

---

## 🔐 SEGURANÇA E CONTROLE

### Dados Sensíveis

```
❌ NUNCA expor ao LLM:
- Preços unitários brutos
- Margens por cliente
- CPF/email de clientes
- Dados de competidores

✅ Expor como agregação:
- Ticket médio (não preços)
- Margem % (não valor)
- Métricas agregadas (não granulares)
```

### Rate Limiting

```
Redis + heurística:
- 100 queries/hora por usuário
- Penalidade exponencial se exceder
- Logs em PostgreSQL
```

### Auditoria

```
memory_consolidation_log:
- user_id, timestamp, status
- intentions processadas
- sessões deletadas
- erros (se houver)
```

---

## 📈 ROADMAP

### Semana 1-2: Setup + Config
- [ ] Estrutura de diretórios
- [ ] Pydantic Settings
- [ ] FastAPI + routes básicas
- [ ] Database pools (MySQL, PostgreSQL, Redis)

### Semana 3: Core Components
- [ ] Decision Router
- [ ] SkillLoader + Registry
- [ ] Data Pipeline (genérico)
- [ ] Context Builder

### Semana 4: Agregadores
- [ ] CrossSellingAggregator
- [ ] FaturamentoAggregator
- [ ] PerformanceAggregator
- [ ] ... (testes)

### Semana 5: Memory + Celery
- [ ] Categorizer (LLM multi-intent)
- [ ] Summarizer
- [ ] Memory Builder
- [ ] Celery Beat + Tasks
- [ ] Consolidator

### Semana 6: Integração + MCP
- [ ] Testes E2E
- [ ] MCP Server (tools que chamam agregadores)
- [ ] Documentação
- [ ] Deploy (Docker)

---

## 🎯 RESPONSABILIDADES ÚNICAS (Single Responsibility)

Cada arquivo = UMA responsabilidade:

| Arquivo | Responsabilidade |
|---------|-----------------|
| `config/settings.py` | Load + validate env vars |
| `route/chat.py` | Receber + responder HTTP |
| `core/orchestrator.py` | Orquestrar turno (não fazer lógica) |
| `core/decision/router.py` | Decidir ação (determinístico) |
| `core/data_engine/pipeline.py` | Pipeline genérico |
| `core/aggregators/*.py` | Agregação específica por skill |
| `context/builder.py` | Montar contexto com budget |
| `llm_provider/openai.py` | Chamar OpenAI |
| `state/repository.py` | CRUD SessionState |
| `memory/consolidator.py` | Job noturno |
| `memory/categorizer.py` | Categorizar por intenção |
| `cache/redis_client.py` | Redis connection |
| `tasks/consolidate.py` | Celery task |

✅ **Benefício:** Fácil de testar, debugar e manter.

---

## 🏆 DIFERENCIADORES

### vs. Soluções Genéricas (ChatGPT, Claude Directo)

```
❌ Genérico: "Use Claude.ai directo"
   - Usuário copia-cola dados manualmente
   - Sem contexto de sessão
   - Sem agregações automáticas
   - Sem memory curta

✅ OrionMCP v2:
   - Integrado ao BD (dados sempre frescos)
   - Contexto automático por intenção
   - Agregadores específicos (dados correctos)
   - Memory curta (reutilização)
```

### vs. Soluções Monolíticas (Maestro v1)

```
❌ Monolítico:
   - 1 SKILL genérico
   - LLM governa decisões
   - Dados brutos
   - Sem memory curta

✅ OrionMCP v2:
   - 6+ SKILLs por domínio
   - Decision Engine determinístico
   - Agregadores especializados
   - Memory curta consolidada
```

### vs. Soluções com LLM Agents (AutoGPT, etc.)

```
❌ LLM Agents:
   - LLM toma decisões (caro, lento)
   - Pode aluci​nar
   - Difícil de controlar

✅ OrionMCP v2:
   - Decisões determinísticas (regras)
   - LLM apenas narra
   - Barato + rápido
   - Previsível + auditável
```

---

## 💡 CONCLUSÃO

**OrionMCP V2** é uma plataforma que:

1. **Automatiza decisões** (Decision Router) em vez de deixar LLM escolher
2. **Processa dados** (Agregadores) ANTES de mandar para LLM
3. **Persiste estado** (PostgreSQL) para não perder contexto
4. **Consolida memory** (Redis + Celery) para reutilização
5. **Expõe como MCP** para clientes externos (IDEs, scripts)

**Resultado**: Chat confiável, rápido, barato e determinístico para análise de negócios em rede de 50-60 concessionárias.

**Metáfora**: Se Maestro v1 era um "secretário que adivinhas o que você quer", OrionMCP v2 é um "analista que SABE exactamente o que você precisa e o traz já pronto".

---

## 📚 DOCUMENTOS RELACIONADOS

- `PLANO_DESCRITIVO_ORION_MCP_V2.md` - Detalhe arquivo por arquivo
- `FLUXO_PROCESSO_ORION_MCP_V2.md` - Fluxos detalhados (em desenvolvimento)
- `30_QUERIES_OTIMIZADAS.md` - Catálogo de 30 queries SQL
- `SESSOES_E_BANCO_DE_DADOS.md` - Arquitetura PostgreSQL + Redis
- `.env.example` - Variáveis de ambiente
- `docker-compose.yml` - Stack completo

---

**Status**: Pronto para começar implementação (Semana 1)  
**Próximo passo**: Validar estrutura de diretórios + começar com Setup + Config
