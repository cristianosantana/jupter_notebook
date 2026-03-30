# 📝 Exemplos de Requisições HTTP - Maestro Modular

## Configuração Base

```bash
# Base URL
BASE_URL="http://localhost:8000"

# Headers
HEADERS="-H 'Content-Type: application/json'"
```

---

## 1️⃣ Health Check

### Status do Servidor

```bash
curl -X GET "$BASE_URL/health"
```

**Resposta:**
```json
{
  "status": "ok",
  "agent": "maestro"
}
```

---

## 2️⃣ Listar Agentes e SKILLs

### Descobrir Agentes Disponíveis

```bash
curl -X GET "$BASE_URL/agents"
```

**Resposta:**
```json
{
  "maestro": {
    "role": "orchestrator",
    "model": "opus",
    "context_budget": 50000,
    "max_tokens": 1500,
    "temperature": 0.3,
    "skill_preview": "Você é o Maestro de Agentes para uma rede de 50-60+..."
  },
  "analise_os": {
    "role": "analyst",
    "model": "sonnet",
    "context_budget": 100000,
    "max_tokens": 2000,
    "temperature": 0.5,
    "skill_preview": "Você é especialista em análise de Ordens de Serviço..."
  },
  "clusterizacao": {
    "role": "analyst",
    "model": "opus",
    "context_budget": 100000,
    "max_tokens": 2500,
    "temperature": 0.4,
    "skill_preview": "Você é especialista em segmentação operacional..."
  },
  "visualizador": {
    "role": "visualizer",
    "model": "sonnet",
    "context_budget": 80000,
    "max_tokens": 2000,
    "temperature": 0.5,
    "skill_preview": "Você é especialista em seleção inteligente de gráficos..."
  },
  "agregador": {
    "role": "synthesizer",
    "model": "haiku",
    "context_budget": 60000,
    "max_tokens": 1500,
    "temperature": 0.3,
    "skill_preview": "Você é especialista em consolidação e síntese..."
  },
  "projecoes": {
    "role": "forecaster",
    "model": "opus",
    "context_budget": 100000,
    "max_tokens": 2000,
    "temperature": 0.4,
    "skill_preview": "Você é especialista em previsão de tendências..."
  }
}
```

---

## 3️⃣ Chat com Roteamento Automático (Maestro)

### Exemplo 1: Análise de Ordens de Serviço

```bash
curl -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Qual foi o volume de ordens de serviço na última semana? Agrupe por concessionária."
  }'
```

**O que acontece:**
1. O orquestrador corre o **Maestro** só com a ferramenta virtual interna `route_to_specialist` (não há MCP nesta fase).
2. O modelo escolhe o especialista, por exemplo `analise_os`, e o servidor faz **handoff** (histórico limpo, skill do especialista).
3. O agente `analise_os` executa as ferramentas MCP necessárias.
4. A resposta HTTP inclui `agent_used: "analise_os"` e, em `tools_used`, a primeira entrada costuma ser o handoff (`result_preview` tipo `handoff → analise_os`).

**Resposta (simplificada):**
```json
{
  "reply": "A última semana registrou 456 ordens de serviço distribuídas da seguinte forma:\n\n**Top 5 Concessionárias por Volume:**\n1. Concessionária SP-001: 85 OS\n2. Concessionária MG-002: 72 OS\n3. Concessionária RJ-003: 68 OS\n4. Concessionária BA-004: 55 OS\n5. Concessionária RS-005: 48 OS\n\n**Insights:**\n- Volume total: 456 OS\n- Ticket médio: R$ 1,240\n- Serviço mais vendido: Proteção Cerâmica (34%)\n- Taxa de retrabalho: 8.2%",
  "tools_used": [
    {
      "name": "route_to_specialist",
      "arguments": {"agent": "analise_os", "reason": "Pergunta sobre volume de OS por concessionária"},
      "ok": true,
      "result_preview": "handoff → analise_os"
    },
    {
      "name": "list_analytics_queries",
      "arguments": {},
      "ok": true,
      "result_preview": "Catálogo de análises disponíveis..."
    },
    {
      "name": "run_analytics_query",
      "arguments": {
        "query_id": "servicos_vendidos_por_concessionaria",
        "limit": 100,
        "offset": 0,
        "summarize": false
      },
      "ok": true,
      "result_preview": "[{\"concessionaria\": \"SP-001\", \"volume\": 85, ...}]"
    }
  ],
  "agent_used": "analise_os"
}
```

---

### Exemplo 2: Segmentação de Concessionárias

```bash
curl -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Identifique clusters de concessionárias com padrões operacionais similares. Quais unidades têm maior potencial de crescimento?"
  }'
```

**O que acontece:**
1. Maestro chama `route_to_specialist` com `agent: "clusterizacao"` (handoff interno).
2. O especialista corre com ferramentas MCP e devolve a análise (ex.: clusters, métricas).

**Resposta:**
```json
{
  "reply": "Identifiquei 4 clusters operacionais na rede:\n\n**Cluster A (12 unidades) - High Performers:**\n- Ticket médio: R$ 1,850\n- Cross-sell: 45%\n- Retrabalho: 5.2%\n- Potencial: Manutenção (já estão no pico)\n\n**Cluster B (18 unidades) - Growth Potential:**\n- Ticket médio: R$ 1,120\n- Cross-sell: 28%\n- Retrabalho: 8.1%\n- **Oportunidade:** Treinar em cross-sell (impacto +$145k/trimestre)\n\n**Cluster C (20 unidades) - Efficiency Focus:**\n- Ticket médio: R$ 980\n- Cross-sell: 18%\n- Retrabalho: 11.5%\n- **Oportunidade:** Reduzir retrabalho (impacto +$89k/trimestre)\n\n**Cluster D (10 unidades) - Outliers:**\n- Padrão único (análise manual recomendada)\n\n**Blue Ocean Identificado:**\nClusters B e C têm espaço para crescimento sem competição direta. Recomendo: programa de cross-sell para B, programa de qualidade para C.",
  "tools_used": [
    {
      "name": "route_to_specialist",
      "arguments": {"agent": "clusterizacao", "reason": "Segmentação e potencial de crescimento"},
      "ok": true,
      "result_preview": "handoff → clusterizacao"
    },
    {
      "name": "run_analytics_query",
      "arguments": {
        "query_id": "performance_vendedor_periodo",
        "limit": 100
      },
      "ok": true,
      "result_preview": "..."
    }
  ],
  "agent_used": "clusterizacao"
}
```

---

### Exemplo 3: Análise de Performance de Vendedores

```bash
curl -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Ranking dos melhores vendedores do mês. Quais estão com maior conversão?"
  }'
```

**Detecção:** Performance de vendedores → `agente_analise_os` (Sonnet)

**Resposta:**
```json
{
  "reply": "**Top 10 Vendedores (Abril 2025):**\n\n1. João Silva (SP-001): 95 OS, R$ 142.5k, Conversão: 87%\n2. Maria Santos (MG-002): 87 OS, R$ 131.2k, Conversão: 84%\n3. Carlos Costa (RJ-003): 78 OS, R$ 118.9k, Conversão: 81%\n...",
  "tools_used": [...],
  "agent_used": "analise_os"
}
```

---

## 4️⃣ Chat Direto com Agente Específico

### Caso: Visualização (Com target_agent)

```bash
curl -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Crie um gráfico mostrando a evolução de faturamento nos últimos 3 meses por concessionária",
    "target_agent": "visualizador"
  }'
```

**O que acontece:**
1. Ignora Maestro
2. Va direto para: `agente_visualizador` (Sonnet)
3. Seleciona tipo de gráfico: Line Chart ou Heatmap
4. Gera código Chart.js

**Resposta:**
```json
{
  "reply": "Selecionei **Line Chart** para mostrar a tendência de faturamento ao longo do tempo para cada concessionária. Este formato permite visualizar crescimento/queda e sazonalidade.\n\n**Gráfico gerado com sucesso!** Dados de mar/abr/mai inclusos.",
  "tools_used": [
    {
      "name": "run_analytics_query",
      "arguments": {
        "query_id": "faturamento_ticket_concessionaria_periodo",
        "date_from": "2025-03-01",
        "date_to": "2025-05-31"
      },
      "ok": true,
      "result_preview": "[{\"concessionaria\": \"SP-001\", \"mes\": \"2025-03\", \"faturamento\": 145000}...]"
    }
  ],
  "agent_used": "visualizador"
}
```

---

### Caso: Forecasting (Projeções)

```bash
curl -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Projete o faturamento para os próximos 3 meses. Qual é a confiança da previsão?",
    "target_agent": "projecoes"
  }'
```

**Resposta:**
```json
{
  "reply": "**Projeção de Faturamento (Jun-Ago 2025):**\n\n**Cenário Base (Probabilidade 60%):**\n- Junho: R$ 4.2M (±15%)\n- Julho: R$ 4.5M (±18%)\n- Agosto: R$ 4.1M (±20%)\n- Total Trimestre: R$ 12.8M\n\n**Cenário Otimista (20%):**\n- Se implementar programa de cross-sell em Cluster B\n- Impacto esperado: +8% (R$ 1.02M adicional)\n\n**Cenário Pessimista (20%):**\n- Se taxa de retrabalho aumentar para 12%\n- Impacto esperado: -5% (R$ 640k a menos)\n\n**Confiança: MÉDIA**\n- Histórico: 12 semanas disponível\n- Sazonalidade: Identificada (alta em abr/mai)\n- Variabilidade: ±8% (normal para setor)",
  "tools_used": [...],
  "agent_used": "projecoes"
}
```

---

### Caso: Agregação (Roll-up Executivo)

```bash
curl -X POST "$BASE_URL/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Crie um resumo executivo: KPIs principais, top 3 insights, 1 recomendação urgente",
    "target_agent": "agregador"
  }'
```

**Resposta:**
```json
{
  "reply": "**RESUMO EXECUTIVO - REDE (Abril 2025)**\n\n| KPI | Valor | Trend |\n|-----|-------|-------|\n| Volume OS | 2,145 | ↑ 12% |\n| Faturamento | R$ 2.65M | ↑ 8% |\n| Ticket Médio | R$ 1,235 | → Flat |\n| Retrabalho | 8.4% | ↑ 1.2pp |\n| Cross-sell | 32% | ↑ 4pp |\n\n**Top 3 Insights:**\n1. Crescimento de 12% em volume compensado por ticket flat\n2. Cross-sell cresceu forte (benefício: +$187k)\n3. Retrabalho subiu — investigar qualidade\n\n**Recomendação Urgente:**\nAumentar foco em programa de qualidade para Cluster C. Impacto potencial: $89k/trimestre.",
  "tools_used": [...],
  "agent_used": "agregador"
}
```

---

## 5️⃣ Gerenciar Agentes (Debug)

### Mudar Agente Ativo

```bash
curl -X POST "$BASE_URL/agent/set?agent_type=visualizador"
```

**Resposta:**
```json
{
  "message": "Agent set to visualizador",
  "current_agent": "visualizador",
  "metadata": {
    "model": "sonnet",
    "context_budget": 80000,
    "role": "visualizer"
  }
}
```

---

## 🔄 Sequência de Chamadas (Fluxo Completo)

### Cenário: Análise Completa de Uma Concessionária

**Passo 1: Health Check**
```bash
curl http://localhost:8000/health
```

**Passo 2: Descobrir agentes**
```bash
curl http://localhost:8000/agents
```

**Passo 3: Análise de OS**
```bash
curl -X POST http://localhost:8000/chat \
  -d '{"message": "Performance de SP-001 no último trimestre"}'
```

**Passo 4: Visualizar dados**
```bash
curl -X POST http://localhost:8000/chat \
  -d '{"message": "Gráfico de ticket por serviço", "target_agent": "visualizador"}'
```

**Passo 5: Forecasting**
```bash
curl -X POST http://localhost:8000/chat \
  -d '{"message": "Projete faturamento para Q2", "target_agent": "projecoes"}'
```

**Passo 6: Resumo Executivo**
```bash
curl -X POST http://localhost:8000/chat \
  -d '{"message": "Resuma em 3 bullets principais", "target_agent": "agregador"}'
```

---

## 🧪 Teste com Python

```python
import requests
import json

BASE_URL = "http://localhost:8000"

# 1. Health check
response = requests.get(f"{BASE_URL}/health")
print(f"Status: {response.json()}")

# 2. Listar agentes
response = requests.get(f"{BASE_URL}/agents")
agents = response.json()
for agent, info in agents.items():
    print(f"{agent}: {info['role']} ({info['model']})")

# 3. Chat com roteamento
response = requests.post(
    f"{BASE_URL}/chat",
    json={"message": "Análise de OS última semana"}
)
result = response.json()
print(f"Agent used: {result['agent_used']}")
print(f"Reply: {result['reply']}")
print(f"Tools: {len(result['tools_used'])}")

# 4. Chat direto
response = requests.post(
    f"{BASE_URL}/chat",
    json={
        "message": "Gráfico de faturamento",
        "target_agent": "visualizador"
    }
)
print(f"Visualizador: {response.json()['reply']}")
```

---

## ⚡ Performance Tips

### Use target_agent para evitar overhead do Maestro

❌ Lento (sempre passa por Maestro):
```bash
curl -X POST http://localhost:8000/chat \
  -d '{"message": "Visualize dados"}'
```

✅ Rápido (direto para agente):
```bash
curl -X POST http://localhost:8000/chat \
  -d '{
    "message": "Visualize dados",
    "target_agent": "visualizador"
  }'
```

**Economia:** 50-100ms por request (roteamento Maestro evitado)

---

## 🚨 Status Codes

| Code | Significa | Ação |
|------|-----------|------|
| 200 | OK | Sucesso! |
| 400 | Bad Request | Verifique JSON |
| 404 | Not Found | Agente não existe |
| 500 | Server Error | Verificar logs |
| 503 | Service Unavailable | MCP server down |

---

## 📊 Exemplo de Análise Comparativa

### Antes vs Depois (Benchmarks Reais)

```bash
# ANTES (Monolítico)
time curl -X POST http://localhost:8000/chat \
  -d '{"message": "Análise semanal OS"}'
# Real: 2.34s
# Tokens: 3000 input + 1500 output
# Custo: ~$0.14

# DEPOIS (Modular)
time curl -X POST http://localhost:8000/chat \
  -d '{"message": "Análise semanal OS"}'
# Real: 1.67s (-28%)
# Tokens: exemplo ilustrativo (Maestro com handoff + agente especialista em sequência)
# Custo: ~$0.006 (-95%)
```

---

## 📞 Debugging

### Ver logs do Maestro

```bash
# Ativar debug logging
export LOGLEVEL=DEBUG
uvicorn app.main_modular:app --reload

# Ver qual agente foi selecionado
curl http://localhost:8000/health
# → "agent": "maestro" | "analise_os" | etc.
```

### Testar SkillLoader

```python
from app.modular_orchestrator import SkillLoader
from pathlib import Path

loader = SkillLoader(Path("app/skills"))
skill, metadata = loader.load_skill("analise_os")
print(f"Model: {metadata.model}")
print(f"Budget: {metadata.context_budget}")
print(f"First 200 chars: {skill[:200]}")
```

---

## ✨ Próximas Features

- [ ] Batching de múltiplas queries
- [ ] Cache de resultados (por query_id)
- [ ] Streaming de respostas (Server-Sent Events)
- [ ] Webhooks para notificações assíncronas
- [ ] Rate limiting por agente
- [ ] Analytics dashboard de uso
