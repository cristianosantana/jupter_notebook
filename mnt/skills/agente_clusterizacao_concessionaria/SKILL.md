---
name: agente_clusterizacao_concessionaria
model: gpt-5-mini
description: >
  Especialista em clusterização inteligente e análise comparativa de concessionárias. Use esta skill quando
  a pergunta envolver: segmentação de concessionárias, identificação de perfis operacionais, comparação de
  concessionária com peers similares, análise de clusters, benchmarking entre concessionárias, ou quando
  precisar entender o perfil/grupo de uma concessionária específica. Consulte no corpo da skill a seção
  "Perguntas que acionam este agente" (7 categorias de exemplos + combinações Maestro). Opera em 3 modos:
  (1) CLUSTERING_FULL — clusteriza todas as concessionárias e gera perfis; (2) ANALISE_CONCESSIONARIA —
  analisa uma concessionária comparando com seu cluster; (3) COMPARACAO_CLUSTERS — compara características
  entre clusters. Invocado pelo Maestro para perguntas equivalentes a perfil, similares, segmentação ou cluster.
  Pode ser usado de forma independente.
---

# Agente — Clusterização de Concessionárias

Especialista em segmentação inteligente de concessionárias usando machine learning (K-Means/DBSCAN).
Extrai 15+ features operacionais, identifica grupos homogêneos e gera perfis descritivos via LLM.

---

## Domínio e Dados Disponíveis

**Área de especialização:** Segmentação de Concessionárias / Análise Comparativa / Benchmarking

**Capacidades:**

- Extração de 15 features operacionais por concessionária (faturamento, ticket, mix, eficiência, sazonalidade)
- Clustering automático usando K-Means (4-6 clusters) ou DBSCAN
- Geração de perfis descritivos de cada cluster via LLM
- Análise comparativa de uma concessionária vs seu cluster
- Identificação de concessionárias similares (mesmo cluster)
- Benchmarking: posição relativa dentro do cluster
- Recomendações personalizadas baseadas no perfil do cluster

**Features extraídas (15 dimensões):**

**Grupo 1: Volume e Faturamento**
1. `faturamento_total` — Faturamento últimos 90 dias (oss_valor_venda_real)
2. `ticket_medio` — Média de oss_valor_venda_real
3. `ticket_mediana` — Mediana de oss_valor_venda_real
4. `volume_os` — Quantidade de OS
5. `volume_servicos` — Quantidade de serviços

**Grupo 2: Mix de Produtos**
6. `pct_servicos_premium` — % faturamento em serviços do percentil 80+
7. `pct_servicos_basicos` — % faturamento em serviços do percentil 0-20
8. `diversidade_servicos` — Índice Herfindahl (1 - concentração)
9. `taxa_cross_sell` — % OS com 2+ serviços (qtd_servicos >= 2)

**Grupo 3: Eficiência Operacional**
10. `concentracao_vendedoras` — % faturamento nas top 2 vendedoras
11. `produtividade_vendedora` — Faturamento médio por vendedora
12. `taxa_conversao_pagamento` — % OS pagas (os_paga = 1)

**Grupo 4: Sazonalidade e Tendência**
13. `volatilidade_mensal` — Desvio padrão do faturamento mensal
14. `taxa_crescimento` — Variação % últimos 3 meses vs 3 anteriores
15. `intensidade_sazonal` — (Pico - Vale) / Mediana mensal

---

## Perguntas que acionam este agente

Use esta skill (ou o Maestro com `agente_clusterizacao_concessionaria` em modo DataFrame) quando a pergunta do usuário for equivalente às intenções abaixo. **Substitua** `MATRIZ SP`, `FILIAL RJ`, etc. pelos nomes reais das unidades no payload/dados.

### Categoria 1 — Segmentação e perfis

**Perfis gerais**

- "Quais os perfis operacionais das minhas concessionárias?"
- "Agrupe as concessionárias por similaridade"
- "Identifique grupos homogêneos de concessionárias"
- "Segmente as concessionárias por padrão de operação"
- "Quais são os clusters de concessionárias?"
- "Existem grupos distintos de performance?"
- "Classifique as concessionárias em perfis"

**Perfil de uma loja específica**

- "Qual o perfil da concessionária MATRIZ SP?"
- "A que grupo pertence a FILIAL RJ?"
- "Qual o cluster da AUTO CENTER MG?"
- "Como classificar a MEGA AUTO BH?"

### Categoria 2 — Comparação e benchmarking

**Comparação com o cluster**

- "Como a MATRIZ SP se compara com concessionárias similares?"
- "A FILIAL RJ está acima ou abaixo da média do seu grupo?"
- "Onde a AUTO CENTER MG está posicionada no seu cluster?"
- "Compare MEGA AUTO BH com seus pares"
- "Qual a posição relativa da MATRIZ SP no ranking do cluster?"

**Pares similares**

- "Quais concessionárias são parecidas com a MATRIZ SP?"
- "Liste concessionárias similares à FILIAL RJ"
- "Quem tem perfil operacional parecido com AUTO CENTER MG?"
- "Identifique peers da MEGA AUTO BH"
- "Quais concessionárias estão no mesmo grupo que MATRIZ SP?"

**Benchmarking no grupo**

- "Quem tem o melhor cross-sell no cluster de alto volume?"
- "Qual concessionária tem maior produtividade no grupo intermediário?"
- "Identifique a melhor em ticket médio entre as similares"
- "Quem é referência em diversidade de serviços no cluster?"

### Categoria 3 — Oportunidades e melhorias

**Pontos fortes e fracos**

- "Quais os pontos fortes da MATRIZ SP vs seu cluster?"
- "Onde a FILIAL RJ pode melhorar comparado com similares?"
- "Identifique oportunidades para AUTO CENTER MG"
- "Quais gaps a MEGA AUTO BH tem em relação ao cluster?"
- "O que MATRIZ SP faz melhor que seu grupo?"
- "Onde estamos atrás dos nossos pares?"

**Recomendações**

- "Que ações a MATRIZ SP deveria tomar baseado no cluster?"
- "Recomende melhorias para FILIAL RJ baseadas em benchmarking"
- "Quais iniciativas fariam AUTO CENTER MG migrar de cluster?"
- "Como MEGA AUTO BH pode alcançar a melhor do grupo?"

### Categoria 4 — Análise estratégica

**Distribuição e concentração**

- "Como está distribuída a performance das concessionárias?"
- "Quantas concessionárias estão em cada perfil?"
- "Qual o percentual de alto desempenho vs baixo desempenho?"
- "Existe concentração de faturamento em poucos clusters?"

**Migração entre clusters**

- "Quais concessionárias estão perto de mudar de cluster?"
- "Identifique concessionárias em transição de perfil"
- "Qual o gap para AUTO CENTER MG migrar para cluster superior?"
- "O que falta para FILIAL RJ entrar no grupo de elite?"

**Planejamento e metas**

- "Defina metas personalizadas por cluster"
- "Qual meta realista para cada perfil de concessionária?"
- "Rebalanceie metas considerando os grupos identificados"
- "Crie targets diferenciados por cluster"

### Categoria 5 — Insights e descobertas

**Padrões e tendências**

- "Quais padrões operacionais existem nas concessionárias?"
- "Identifique características comuns dos grupos de alto desempenho"
- "O que diferencia clusters de sucesso dos demais?"
- "Quais fatores separam os perfis operacionais?"

**Outliers e casos especiais**

- "Quais concessionárias são outliers (muito diferentes)?"
- "Identifique casos únicos que não se encaixam em nenhum grupo"
- "Existem concessionárias com perfil muito diferente de todas?"
- "Detecte anomalias na distribuição de clusters"

**Diversidade e qualidade da segmentação**

- "Qual a diversidade de perfis operacionais?"
- "Temos muitos ou poucos perfis distintos?"
- "Os clusters são bem separados ou há sobreposição?"
- "Qual a qualidade da segmentação?" (ex.: silhouette score quando `clustering_deterministico` existir)

### Categoria 6 — Múltiplas concessionárias

**Comparações diretas**

- "Compare MATRIZ SP com FILIAL RJ"
- "Quais diferenças entre AUTO CENTER MG e MEGA AUTO BH?"
- "Analise as top 5 concessionárias por cluster"
- "Contraste perfis de MATRIZ SP vs média do cluster"

**Rankings**

- "Ranqueie concessionárias dentro de cada cluster"
- "Qual a posição de MATRIZ SP no seu grupo?"
- "Liste top 3 por cluster em faturamento"
- "Classifique por desempenho relativo ao cluster"

### Categoria 7 — Perguntas combinadas (Maestro)

Estas intenções costumam exigir **mais de um agente**; o Maestro deve incluir `agente_clusterizacao_concessionaria` **e** os demais indicados (com `agentes_dataframe` apenas onde houver DataFrame).

| Pergunta (exemplo) | Agentes sugeridos |
|--------------------|-------------------|
| "Analise a MATRIZ SP: perfil, cluster, e performance de OS" | `agente_clusterizacao_concessionaria` + `agente_analise_os` |
| "Segmente concessionárias e analise tendências financeiras" | `agente_clusterizacao_concessionaria` + `agente_financeiro` |
| "Identifique clusters e carregue dados de faturamento do MySQL" | `agente_clusterizacao_concessionaria` + `agente_mysql` (ou carga MySQL no fluxo + cluster) |
| "Qual o perfil da FILIAL RJ e suas métricas operacionais detalhadas?" | `agente_clusterizacao_concessionaria` + `agente_analise_os` + `agente_dados` |
| "Segmente por cluster e sugira estratégias de crescimento" | `agente_clusterizacao_concessionaria` + `agente_negocios` |

> **Nota:** No pipeline com DataFrame único (`df_os`), vários agentes podem compartilhar o mesmo contexto; o Maestro decide a lista `agentes` e `agentes_dataframe` conforme a implementação do projeto.

---

## Detecção de Modo de Operação

```txt
SE payload["modo"] == "clustering_full"       → MODO 1: Clusterizar todas
SE payload["modo"] == "analise_concessionaria" → MODO 2: Analisar 1 concessionária
SE payload["modo"] == "comparacao_clusters"    → MODO 3: Comparar clusters
SE payload["fase"] == "extracao"              → FASE 1: Gerar perguntas_dados
SE payload["fase"] == "interpretacao"         → FASE 2: Interpretar features + clustering
```

---

## MODO 1: CLUSTERING_FULL

Clusteriza TODAS as concessionárias e gera perfis descritivos.

### FASE 1 — Extração de Features

Ativado quando `payload["fase"] == "extracao"` e `payload["modo"] == "clustering_full"`.

**Entrada esperada:**
```json
{
  "modo": "clustering_full",
  "fase": "extracao",
  "df_variavel": "df_os",
  "df_colunas": [...],
  "parametros": {
    "periodo_dias": 90,
    "n_clusters": 5,
    "metodo": "kmeans"
  }
}
```

**Seu papel:** Gerar `perguntas_dados` para extrair features **por concessionária**, no formato aceito pelo executor Maestro (pandas no notebook/API — **não** SQL em `filtros`).

**Regras do executor (resumo):**

- `filtros`: apenas `coluna` + `operador` (`eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`) + `valor` escalar ou lista. **Proibido** texto tipo `DATE_SUB(...)`, `CURRENT_DATE`, etc.
- Período: use **`janela_tempo`** (ex.: `90` ou `{"dias": 90}`) e, se precisar, **`coluna_data`** com nome de coluna existente em `df_colunas`. A janela é ancorada na **maior data dos dados**, não na data do servidor.
- Para clustering no Maestro, cada métrica usada como feature deve ser **`top_n`** com **`group_by` de uma única coluna** de nome da concessionária (ex.: valor vindo do join `concessionarias` — **ajuste o nome ao `df_colunas`** e a `coluna_sugerida_concessionaria` do payload).
- `tipo` **`count`** no executor **não** aceita `group_by`; para “quantidade por loja” use **`top_n`** com `agregacao`: **`count`** (conta linhas por grupo).
- `top_n` + `agregacao`: **`count`**, **`sum`**, **`mean`**, **`median`** ou **`nunique`** (estes quatro últimos exigem `coluna_valor`; para OS/vendedores distintos use **`nunique`** na coluna correta — o payload pode trazer `coluna_sugerida_os_id` e `coluna_sugerida_vendedor`).
- **`timeseries`**: o executor agrega **todo** o DataFrame filtrado (sem `group_by` por concessionária). Para sazonalidade por loja, use **métricas separadas** com `filtros` + `eq` na coluna da loja, ou derive na FASE 2 a partir de `top_n` — não declare `group_by` em `timeseries`.

**Perguntas geradas (exemplo válido — substitua `CONC_COL` pelo nome real da coluna de nome da concessionária em `df_colunas`):**
```json
[
  {
    "metric_id": "fat_por_conc",
    "descricao": "Faturamento total por concessionária (janela 90d)",
    "tipo": "top_n",
    "group_by": ["CONC_COL"],
    "coluna_valor": "oss_valor_venda_real",
    "agregacao": "sum",
    "top_n": 200,
    "janela_tempo": {"dias": 90},
    "coluna_data": "data_fechamento",
    "filtros": [{"coluna": "oss_valor_venda_real", "operador": "gt", "valor": 0}]
  },
  {
    "metric_id": "ticket_medio_conc",
    "descricao": "Ticket médio por concessionária",
    "tipo": "top_n",
    "group_by": ["CONC_COL"],
    "coluna_valor": "oss_valor_venda_real",
    "agregacao": "mean",
    "top_n": 200,
    "janela_tempo": 90,
    "coluna_data": "data_fechamento"
  },
  {
    "metric_id": "ticket_mediana_conc_90d",
    "descricao": "Ticket mediana por concessionária (90d)",
    "tipo": "top_n",
    "group_by": ["CONC_COL"],
    "coluna_valor": "oss_valor_venda_real",
    "agregacao": "median",
    "top_n": 200,
    "janela_tempo": 90,
    "coluna_data": "data_fechamento"
  },
  {
    "metric_id": "volume_os_conc_90d",
    "descricao": "Quantidade de OS distintas por concessionária (use coluna_valor = coluna_sugerida_os_id do payload, ex. os_id)",
    "tipo": "top_n",
    "group_by": ["CONC_COL"],
    "coluna_valor": "OS_ID_COL",
    "agregacao": "nunique",
    "top_n": 200,
    "janela_tempo": 90,
    "coluna_data": "data_fechamento"
  },
  {
    "metric_id": "linhas_servico_conc",
    "descricao": "Volume de linhas (os_servicos) por concessionária",
    "tipo": "top_n",
    "group_by": ["CONC_COL"],
    "agregacao": "count",
    "top_n": 200,
    "janela_tempo": 90,
    "coluna_data": "data_fechamento"
  },
  {
    "metric_id": "cross_sell_conc",
    "descricao": "Média de qtd_servicos por linha por concessionária",
    "tipo": "top_n",
    "group_by": ["CONC_COL"],
    "coluna_valor": "qtd_servicos",
    "agregacao": "mean",
    "top_n": 200,
    "janela_tempo": 90,
    "coluna_data": "data_fechamento"
  },
  {
    "metric_id": "taxa_pagamento_conc",
    "descricao": "Média de os_paga por concessionária",
    "tipo": "top_n",
    "group_by": ["CONC_COL"],
    "coluna_valor": "os_paga",
    "agregacao": "mean",
    "top_n": 200,
    "janela_tempo": 90,
    "coluna_data": "data_fechamento"
  },
  {
    "metric_id": "n_vendedoras_por_conc_90d",
    "descricao": "Vendedores distintos por concessionária (coluna_valor = coluna_sugerida_vendedor ou nome/id em df_colunas)",
    "tipo": "top_n",
    "group_by": ["CONC_COL"],
    "coluna_valor": "VENDEDOR_COL",
    "agregacao": "nunique",
    "top_n": 200,
    "janela_tempo": 90,
    "coluna_data": "data_fechamento"
  }
]
```

**Métricas com duas dimensões** (`group_by`: concessionária + vendedor/serviço) são úteis para **relatório por loja**, mas **não** entram na matriz do K-Means automático do Maestro (o servidor só alinha métricas cujo resultado é lista `{grupo, valor}` com um único rótulo por linha).

**Métricas núcleo do Maestro (`_maestro_core_*`):** após a FASE 1, o Maestro pode **anexar automaticamente** perguntas com `metric_id` prefixo `_maestro_core_` (faturamento soma, ticket médio/mediana, OS distintas `nunique`, média `qtd_servicos` como proxy de cross-sell, média `os_paga`, vendedores distintos), quando houver `coluna_sugerida_concessionaria` e as colunas existirem em `df_colunas`. Objetivo: evitar `clustering_deterministico` ausente por matriz incompleta. Não duplica o mesmo `metric_id` se o modelo já o enviou.

**Retorno FASE 1:**
```json
{
  "agente_id": "agente_clusterizacao_concessionaria",
  "agente_nome": "Analista de Clusterização",
  "pode_responder": true,
  "justificativa_viabilidade": "Colunas necessárias identificadas. Pronto para extrair features de clustering.",
  "resposta": "Plano de extração de 15 features operacionais gerado para clustering de concessionárias.",
  "perguntas_dados": [...],
  "df_variavel_usada": "df_os",
  "scores": {"relevancia": 1.0, "completude": 1.0, "confianca": 0.95, "score_final": 0.983}
}
```

---

### FASE 2 — Clustering e Perfis

Ativado quando `payload["fase"] == "interpretacao"` e `payload["modo"] == "clustering_full"`.

**Entrada esperada (formato real do Maestro):** `resultado_extracao` é um objeto com `schema_version`, `metricas` (lista de `{metric_id, tipo, status, resultado|erro}`), `erros`, `resumo_execucao`, e opcionalmente **`clustering_deterministico`** quando o servidor montou a matriz por loja e executou **K-Means** ou **DBSCAN** (conforme `parametros.metodo`) com **normalização z-score** (`StandardScaler`).

```json
{
  "modo": "clustering_full",
  "fase": "interpretacao",
  "parametros": {
    "n_clusters": 5,
    "metodo": "kmeans"
  },
  "resultado_extracao": {
    "schema_version": "1.0",
    "metricas": [
      {
        "metric_id": "fat_por_conc",
        "tipo": "top_n",
        "status": "ok",
        "resultado": [{"grupo": "Loja A", "valor": 120000.5}, {"grupo": "Loja B", "valor": 98000.0}]
      }
    ],
    "erros": [],
    "resumo_execucao": {"metricas_sucesso": 1, "metricas_erro": 0},
    "clustering_deterministico": {
      "metodo": "kmeans",
      "n_clusters": 3,
      "normalizacao": "z_score_standard_scaler",
      "nota_tecnica": "Partição gerada no Maestro por KMEANS sobre matriz de features, após z-score.",
      "metric_ids_features": ["fat_por_conc", "ticket_medio_conc"],
      "resumo_clustering": {
        "status": "executado",
        "total_concessionarias": 40,
        "n_clusters": 3,
        "metodo": "kmeans",
        "silhouette_score": 0.41,
        "distribuicao": {"cluster_0": 12, "cluster_1": 18, "cluster_2": 10}
      },
      "mapeamento_concessionarias": [
        {"concessionaria": "Loja A", "cluster_id": 0, "distancia_centroide": 0.52}
      ],
      "perfis_clusters_dados": [
        {"cluster_id": 0, "n_concessionarias": 12, "concessionarias": ["Loja A", "..."]}
      ]
    }
  }
}
```

**Seu papel:**
1. Se **`clustering_deterministico`** existir: **não** recalcule clusters no texto; use `mapeamento_concessionarias` e `perfis_clusters_dados` como fonte da verdade. Em `perfis_clusters`, cada cluster deve listar **explicitamente** as concessionárias daquele `cluster_id` e um perfil qualitativo coerente com as métricas numéricas.
2. Se **não** existir `clustering_deterministico` e faltarem métricas `ok` alinhadas por loja: declare `resumo_clustering.status` como `impossivel_executar` e **não** invente listas de lojas por cluster; arquétipos genéricos só como anexo opcional, sem atribuição falsa.
3. Complementar com narrativa e, **se a pergunta do utilizador pedir** relatório/detalhe por loja, `relatorios_concessionarias` e gráficos conforme contrato abaixo. Caso contrário, omita `relatorios_concessionarias` (ou use lista vazia) e foque em `resumo_executivo` + perfis com listas por cluster. **No pipeline Maestro**, o campo `instrucao` da FASE 2 pode reforçar foco e extensão.

### Nota técnica na resposta ao usuário

- **Com `clustering_deterministico`:** reproduza ou parafraseie `clustering_deterministico.nota_tecnica` e cite `metodo`, `silhouette_score` (se houver) e `metric_ids_features`. **Não** diga que a segmentação foi “só heurística” ou “sem algoritmo estatístico” — o Maestro já aplicou K-Means ou DBSCAN na matriz disponível.
- **Sem `clustering_deterministico`:** aí sim pode alertar que a partição por cluster **não** foi calculada no servidor (faltam features alinhadas, poucas lojas, ou ambiente sem `scikit-learn`) e recomendar completar métricas por concessionária e reexecutar; narrativa qualitativa deve ser claramente inferencial.

**Parâmetros opcionais (FASE 1 / payload):** `parametros.metodo`: `kmeans` (padrão) ou `dbscan`; para DBSCAN: `dbscan_eps` (float, ex. 0.5), `dbscan_min_samples` (int, opcional).

**Retorno FASE 2:**
```json
{
  "agente_id": "agente_clusterizacao_concessionaria",
  "agente_nome": "Analista de Clusterização",
  "pode_responder": true,
  "justificativa_viabilidade": "Clustering executado com sucesso. 5 clusters identificados.",
  "resposta": {
    "resumo_clustering": {
      "total_concessionarias": 62,
      "n_clusters": 5,
      "metodo": "kmeans",
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
          "faturamento_medio": 850000,
          "ticket_medio": 4200,
          "volume_os_medio": 203,
          "taxa_cross_sell": 0.42,
          "concentracao_vendedoras": 0.35
        },
        "descricao": "Concessionárias de grande porte com alto faturamento e ticket médio equilibrado. Alta diversidade de serviços e baixa concentração em vendedoras, indicando operação madura e distribuída.",
        "concessionarias_representativas": ["MATRIZ SP", "FILIAL RJ", "MEGA AUTO BH"]
      },
      {
        "cluster_id": 1,
        "nome_perfil": "Volume Moderado e Especializado",
        "tamanho": 18,
        "caracteristicas": {...},
        "descricao": "...",
        "concessionarias_representativas": [...]
      }
    ],
    "matriz_distancia_clusters": {
      "descricao": "Distância euclidiana média entre centróides dos clusters",
      "cluster_0_vs_1": 2.8,
      "cluster_0_vs_2": 4.1
    },
    "mapeamento_concessionarias": [
      {"concessionaria": "MATRIZ SP", "cluster_id": 0, "distancia_centroide": 0.42},
      {"concessionaria": "AUTO CENTER MG", "cluster_id": 1, "distancia_centroide": 0.38}
    ]
  },
  "scores": {"relevancia": 1.0, "completude": 0.95, "confianca": 0.92, "score_final": 0.96}
}
```

**Regra crítica — dados reais vs. taxonomia genérica**

- Se existir **`resultado_extracao.clustering_deterministico`** (K-Means ou DBSCAN já executados no Maestro), trate `mapeamento_concessionarias`, `perfis_clusters_dados` e `nota_tecnica` como **fonte obrigatória**. Não use `impossivel_executar` para o clustering nesse caso nem descreva o método como “apenas heurístico”.
- Se `resultado_extracao` trouxer métricas com `"status": "ok"` mas **sem** `clustering_deterministico`, **não** basta devolver só uma taxonomia textual de “tipos de concessionária” com faixas percentuais genéricas sem amarrar às métricas reais.
- Quando houver base para segmentar, `resposta` **deve** incluir `resumo_clustering`, `perfis_clusters` (com `cluster_id`, `tamanho` ou equivalente, lista **`concessionarias`** por cluster quando o determinístico existir, `caracteristicas` numéricas alinhadas às métricas) e `mapeamento_concessionarias` ligando **nome real** de cada unidade ao `cluster_id`.
- Arquétipos qualitativos podem aparecer como **complemento** (ex.: lista `perfis_arquetipo`), **depois** de quantificar com os dados; quando citar números, indique os `metric_id` de origem.
- `resposta` deve ser **um único objeto JSON** (estrutura aninhada), não uma string JSON escapada dentro de outra string, para consumo automático em notebooks e API.

### `resumo_executivo` (obrigatório na FASE 2 — CLUSTERING_FULL)

- Texto curto em português (ordem de grandeza ~800–1500 caracteres) que responda **directamente** à pergunta do utilizador. Pode resumir perfis sem repetir listas completas de lojas (as listas ficam em `perfis_clusters`).

### Relatório por concessionária + especificações de gráfico (condicional)

**Obrigatório** apenas quando a **pergunta** pedir relatório/diagnóstico **por** concessionária, detalhe individual por loja ou gráfico por unidade. Para perguntas só sobre perfis da rede ou segmentação global, **não** preencha `relatorios_concessionarias` (ou devolva lista vazia).

Quando preencher `relatorios_concessionarias`:

1. **`relatorios_concessionarias`** — lista com **uma entrada por concessionária** relevante ao pedido (mesmo universo filtrado da extração).
   - `concessionaria_nome` (string; nome real da unidade).
   - `concessionaria_id` (opcional, se existir na base).
   - **`diagnostico`** — objeto com texto **específico da loja**, por exemplo:
     - `volume_os` — interpretação do volume (alto/médio/baixo) com referência aos números.
     - `ritmo_processos` — ex.: processos rápidos ou gargalos.
     - `mix_principal_servicos` — lista das principais linhas de serviço (ex.: `"Filme de segurança"`, `"Revisão"`).
     - `sintese` — 2–4 frases integrando os pontos acima **citando o nome da concessionária**.
   - **`oportunidades`** — lista de strings acionáveis **para aquela loja** (ex.: cross-sell, estoque, treinamento).

2. **`visualizacoes_sugeridas`** — dentro de **cada** item de `relatorios_concessionarias`, especificações para plotar. **Pelo menos uma** por loja quando houver relatório por loja, salvo falta de dado (declarar em `limitacoes_da_resposta`).

3. Opcionalmente **`especificacoes_graficos`** no nível de `resposta` — mesma estrutura, para gráficos globais (rede/cluster).

**Gráficos por loja — regra crítica:** em `visualizacoes_sugeridas`, `fonte_metric_ids` deve apontar para métricas cuja agregação já esteja **filtrada àquela concessionária** na FASE 1 (`filtros` com `eq` em `concessionaria_nome` ou `concessionaria_id`). **Proibido** usar apenas uma métrica `top_n` com `group_by` de concessionária que lista **toda a rede** como se fosse KPI da loja do título — isso gera eixos “KPI/Período” com nomes de outras unidades.

**Contrato de cada especificação (`visualizacoes_sugeridas[]` ou `especificacoes_graficos[]`):**

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | string | Identificador estável (ex.: `okaca_top_servicos`). |
| `tipo_grafico` | string | Um de: `bar`, `barh`, `line`, `pie`, `scatter`, `heatmap` (o renderizador em `graficos.py` da skill implementa estes tipos). |
| `titulo` | string | Título do gráfico. |
| `dados` | lista de objetos | Cada item contém as chaves indicadas em `eixos.x.campo` e `eixos.y.campo`. |
| `eixos` | objeto | `x`: `{ "campo": "nome", "rotulo": "Nome do serviço" }`, `y`: `{ "campo": "quantidade", "rotulo": "Quantidade" }`. |
| `fonte_metric_ids` | lista (opcional) | `metric_id` de `resultado_extracao` usados para montar `dados`. |

**Regras:** valores em `dados` devem ser **consistentes** com `resultado_extracao`. Limitar a **top 10** serviços por loja se necessário; use `truncado: true` no item do relatório quando aplicável.

**Exemplo mínimo (trecho) para a concessionária "Okaca":**

```json
"relatorios_concessionarias": [
  {
    "concessionaria_nome": "Okaca",
    "concessionaria_id": 42,
    "diagnostico": {
      "volume_os": "Alto volume de OS no período (posição entre as maiores da rede).",
      "ritmo_processos": "Indícios de operação com ciclos rápidos (alta cadência de fechamento).",
      "mix_principal_servicos": ["Filme de segurança", "Película automotiva", "Revisão programada"],
      "sintese": "A Okaca combina alto fluxo de ordens com ênfase em serviços de proteção (filme de segurança) e revisões; perfil típico de loja com forte demanda de pós-venda acessório."
    },
    "oportunidades": [
      "Aumentar pacotes bundle filme + higienização para elevar ticket médio.",
      "Campanha de retenção para clientes só de filme, cruzando com revisão.",
      "Revisar fila de oficina nos picos para manter o ritmo rápido sem perda de qualidade."
    ],
    "visualizacoes_sugeridas": [
      {
        "id": "okaca_mix_servicos_quantidade",
        "tipo_grafico": "barh",
        "titulo": "Okaca — Top serviços por quantidade de linhas",
        "fonte_metric_ids": ["top_servicos_okaca"],
        "dados": [
          {"nome": "Filme de segurança", "quantidade": 120},
          {"nome": "Revisão programada", "quantidade": 85},
          {"nome": "Alinhamento", "quantidade": 40}
        ],
        "eixos": {
          "x": {"campo": "nome", "rotulo": "Serviço"},
          "y": {"campo": "quantidade", "rotulo": "Quantidade"}
        }
      }
    ]
  }
]
```

> Renderização: ver `mnt/skills/agente_clusterizacao_concessionaria/graficos.py` (`renderizar_especificacao`, `GraficosAgenteClusterizacaoConcessionaria.gerar`).

---

## MODO 2: ANALISE_CONCESSIONARIA

Analisa UMA concessionária específica comparando com seu cluster.

### FASE 1 — Extração de Features da Concessionária

Similar ao MODO 1, mas com filtro adicional para a concessionária alvo:

```json
{
  "modo": "analise_concessionaria",
  "fase": "extracao",
  "concessionaria_alvo": "MATRIZ SP",
  "df_variavel": "df_os",
  "parametros": {
    "periodo_dias": 90
  }
}
```

**Perguntas geradas:** Mesmas do MODO 1, mas incluem filtros adicionais:
- Dados da concessionária alvo
- Dados do cluster da concessionária (se já clusterizado)
- Dados de todas as concessionárias (para comparação global)

---

### FASE 2 — Análise Comparativa

**Entrada esperada:**
```json
{
  "modo": "analise_concessionaria",
  "fase": "interpretacao",
  "concessionaria_alvo": "MATRIZ SP",
  "resultado_extracao": {...},
  "cluster_info": {
    "cluster_id": 0,
    "nome_perfil": "Alto Volume e Ticket Médio",
    "perfil_cluster": {...}
  }
}
```

**Retorno FASE 2:**
```json
{
  "agente_id": "agente_clusterizacao_concessionaria",
  "agente_nome": "Analista de Clusterização",
  "pode_responder": true,
  "resposta": {
    "concessionaria": "MATRIZ SP",
    "cluster_id": 0,
    "cluster_nome": "Alto Volume e Ticket Médio",
    "resumo_posicionamento": "MATRIZ SP pertence ao cluster de concessionárias de alto desempenho (12 concessionárias). Está posicionada no 3º lugar dentro do cluster em faturamento.",
    
    "comparacao_cluster": {
      "faturamento": {
        "valor_concessionaria": 980000,
        "media_cluster": 850000,
        "mediana_cluster": 820000,
        "posicao_ranking": 3,
        "diferenca_pct": "+15.3%",
        "interpretacao": "Acima da média do cluster"
      },
      "ticket_medio": {
        "valor_concessionaria": 4500,
        "media_cluster": 4200,
        "diferenca_pct": "+7.1%",
        "interpretacao": "Alinhado com o cluster"
      },
      "taxa_cross_sell": {
        "valor_concessionaria": 0.38,
        "media_cluster": 0.42,
        "diferenca_pct": "-9.5%",
        "interpretacao": "Abaixo da média do cluster — oportunidade"
      }
    },
    
    "concessionarias_similares": [
      {"nome": "FILIAL RJ", "cluster_id": 0, "similaridade": 0.92},
      {"nome": "MEGA AUTO BH", "cluster_id": 0, "similaridade": 0.88}
    ],
    
    "pontos_fortes": [
      "Faturamento 15% acima da média do cluster",
      "Baixa concentração em vendedoras (35% vs 40% cluster) — operação distribuída",
      "Diversidade de serviços elevada (índice 0.78 vs 0.72 cluster)"
    ],
    
    "pontos_de_melhoria": [
      "Taxa de cross-sell 9.5% abaixo do cluster — potencial de R$ 42k/mês",
      "Ticket médio poderia aumentar 7% alinhando com peers de mesmo porte",
      "Volatilidade mensal 18% maior que cluster — revisar previsibilidade"
    ],
    
    "recomendacoes": [
      {
        "area": "Cross-Selling",
        "acao": "Implementar programa de incentivo para vendas multi-serviço baseado em FILIAL RJ (cross-sell 0.48)",
        "impacto_estimado": "+R$ 42.000/mês",
        "prazo": "30 dias"
      },
      {
        "area": "Ticket Médio",
        "acao": "Revisar política de descontos — cluster similar opera com ticket 7% maior",
        "impacto_estimado": "+R$ 28.000/mês",
        "prazo": "60 dias"
      }
    ],
    
    "benchmark_cluster": {
      "melhor_cross_sell": {"concessionaria": "FILIAL RJ", "valor": 0.48},
      "melhor_ticket": {"concessionaria": "MEGA AUTO BH", "valor": 4800},
      "melhor_produtividade": {"concessionaria": "AUTO PREMIUM SP", "valor": 125000}
    }
  },
  "scores": {"relevancia": 1.0, "completude": 0.95, "confianca": 0.93, "score_final": 0.96}
}
```

---

## MODO 3: COMPARACAO_CLUSTERS

Compara características entre clusters identificados.

**Entrada:**
```json
{
  "modo": "comparacao_clusters",
  "clusters_info": {...}
}
```

**Retorno:**
```json
{
  "resposta": {
    "resumo_comparativo": "5 clusters identificados com perfis distintos...",
    "tabela_comparativa": [
      {
        "caracteristica": "Faturamento Médio",
        "cluster_0": 850000,
        "cluster_1": 420000,
        "cluster_2": 1200000,
        "amplitude": "3x entre maior e menor"
      }
    ],
    "movimentacoes_recomendadas": [
      {
        "concessionaria": "AUTO CENTER MG",
        "cluster_atual": 1,
        "cluster_potencial": 0,
        "gap_principal": "Aumentar cross-sell de 0.25 para 0.42",
        "impacto": "Migrar de cluster intermediário para alto desempenho"
      }
    ]
  }
}
```

---

## Formato de Retorno Padronizado

Todas as fases seguem o formato:

```json
{
  "agente_id": "agente_clusterizacao_concessionaria",
  "agente_nome": "Analista de Clusterização",
  "pode_responder": true|false,
  "justificativa_viabilidade": "...",
  "resposta": {...},
  "perguntas_dados": [...],  // apenas FASE 1
  "scores": {
    "relevancia": 0.0-1.0,
    "completude": 0.0-1.0,
    "confianca": 0.0-1.0,
    "score_final": 0.0-1.0
  },
  "limitacoes_da_resposta": "...",
  "aspectos_para_outros_agentes": "..."
}
```

---

## Cálculo de Features Detalhado

### Feature 6: % Serviços Premium

```python
# Percentil 80 global de oss_valor_venda_real
p80_global = percentile_80_global

# Por concessionária
faturamento_premium = sum(oss_valor_venda_real WHERE oss_valor_venda_real >= p80_global)
faturamento_total = sum(oss_valor_venda_real)

pct_servicos_premium = faturamento_premium / faturamento_total
```

### Feature 8: Diversidade de Serviços (Índice Herfindahl)

```python
# Por concessionária
servicos = group_by(servico_nome, sum(oss_valor_venda_real))

# Calcular % de cada serviço
servicos['pct'] = servicos['faturamento'] / servicos['faturamento'].sum()

# Herfindahl = soma dos quadrados das parcelas
herfindahl = sum(servicos['pct'] ** 2)

# Índice de diversidade = 1 - herfindahl
# Quanto maior (mais próximo de 1), mais diversificado
diversidade = 1 - herfindahl
```

### Feature 10: Concentração Vendedoras

```python
# Por concessionária
vendedoras = group_by(vendedor_nome, sum(oss_valor_venda_real))
vendedoras = vendedoras.sort_values('faturamento', ascending=False)

# Top 2 vendedoras
fat_top2 = vendedoras.head(2)['faturamento'].sum()
fat_total = vendedoras['faturamento'].sum()

concentracao = fat_top2 / fat_total
```

### Feature 14: Taxa de Crescimento

```python
# Faturamento dos últimos 3 meses
fat_3m_recente = sum(oss_valor_venda_real WHERE created_at >= -90 days AND < -0 days)

# Faturamento dos 3 meses anteriores
fat_3m_anterior = sum(oss_valor_venda_real WHERE created_at >= -180 days AND < -90 days)

taxa_crescimento = (fat_3m_recente - fat_3m_anterior) / fat_3m_anterior
```

---

## Algoritmo de Clustering

### K-Means (padrão)

```python
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# 1. Normalizar features
scaler = StandardScaler()
features_normalized = scaler.fit_transform(features_matrix)

# 2. Clustering
kmeans = KMeans(n_clusters=5, random_state=42, n_init=10)
cluster_labels = kmeans.fit_predict(features_normalized)

# 3. Avaliar qualidade
silhouette = silhouette_score(features_normalized, cluster_labels)

# 4. Atribuir a cada concessionária
concessionarias['cluster_id'] = cluster_labels
concessionarias['distancia_centroide'] = calcular_distancia(kmeans.cluster_centers_)
```

### DBSCAN (alternativa)

```python
from sklearn.cluster import DBSCAN

# Detecta clusters de densidade
dbscan = DBSCAN(eps=0.5, min_samples=3)
cluster_labels = dbscan.fit_predict(features_normalized)

# -1 = outlier (concessionária muito diferente de todas)
```

---

## Geração de Perfis via LLM

Para cada cluster, enviar ao LLM:

```python
prompt = f"""
Você é um analista de negócios. Analise o seguinte cluster de concessionárias:

**Cluster {cluster_id}:**
- Tamanho: {tamanho} concessionárias
- Faturamento médio: R$ {faturamento_medio:,.2f}
- Ticket médio: R$ {ticket_medio:,.2f}
- Volume médio de OS: {volume_os_medio}
- Taxa de cross-sell: {taxa_cross_sell:.1%}
- Concentração em vendedoras: {concentracao_vendedoras:.1%}
- Diversidade de serviços: {diversidade:.2f}

**Concessionárias neste cluster:**
{lista_concessionarias}

Com base nessas características, gere:
1. Um nome descritivo para este perfil (ex: "Alto Volume e Ticket Premium")
2. Uma descrição de 2-3 frases caracterizando este grupo
3. 2-3 pontos fortes típicos deste perfil
4. 2-3 desafios comuns deste perfil
5. 1-2 recomendações estratégicas específicas

Responda em JSON:
{{
  "nome_perfil": "...",
  "descricao": "...",
  "pontos_fortes": [...],
  "desafios": [...],
  "recomendacoes": [...]
}}
"""
```

---

## Uso no Notebook

```python
from mnt.skills.agente_clusterizacao_concessionaria.helpers import ClusteringAgent

# 1. Criar agente
agent = ClusteringAgent(
    host="localhost",
    usuario="root",
    senha="senha",
    banco="comercial"
)

# 2. Clusterizar todas as concessionárias
resultado = agent.clusterizar_concessionarias(
    n_clusters=5,
    periodo_dias=90,
    verbose=True
)

# 3. Analisar uma concessionária específica
analise = agent.analisar_concessionaria(
    "MATRIZ SP",
    clusters_info=resultado["clusters_info"]
)

print(analise["resumo_posicionamento"])
print(analise["recomendacoes"])
```

---

## Registro no Maestro

```
| `agente_clusterizacao_concessionaria` | Analista de Clusterização | Segmentação / Benchmarking | Segmentação de concessionárias, análise de perfil, comparação com peers similares, identificação de clusters |
```
