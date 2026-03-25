# 🎼 Integração: Agente Visualizador + Maestro

## Registro no Maestro

Adicione esta linha à tabela de **Registro de Agentes Disponíveis** no `maestro.md`:

```txt
| `agente_visualizador` | Visualizador de Dados | Visualização | Sempre que dados precisam de visualização automática; recomenda o melhor gráfico (7 tipos) |
```

---

## Quando o Maestro Invoca Esta Skill

### 1. **Usuário pede visualização explícita**

```
Usuário: "Visualize as vendas de 2024"
           ↓
Maestro reconhece: palavra-chave "visualize", "gráfico", "desenhe"
           ↓
Seleciona: agente_visualizador (+ agente_dados ou agente_financeiro se precisar de dados)
           ↓
Fluxo: agente_mysql → agente_dados/financeiro → agente_visualizador
```

### 2. **Resultado de análise precisa de visualização**

```
agente_dados retorna:
{
  "resultado": "Média de vendas: R$ 2500",
  "dados_para_visualizar": {
    "meses": ["Jan", "Fev", "Mar", ...],
    "vendas": [1500, 2100, 1800, ...]
  }
}
           ↓
Maestro detecta: campo "dados_para_visualizar"
           ↓
Invoca: agente_visualizador(dados=dados_para_visualizar)
           ↓
Recebe: codigo_grafico HTML/JS
           ↓
Embarca no HTML da resposta ao usuário
```

### 3. **Dashboard multi-gráfico**

```
Pergunta: "Mostre um resumo das vendas"
           ↓
Maestro:
  1. agente_financeiro → retorna resumo + dados
  2. Para cada conjunto de dados:
       agente_visualizador → código gráfico
  3. Sintetiza todos em HTML com múltiplos gráficos
```

---

## Fluxo Completo com Maestro

### Cenário: "Como estão as vendas por região?"

```
┌─────────────────────────────────────────────────────────────┐
│ USUÁRIO: "Como estão as vendas por região?"                │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ MAESTRO (Análise da Pergunta)                               │
│ • Domínios: Financeiro + Visualização                       │
│ • Tipo esperado: Analítica + Gráfico                        │
│ • Agentes selecionados: mysql, financeiro, visualizador     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ PASSO 1: agente_mysql                                       │
│ Input: { tabela: "vendas", conexao: {...} }                │
│ Output: df_vendas (carregado)                               │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ PASSO 2: agente_financeiro (FASE 1)                         │
│ Input: { pergunta, df_vendas, fase: "extracao" }           │
│ Output: { perguntas_dados: [...] }                          │
│         (define agregações)                                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ PASSO 3: agente_agregador (NOVO)                            │
│ Input: { perguntas_dados, df_vendas }                       │
│ Output: { resultado_extracao: {...} }                       │
│         (dados agregados reais)                              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ PASSO 4: agente_financeiro (FASE 2)                         │
│ Input: { pergunta, resultado_extracao }                     │
│ Output: { resposta: "Região X lidera com...",               │
│           dados_para_visualizar: [...] }                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ PASSO 5: agente_visualizador ⭐                              │
│ Input: { dados: resultado_agregado,                         │
│          pergunta_contexto: "Vendas por região" }           │
│ Output: { tipo_grafico: "bar",                              │
│           codigo_grafico: "<div>...</div><script>..." }     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ PASSO 6: avaliador_coerencia                                │
│ Input: { pergunta, respostas: [financeiro, visualizador] }  │
│ Output: { ranking, scores, conflitos }                      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ MAESTRO → RESPOSTA AO USUÁRIO                               │
│                                                              │
│ ## Análise: Vendas por Região                              │
│                                                              │
│ A região Norte lidera com R$ 450K (35% da receita).         │
│ Sul contribui com 28%, Leste 22%, Oeste 15%.                │
│                                                              │
│ [GRÁFICO BAR AQUI - código embarcado]                       │
│                                                              │
│ **Score**: Financeiro (0.95) | Visualizador (0.94)          │
└─────────────────────────────────────────────────────────────┘
```

---

## Assinatura de Invocação

```python
# Como o Maestro chama a skill

payload_para_visualizador = {
    "pergunta": "Como estão as vendas por região?",
    "contexto_maestro": "Usuário quer análise financeira com visualização",
    "tipo_resposta_esperada": "analítica",
    "dados": {
        "tabela": [
            {"regiao": "Norte", "vendas": 450000},
            {"regiao": "Sul", "vendas": 280000},
            {"regiao": "Leste", "vendas": 220000},
            {"regiao": "Oeste", "vendas": 150000}
        ]
    },
    "instrucao": "Escolha o gráfico mais adequado para esses dados"
}

# Resposta esperada
resposta_visualizador = {
    "agente_id": "agente_visualizador",
    "tipo_grafico_selecionado": "bar",
    "codigo_grafico": "<div>...</div><script>...",
    "scores": {...}
}
```

---

## Palavras-Chave para Trigger

O Maestro deveria invocar `agente_visualizador` quando detectar:

- "**visualiz**e", "**gráfico**", "**desenhe**", "**mostre**"
- "**chart**", "**plot**", "**diagramar**"
- "**compare** visualmente"
- "em **forma de gráfico**"
- Quando resultado anterior tem campo `dados_para_visualizar`

---

## Integração com Avaliador de Coerência

O `avaliador_coerencia` ranqueia a visualização junto com outras análises:

```json
{
  "resposta_financeiro": {
    "agente_id": "agente_financeiro",
    "score_final": 0.95,
    "pode_responder": true
  },
  "resposta_visualizador": {
    "agente_id": "agente_visualizador",
    "score_final": 0.94,
    "pode_responder": true
  }
}
```

Resultado: Ambas as respostas são qualificadas e apresentadas juntas.

---

## Casos de Uso Específicos

### Caso 1: Análise de Dados → Visualização

```
Usuário: "Analise as vendas de janeiro"
         ↓
Maestro invoca:
  1. agente_mysql (carrega dados)
  2. agente_dados (FASE 1: define perguntas)
  3. agente_agregador (executa agregações)
  4. agente_dados (FASE 2: interpreta)
  5. agente_visualizador (visualiza os dados analisados)
         ↓
Resultado: Análise + Gráfico em um só lugar
```

### Caso 2: Recomendação de Gráfico

```
Usuário: "Que tipo de gráfico devo usar para esses dados?"
         ↓
Maestro invoca:
  agente_visualizador(apenas_recomendacao=True)
         ↓
Resultado: Recomendação + Alternativas (sem código)
```

### Caso 3: Forçar Gráfico Específico

```
Usuário: "Visualize em pizza"
         ↓
Maestro invoca:
  agente_visualizador(tipo_grafico_preferido='pie')
         ↓
Resultado: Pie chart (mesmo que não seja ideal)
           + Aviso: "Aviso: Pie não é ideal para esses dados"
```

### Caso 4: Dashboard Executivo

```
Usuário: "Crie um resumo executivo com gráficos"
         ↓
Maestro:
  1. Coleta dados: agente_financeiro
  2. Para cada KPI:
       agente_visualizador(dados=kpi_data)
  3. Sintetiza em HTML multi-gráfico
         ↓
Resultado: Dashboard com 4-5 gráficos
```

---

## Payload Esperado pelo Visualizador

Quando Maestro invoca, deve passar:

```json
{
  "pergunta": "string — pergunta original do usuário",
  "contexto_maestro": "string — análise feita pelo Maestro",
  "dados": {
    "tabela": "array de objects ou DataFrame convertido para JSON"
  },
  "tipo_resposta_esperada": "factual|analítica|técnica|criativa|comparativa",
  "instrucao": "string — instrução específica se houver"
}
```

---

## Checklist de Integração

- [ ] Adicionar `agente_visualizador` ao registro no maestro.md
- [ ] Adicionar trigger words em "Quando Selecionar"
- [ ] Testar com dados de exemplo (bar, line, scatter, pie)
- [ ] Validar score de adequação (deve estar >= 0.80)
- [ ] Integrar com avaliador_coerencia
- [ ] Testar fluxo completo: mysql → dados → financeiro → visualizador
- [ ] Documentar em "Fluxos.md"

---

## Exemplo: Integração Rápida em Python

```python
from maestro import Maestro
from agente_visualizador.helpers import VisualizadorAgente

# Cenário: Maestro coletou dados e quer visualizar

maestro = Maestro()
viz = VisualizadorAgente()

# 1. Maestro coleta dados
dados_coletados = maestro.agente_financeiro(
    pergunta="Vendas por região"
)

# 2. Maestro invoca visualizador
resultado_viz = viz.analisar_e_gerar(
    dados=dados_coletados['resultado_extracao'],
    pergunta_contexto=dados_coletados['pergunta']
)

# 3. Maestro sintetiza resposta
resposta_final = {
    "analise": dados_coletados['resposta'],
    "grafico": resultado_viz['codigo_grafico'],
    "score_geral": (
        dados_coletados['scores']['score_final'] * 0.6 +
        resultado_viz['scores']['score_final'] * 0.4
    )
}

# 4. Retorna ao usuário
maestro.enviar_resposta(resposta_final)
```

---

## Troubleshooting

### Problema: Gráfico não renderiza

**Causas:**
- Script Chart.js não carregou
- Dados em formato inválido
- Navegador sem suporte Canvas

**Solução:**
- Verificar console do navegador
- Validar JSON do `codigo_grafico`
- Testar em navegador moderno

### Problema: Seleção de gráfico errada

**Causas:**
- Dados com tipos mistos não detectados corretamente
- Contexto insuficiente

**Solução:**
```python
# Ver análise completa
resultado = viz.analisar_e_gerar(dados)
print(resultado['analise_dados'])  # Verificar tipos detectados

# Forçar tipo correto
resultado = viz.analisar_e_gerar(
    dados,
    tipo_grafico_preferido='bar'
)
```

### Problema: Muitos nulls

**Causa:**
- Dados com qualidade ruim

**Solução:**
```python
# Agente retorna aviso
resultado = viz.analisar_e_gerar(dados)
print(resultado['analise_dados']['problemas_qualidade'])

# Limpar dados antes de visualizar
df_limpo = df.dropna()
resultado = viz.analisar_e_gerar(df_limpo)
```

---

## Próximas Fases de Integração

### Fase 1 (Atual)
✅ Seleção automática de 7 tipos básicos  
✅ Geração Chart.js  
✅ Integração Maestro

### Fase 2 (Curto Prazo)
⏳ Box Plot + Heatmap (Vega-Lite)  
⏳ Temas corporativos  
⏳ Legendas customizáveis

### Fase 3 (Médio Prazo)
⏳ Dashboard multi-gráfico automático  
⏳ Filtros interativos  
⏳ Exportar PNG/SVG

---

**Status**: ✅ Pronto para Integração  
**Última atualização**: 2026-03-22
