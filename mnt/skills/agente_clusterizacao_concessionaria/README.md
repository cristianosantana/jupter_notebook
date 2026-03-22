# 🎯 Agente de Clusterização de Concessionárias

## 📊 Visão Geral

O **Agente de Clusterização** é um sistema inteligente que segmenta automaticamente concessionárias em grupos homogêneos usando machine learning (K-Means/DBSCAN).

Extrai 15 features operacionais de cada concessionária, identifica clusters naturais e gera perfis descritivos detalhados.

---

## 🚀 Casos de Uso

### **1. Segmentação Automática**
"Quais os perfis operacionais das 60+ concessionárias?"

→ Identifica 4-6 clusters com características distintas
→ Gera nome e descrição para cada perfil
→ Mapeia cada concessionária ao seu cluster

### **2. Análise Comparativa**
"Como a MATRIZ SP se compara com concessionárias similares?"

→ Identifica cluster da concessionária
→ Compara métricas com média do cluster
→ Identifica pontos fortes e oportunidades de melhoria

### **3. Benchmarking**
"Quem são as melhores performers em cross-selling no cluster de alto volume?"

→ Ranking dentro de cada cluster
→ Identificação de best practices
→ Recomendações personalizadas

### **4. Identificação de Outliers**
"Quais concessionárias têm perfil muito diferente de todas as outras?"

→ DBSCAN detecta concessionárias únicas
→ Análise de características distintivas

---

## 📐 Features Extraídas (15 Dimensões)

### **Grupo 1: Volume e Faturamento**
1. `faturamento_total` — Faturamento últimos 90 dias
2. `ticket_medio` — Média de oss_valor_venda_real
3. `ticket_mediana` — Mediana de oss_valor_venda_real
4. `volume_os` — Quantidade de OS
5. `volume_servicos` — Quantidade de serviços

### **Grupo 2: Mix de Produtos**
6. `pct_servicos_premium` — % faturamento em serviços P80+
7. `pct_servicos_basicos` — % faturamento em serviços P0-20
8. `diversidade_servicos` — Índice Herfindahl invertido (1 - concentração)
9. `taxa_cross_sell` — % OS com 2+ serviços

### **Grupo 3: Eficiência Operacional**
10. `concentracao_vendedoras` — % faturamento nas top 2 vendedoras
11. `produtividade_vendedora` — Faturamento médio por vendedora
12. `taxa_conversao_pagamento` — % OS pagas

### **Grupo 4: Sazonalidade e Tendência**
13. `volatilidade_mensal` — Desvio padrão do faturamento mensal
14. `taxa_crescimento` — Variação % últimos 3m vs 3m anteriores
15. `intensidade_sazonal` — (Pico - Vale) / Mediana mensal

---

## 🛠️ Instalação

### **Pré-requisitos**

```bash
pip install pandas numpy scikit-learn sqlalchemy pymysql
```

### **Estrutura de Arquivos**

```
mnt/skills/agente_clusterizacao_concessionaria/
├── SKILL.md                 # Definição do agente
├── helpers.py               # Implementação do clustering
├── __init__.py              # Módulo Python
├── exemplo_uso.py           # Exemplos de uso
└── README.md                # Esta documentação
```

---

## 📖 Uso Básico

### **Exemplo 1: Clustering Completo**

```python
from mnt.skills.agente_clusterizacao_concessionaria import ClusteringAgent

# Criar agente
agent = ClusteringAgent(
    host="localhost",
    porta=3306,
    usuario="root",
    senha="sua_senha",
    banco="comercial"
)

# Executar clustering completo
resultado = agent.clusterizar_concessionarias(
    n_clusters=5,       # Número de clusters
    periodo_dias=90,    # Janela temporal
    metodo="kmeans"     # Algoritmo
)

# Exibir resumo
print(resultado["resumo_clustering"])
print(resultado["perfis_clusters"])
```

**Saída esperada:**
```json
{
  "resumo_clustering": {
    "total_concessionarias": 62,
    "n_clusters": 5,
    "silhouette_score": 0.68,
    "distribuicao": {
      "cluster_0": 12,
      "cluster_1": 18,
      "cluster_2": 15,
      "cluster_3": 10,
      "cluster_4": 7
    }
  },
  "perfis_clusters": [
    {
      "cluster_id": 0,
      "nome_perfil": "Alto Volume e Ticket Médio",
      "tamanho": 12,
      "caracteristicas": {
        "faturamento_medio": 850000.00,
        "ticket_medio": 4200.00,
        "taxa_cross_sell": 0.42
      },
      "concessionarias": ["MATRIZ SP", "FILIAL RJ", "MEGA AUTO BH"]
    }
  ]
}
```

---

### **Exemplo 2: Analisar Concessionária Específica**

```python
# Analisar MATRIZ SP
analise = agent.analisar_concessionaria("MATRIZ SP")

# Exibir comparação
print(f"Cluster: {analise['cluster_nome']}")
print(f"Posição: {analise['resumo_posicionamento']}")

# Comparação com cluster
for metrica, dados in analise['comparacao_cluster'].items():
    print(f"{dados['nome']}: {dados['diferenca_pct']:+.1f}% vs cluster")

# Concessionárias similares
print("Similares:", analise['concessionarias_similares'])

# Pontos fortes
print("Pontos fortes:", analise['pontos_fortes'])

# Oportunidades
print("Melhorias:", analise['pontos_de_melhoria'])
```

**Saída esperada:**
```
Cluster: Alto Volume e Ticket Médio
Posição: MATRIZ SP pertence ao cluster de alto desempenho (12 concessionárias).

Faturamento: +15.3% vs cluster
Ticket Médio: +7.1% vs cluster
Taxa Cross-Sell: -9.5% vs cluster ← OPORTUNIDADE!

Similares: [
  {'nome': 'FILIAL RJ', 'similaridade': 0.92},
  {'nome': 'MEGA AUTO BH', 'similaridade': 0.88}
]

Pontos fortes:
  • Faturamento 15% acima da média do cluster
  • Baixa concentração em vendedoras (35% vs 40%)

Melhorias:
  • Taxa de cross-sell 9.5% abaixo — potencial de R$ 42k/mês
  • Volatilidade mensal 18% maior que cluster
```

---

### **Exemplo 3: Uso com DataFrame Customizado**

```python
import pandas as pd

# Carregar dados de CSV (ou qualquer fonte)
df = pd.read_csv("dados_os.csv")

# Criar agente (sem conectar ao banco)
agent = ClusteringAgent(host="localhost")

# Extrair features do DataFrame
features = agent.extrair_features_concessionarias(
    periodo_dias=90,
    df=df
)

# Clusterizar
resultado_clustering = agent.clusterizar(n_clusters=5)

# Gerar perfis
perfis = agent.gerar_perfis_clusters()

print(f"✅ {len(perfis)} perfis gerados")
```

---

## 🧮 Algoritmos de Clustering

### **K-Means (Padrão)**

```python
resultado = agent.clusterizar_concessionarias(
    n_clusters=5,
    metodo="kmeans"
)
```

**Vantagens:**
- Rápido e eficiente
- Funciona bem com dados normalizados
- Número de clusters definido pelo usuário

**Quando usar:**
- Você sabe aproximadamente quantos perfis quer
- Dados bem distribuídos

---

### **DBSCAN (Detecção de Densidade)**

```python
resultado = agent.clusterizar_concessionarias(
    n_clusters=3,  # min_samples neste caso
    metodo="dbscan"
)
```

**Vantagens:**
- Detecta clusters de forma orgânica
- Identifica outliers automaticamente (-1)
- Não precisa definir número de clusters

**Quando usar:**
- Quer detectar perfis naturalmente
- Quer identificar concessionárias muito diferentes

---

## 📈 Interpretação de Resultados

### **Silhouette Score**

- **> 0.7** → Clusters muito bem definidos
- **0.5 - 0.7** → Clusters razoáveis
- **< 0.5** → Clusters fracos (considere mudar n_clusters)

### **Distância ao Centróide**

- **< 0.3** → Concessionária típica do cluster
- **0.3 - 0.6** → Concessionária com algumas variações
- **> 0.6** → Concessionária atípica (quase outlier)

### **Taxa de Similaridade**

- **> 0.9** → Concessionárias quase idênticas
- **0.7 - 0.9** → Muito similares
- **0.5 - 0.7** → Moderadamente similares
- **< 0.5** → Diferentes (mesmo cluster, mas perfis distintos)

---

## 🎯 Casos Reais de Uso

### **Caso 1: Rebalanceamento de Metas**

**Problema:** Metas iguais para todas as concessionárias.

**Solução:**
```python
resultado = agent.clusterizar_concessionarias(n_clusters=4)

for perfil in resultado["perfis_clusters"]:
    print(f"Cluster {perfil['nome_perfil']}:")
    print(f"  Meta sugerida: R$ {perfil['caracteristicas']['faturamento_medio'] * 1.1:,.2f}")
```

---

### **Caso 2: Transferência de Best Practices**

**Problema:** MATRIZ SP quer melhorar cross-sell.

**Solução:**
```python
analise = agent.analisar_concessionaria("MATRIZ SP")

# Identificar melhor em cross-sell no mesmo cluster
similares = analise['concessionarias_similares']
melhor_cross_sell = max(similares, key=lambda x: x['taxa_cross_sell'])

print(f"Benchmark: {melhor_cross_sell['nome']}")
print(f"Taxa deles: {melhor_cross_sell['taxa_cross_sell']:.1%}")
print(f"Sua taxa: {analise['features_raw']['taxa_cross_sell']:.1%}")
print(f"Gap: {(melhor_cross_sell['taxa_cross_sell'] - analise['features_raw']['taxa_cross_sell']) * 100:.1f}pp")
```

---

### **Caso 3: Identificação de Perfis Emergentes**

**Problema:** Detectar novo padrão operacional.

**Solução:**
```python
# Rodar clustering em 2 períodos diferentes
resultado_atual = agent.clusterizar_concessionarias(periodo_dias=90)
resultado_anterior = agent.clusterizar_concessionarias(periodo_dias=180)

# Comparar distribuição de clusters
# Se surgir novo cluster pequeno → perfil emergente!
```

---

## 🧪 Testes e Validação

### **Validar Qualidade do Clustering**

```python
from sklearn.metrics import davies_bouldin_score, calinski_harabasz_score

# Testar múltiplos valores de n_clusters
for n in range(3, 8):
    resultado = agent.clusterizar(n_clusters=n)
    print(f"n={n}: silhouette={resultado['silhouette_score']:.3f}")

# Escolher o n com melhor score
```

---

## 🔧 Troubleshooting

### **Problema: Todos em um cluster**

**Causa:** Features muito homogêneas ou normalizadas incorretamente.

**Solução:**
```python
# Verificar features antes de normalizar
for f in agent.features_concessionarias:
    print(f.concessionaria, f.faturamento_total, f.ticket_medio)

# Se todas muito parecidas → aumentar período ou refinar features
```

---

### **Problema: Muitos outliers no DBSCAN**

**Causa:** eps (epsilon) muito baixo.

**Solução:**
```python
from sklearn.cluster import DBSCAN

# Tentar eps maiores
for eps in [0.3, 0.5, 0.7, 1.0]:
    dbscan = DBSCAN(eps=eps, min_samples=3)
    labels = dbscan.fit_predict(X_norm)
    print(f"eps={eps}: {len(set(labels))} clusters, {(labels==-1).sum()} outliers")
```

---

## 📚 Referências

- [Scikit-Learn K-Means](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html)
- [Scikit-Learn DBSCAN](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.DBSCAN.html)
- [Silhouette Score](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html)

---

## 🤝 Contribuição

Para adicionar novas features ou melhorar o algoritmo, edite `helpers.py`:

1. Adicione nova feature em `FeaturesConcessionaria`
2. Implemente extração em `extrair_features_concessionarias()`
3. Adicione ao vetor em `to_feature_vector()`
4. Documente no SKILL.md

---

## 📝 Changelog

### v1.0 (2025-03-20)
- ✅ Implementação inicial
- ✅ 15 features operacionais
- ✅ K-Means e DBSCAN
- ✅ Geração automática de perfis
- ✅ Análise comparativa de concessionárias
