# 🎨 Agente Visualizador de Dados — Guia Rápido

## O Que Faz

**Recebe dados (DataFrame) e escolhe automaticamente o melhor tipo de gráfico**, gerando código Chart.js pronto para usar.

---

## 7 Tipos de Gráficos Suportados

| # | Tipo | Quando Usar | Exemplo |
|---|------|-----------|---------|
| 1️⃣ | **Bar Chart** | 1 categórica + 1 métrica | Vendas por região |
| 2️⃣ | **Line Chart** | Série temporal | Evolução de vendas (ano) |
| 3️⃣ | **Pie Chart** | Partes de um todo (≤5 fatias) | Distribuição de receita |
| 4️⃣ | **Scatter Plot** | 2 variáveis numéricas | Correlação vendas vs lucro |
| 5️⃣ | **Histogram** | Distribuição de 1 variável | Distribuição de idade |
| 6️⃣ | **Box Plot** | Comparação entre grupos + outliers | Salários por depto |
| 7️⃣ | **Heatmap** | 2 dimensões categóricas + métrica | Vendas região×trimestre |

---

## Uso Rápido

### Modo Automático (Recomendado)

```python
from helpers import VisualizadorAgente
import pandas as pd

# Seus dados
df = pd.DataFrame({
    'mes': ['Jan', 'Fev', 'Mar', 'Abr'],
    'vendas': [1500, 2100, 1800, 2400]
})

# Criar agente
viz = VisualizadorAgente()

# Analisar e gerar gráfico
resultado = viz.analisar_e_gerar(
    dados=df,
    pergunta_contexto="Como evoluíram as vendas?"
)

# Acessar resultado
print(resultado['tipo_grafico_selecionado'])  # "line"
print(resultado['score_adequacao'])            # 0.94
print(resultado['codigo_grafico'])             # HTML/JS pronto
```

### Forçar um Tipo Específico

```python
resultado = viz.analisar_e_gerar(
    dados=df,
    tipo_grafico_preferido='bar'  # Sobrepõe seleção automática
)
```

### Apenas Recomendação (Sem Código)

```python
resultado = viz.analisar_e_gerar(
    dados=df,
    apenas_recomendacao=True  # Retorna só análise, sem código
)
```

---

## Estrutura de Resposta

```json
{
  "agente_id": "agente_visualizador",
  "tipo_grafico_selecionado": "line",
  "score_adequacao": 0.94,
  "justificativa_selecao": "1 série temporal + 1 métrica → Line Chart ideal",
  "alternativas": [
    {
      "tipo": "bar",
      "score": 0.78,
      "quando_usar": "Se preferir comparação direta entre meses"
    }
  ],
  "analise_dados": {
    "n_linhas": 12,
    "n_colunas": 3,
    "colunas": [
      {
        "nome": "mes",
        "tipo": "categórico",
        "cardinalidade": 12
      }
    ],
    "problemas_qualidade": []
  },
  "codigo_grafico": "<div>...</div><script>...</script>",
  "scores": {
    "relevancia": 0.95,
    "completude": 0.90,
    "confianca": 0.94,
    "score_final": 0.937
  }
}
```

---

## Regras de Seleção Automática

### 1 Coluna Apenas
- **Numérica** → Histogram
- **Categórica** → Bar Chart

### 2 Colunas
| Combinação | Gráfico | Critério |
|-----------|---------|----------|
| Num + Num | Scatter | Correlação |
| Cat + Num | Bar | Se card ≤ 50 |
| Cat + Num | BoxPlot | Se card > 50 |
| Temporal + Num | Line | Sempre |
| Cat + Cat | Heatmap | Se card ≤ 10 cada |

### 3+ Colunas
- **Temporal + múltiplos nums** → Line (multi-série)
- **2+ cats + 1 num** → Heatmap (se card baixa)
- **1 cat + múltiplos nums** → Bar (multi-série)

---

## Validação Automática

A skill detecta e avisa sobre:

✅ **Qualidade dos Dados:**
- Nulls altos (>50%)
- Cardinalidade muito alta (>1000)
- Datasets vazios

✅ **Recomendações:**
- "Muitas categorias (N>50), considere filtrar ou usar BoxPlot"
- "Dataset vazio, nenhum dado para visualizar"

---

## Integração com Maestro

### Invocação Típica

```
Maestro recepciona pergunta
  ↓
"Visualize os dados"
  ↓
Maestro → agente_visualizador
  ↓
Retorna: tipo_grafico + codigo_grafico
  ↓
Maestro embarca código no HTML da resposta
  ↓
Usuário vê gráfico renderizado
```

### Fluxo Completo

```
1. agente_dados / agente_financeiro retorna resultado_extracao
2. Maestro invoca agente_visualizador(dados=resultado_extracao)
3. Visualizador retorna código do gráfico
4. Maestro renderiza no HTML
```

---

## Exemplos Concretos

### Exemplo 1: Vendas por Mês (Bar)

```python
df = pd.DataFrame({
    'mes': ['Jan', 'Fev', 'Mar'],
    'vendas': [1500, 2100, 1800]
})

# Automático: Bar Chart (1 cat + 1 num)
viz.analisar_e_gerar(df)
# → score: 0.95, tipo: bar
```

### Exemplo 2: Série Temporal (Line)

```python
df = pd.DataFrame({
    'data': pd.date_range('2024-01-01', periods=30),
    'temperatura': [15, 16, 14, ...]
})

# Automático: Line Chart (temporal + num)
viz.analisar_e_gerar(df)
# → score: 0.94, tipo: line
```

### Exemplo 3: Correlação (Scatter)

```python
df = pd.DataFrame({
    'vendas': [1500, 2100, 1800, 2400],
    'lucro': [350, 520, 420, 580]
})

# Automático: Scatter Plot (num + num)
viz.analisar_e_gerar(df)
# → score: 0.92, tipo: scatter
```

### Exemplo 4: Padrões (Heatmap)

```python
df = pd.DataFrame({
    'regiao': ['Norte', 'Sul', 'Leste', 'Oeste'] * 4,
    'trimestre': ['Q1']*4 + ['Q2']*4 + ['Q3']*4 + ['Q4']*4,
    'vendas': [450, 380, 520, 490, ...]
})

# Automático: Heatmap (2 cat + 1 num)
viz.analisar_e_gerar(df)
# → score: 0.87, tipo: heatmap
```

---

## Scores Explicados

```
relevancia   → Quão adequado é o gráfico para os dados?
completude   → Quanto do código foi gerado? (0.9 = com código, 0.7 = apenas recomendação)
confianca    → Confiança na seleção automática (depende de score_adequacao)
score_final  → (relevancia × 0.4) + (completude × 0.3) + (confianca × 0.3)
```

**Interpretação:**
- `score_final >= 0.90` → Excelente seleção
- `score_final >= 0.80` → Boa seleção
- `score_final >= 0.70` → Aceitável
- `score_final < 0.70` → Tipo não ideal, verifique alternativas

---

## Casos de Uso no Maestro

### 1. **Usuário pede "visualize esses dados"**

```
Maestro: "Visualize os dados de vendas"
  ↓
Invoca: agente_visualizador(dados=df_vendas)
  ↓
Retorna: <gráfico renderizado>
```

### 2. **Agente de dados retorna resultado de análise**

```
agente_dados: "Analisei 1000 registros, aqui estão as estatísticas"
  ↓
Maestro: "Vou visualizar isso para ficar mais claro"
  ↓
Invoca: agente_visualizador(dados=resultado_extracao)
```

### 3. **Dashboard com múltiplos gráficos**

```
Para cada conjunto de dados:
  Maestro → agente_visualizador
  ← Recebe código do gráfico
  
Sintetiza todos os códigos em um HTML final
```

---

## Customização

### Tema (Light/Dark)

```python
resultado = viz.analisar_e_gerar(
    dados=df,
    tema='dark'  # Padrão: 'light'
)
```

### Biblioteca (Chart.js ou Vega-Lite)

```python
resultado = viz.analisar_e_gerar(
    dados=df,
    biblioteca='vegaLite'  # Padrão: 'chartjs'
)
```

### Limite de Categorias

```python
resultado = viz.analisar_e_gerar(
    dados=df,
    limite_categorias=30  # Padrão: 50
)
```

---

## Limitações Conhecidas

⚠️ **Atual:**
- Box Plot e Heatmap precisam de Vega-Lite (não implementado em Chart.js puro)
- Não valida valores extremos (use agente_dados para outliers)
- Assume dados já limpos (não trata imputação)

✅ **Planejado:**
- Suporte a Vega-Lite para complexos
- Detecção automática de outliers
- Legendas customizáveis
- Temas corporativos

---

## Debugging

### Verificar Análise de Dados

```python
resultado = viz.analisar_e_gerar(dados=df)

# Análise completa
print(resultado['analise_dados'])

# Colunas identificadas
for col in resultado['analise_dados']['colunas']:
    print(f"{col['nome']}: {col['tipo']}")

# Problemas detectados
print(resultado['analise_dados']['problemas_qualidade'])
```

### Forçar Debug Mode

```python
# Ver score detalhado
resultado = viz.analisar_e_gerar(dados=df)
print(f"Score: {resultado['scores']}")
print(f"Justificativa: {resultado['justificativa_selecao']}")
```

---

## FAQ

**P: Como renderizar o código gerado?**  
R: Cole o `codigo_grafico` em um arquivo HTML e abra no navegador.

**P: Posso forçar um tipo diferente?**  
R: Sim, use `tipo_grafico_preferido='pie'`, etc.

**P: O que fazer se muitas categorias?**  
R: O agente avisa e sugere filtro. Considere agrupar dados antes.

**P: Suporta 3D?**  
R: Não no momento. Use 2 variáveis por gráfico.

**P: Posso customizar cores?**  
R: Atualmente não. Future roadmap: tema corporativo.

---

## Checklist de Uso

- [ ] Dados em formato DataFrame
- [ ] Sem valores nulos críticos (se houver, agente avisa)
- [ ] Contexto claro se possível (`pergunta_contexto`)
- [ ] Usar preferência apenas se souber o tipo certo
- [ ] Verificar `problemas_qualidade` antes de usar para decisão

---

## Roadmap

- ✅ Bar, Line, Pie, Scatter, Histogram
- ⏳ Box Plot + Heatmap (Vega-Lite)
- ⏳ Temas corporativos
- ⏳ Legendas customizáveis
- ⏳ Filtros interativos
- ⏳ Exportar como PNG/SVG

---

**Versão:** 1.0  
**Status:** ✅ Produção  
**Última atualização:** 2026-03-22
