"""
helpers.py — Agente Visualizador de Dados
Lógica de seleção de gráficos baseada em análise de dados
"""

import json
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from enum import Enum


class TipoGrafico(Enum):
    """Tipos de gráficos suportados"""
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"
    BOX_PLOT = "boxplot"
    HEATMAP = "heatmap"


class TipoDado(Enum):
    """Tipos de dados detectados"""
    NUMERICO = "numérico"
    CATEGORICO = "categórico"
    TEMPORAL = "temporal"
    DESCONHECIDO = "desconhecido"


class AnalisadorDados:
    """Analisa características de um dataset"""
    
    def __init__(self, dados: pd.DataFrame):
        self.dados = dados
        self.n_linhas = len(dados)
        self.n_colunas = len(dados.columns)
        self.colunas_info = {}
        self._analisar()
    
    def _analisar(self):
        """Executa análise completa do dataset"""
        for col in self.dados.columns:
            tipo = self._detectar_tipo(col)
            cardinalidade = self.dados[col].nunique()
            nulls = self.dados[col].isnull().sum()
            null_rate = nulls / self.n_linhas
            
            info = {
                "nome": col,
                "tipo": tipo,
                "cardinalidade": cardinalidade,
                "null_count": nulls,
                "null_rate": null_rate,
            }
            
            # Adicionar estatísticas específicas por tipo
            if tipo == TipoDado.NUMERICO:
                info.update({
                    "min": float(self.dados[col].min()),
                    "max": float(self.dados[col].max()),
                    "mean": float(self.dados[col].mean()),
                    "std": float(self.dados[col].std()),
                })
            elif tipo == TipoDado.CATEGRICO:
                info["unicas"] = self.dados[col].unique().tolist()[:10]  # Top 10
            elif tipo == TipoDado.TEMPORAL:
                info["min_data"] = str(self.dados[col].min())
                info["max_data"] = str(self.dados[col].max())
            
            self.colunas_info[col] = info
    
    def _detectar_tipo(self, col: str) -> TipoDado:
        """Detecta tipo de dado da coluna"""
        dtype = self.dados[col].dtype
        
        # Temporal
        if pd.api.types.is_datetime64_any_dtype(dtype):
            return TipoDado.TEMPORAL
        
        # Numérico
        if pd.api.types.is_numeric_dtype(dtype):
            return TipoDado.NUMERICO
        
        # Categórico (strings, objects, etc)
        if pd.api.types.is_string_dtype(dtype) or dtype == 'object':
            # Heurística: se cardinalidade << comprimento, é categórico
            cardinalidade = self.dados[col].nunique()
            if cardinalidade < self.n_linhas * 0.5:
                return TipoDado.CATEGORICO
        
        return TipoDado.DESCONHECIDO
    
    def get_colunas_numericas(self) -> List[str]:
        """Retorna lista de colunas numéricas"""
        return [col for col, info in self.colunas_info.items() 
                if info["tipo"] == TipoDado.NUMERICO]
    
    def get_colunas_categoricas(self) -> List[str]:
        """Retorna lista de colunas categóricas"""
        return [col for col, info in self.colunas_info.items() 
                if info["tipo"] == TipoDado.CATEGORICO]
    
    def get_colunas_temporais(self) -> List[str]:
        """Retorna lista de colunas temporais"""
        return [col for col, info in self.colunas_info.items() 
                if info["tipo"] == TipoDado.TEMPORAL]
    
    def tem_problemas_qualidade(self) -> List[str]:
        """Retorna lista de problemas de qualidade identificados"""
        problemas = []
        
        for col, info in self.colunas_info.items():
            if info["null_rate"] > 0.5:
                problemas.append(f"{col}: {info['null_rate']*100:.1f}% nulls")
            
            if info["tipo"] == TipoDado.CATEGORICO:
                if info["cardinalidade"] > 1000:
                    problemas.append(f"{col}: Cardinalidade muito alta ({info['cardinalidade']})")
        
        return problemas


class SeletorGrafico:
    """Seleciona o tipo de gráfico mais apropriado baseado em análise de dados"""
    
    def __init__(self, analisador: AnalisadorDados):
        self.analisador = analisador
        self.pontuacoes = {}
    
    def selecionar(self) -> Tuple[TipoGrafico, float, str]:
        """
        Seleciona o melhor gráfico para os dados
        Retorna: (tipo_grafico, score_adequacao, justificativa)
        """
        
        # Verificações básicas
        if self.analisador.n_linhas == 0:
            raise ValueError("Dataset vazio")
        
        if self.analisador.n_colunas == 1:
            return self._apenas_uma_coluna()
        
        if self.analisador.n_colunas == 2:
            return self._duas_colunas()
        
        # 3+ colunas
        return self._multiplas_colunas()
    
    def _apenas_uma_coluna(self) -> Tuple[TipoGrafico, float, str]:
        """Estratégia para 1 coluna"""
        col = list(self.analisador.colunas_info.keys())[0]
        info = self.analisador.colunas_info[col]
        
        if info["tipo"] == TipoDado.NUMERICO:
            return (
                TipoGrafico.HISTOGRAM,
                0.85,
                "Apenas 1 coluna numérica → Histogram para visualizar distribuição"
            )
        else:
            return (
                TipoGrafico.BAR,
                0.80,
                "Apenas 1 coluna categórica → Bar Chart com contagem"
            )
    
    def _duas_colunas(self) -> Tuple[TipoGrafico, float, str]:
        """Estratégia para 2 colunas"""
        cols = list(self.analisador.colunas_info.keys())
        info_a, info_b = self.analisador.colunas_info[cols[0]], self.analisador.colunas_info[cols[1]]
        
        tipo_a, tipo_b = info_a["tipo"], info_b["tipo"]
        
        # 2 numéricas
        if tipo_a == TipoDado.NUMERICO and tipo_b == TipoDado.NUMERICO:
            return (
                TipoGrafico.SCATTER,
                0.92,
                "2 variáveis numéricas → Scatter Plot para visualizar correlação"
            )
        
        # 1 categórica + 1 numérica
        if (tipo_a == TipoDado.CATEGORICO and tipo_b == TipoDado.NUMERICO) or \
           (tipo_a == TipoDado.NUMERICO and tipo_b == TipoDado.CATEGORICO):
            
            col_cat = cols[0] if info_a["tipo"] == TipoDado.CATEGORICO else cols[1]
            card = self.analisador.colunas_info[col_cat]["cardinalidade"]
            
            if card <= 50:
                return (
                    TipoGrafico.BAR,
                    0.95,
                    f"1 categórica ({card} valores) + 1 numérica → Bar Chart"
                )
            else:
                return (
                    TipoGrafico.BOX_PLOT,
                    0.85,
                    f"Muitas categorias ({card}) → Box Plot para comparação de grupos"
                )
        
        # 1 temporal + 1 numérica
        if (tipo_a == TipoDado.TEMPORAL and tipo_b == TipoDado.NUMERICO) or \
           (tipo_a == TipoDado.NUMERICO and tipo_b == TipoDado.TEMPORAL):
            return (
                TipoGrafico.LINE,
                0.94,
                "1 série temporal + 1 métrica → Line Chart para tendências"
            )
        
        # 2 categóricas
        if tipo_a == TipoDado.CATEGORICO and tipo_b == TipoDado.CATEGORICO:
            card_a = info_a["cardinalidade"]
            card_b = info_b["cardinalidade"]
            
            if card_a <= 10 and card_b <= 10:
                return (
                    TipoGrafico.HEATMAP,
                    0.88,
                    f"2 categóricas ({card_a}×{card_b}) → Heatmap para padrões"
                )
            else:
                return (
                    TipoGrafico.BAR,
                    0.70,
                    "2 categóricas com cardinalidade alta → Bar Chart de contagem"
                )
        
        # Default
        return (TipoGrafico.BAR, 0.60, "Seleção padrão por falta de padrão claro")
    
    def _multiplas_colunas(self) -> Tuple[TipoGrafico, float, str]:
        """Estratégia para 3+ colunas"""
        cols_num = self.analisador.get_colunas_numericas()
        cols_cat = self.analisador.get_colunas_categoricas()
        cols_temp = self.analisador.get_colunas_temporais()
        
        # Temporal + múltiplas numéricas
        if cols_temp and len(cols_num) >= 1:
            return (
                TipoGrafico.LINE,
                0.93,
                f"1+ série temporal + {len(cols_num)} métrica(s) → Line Chart multi-série"
            )
        
        # 2 categóricas + 1 numérica
        if len(cols_cat) >= 2 and len(cols_num) >= 1:
            card_a = self.analisador.colunas_info[cols_cat[0]]["cardinalidade"]
            card_b = self.analisador.colunas_info[cols_cat[1]]["cardinalidade"]
            
            if card_a <= 10 and card_b <= 10:
                return (
                    TipoGrafico.HEATMAP,
                    0.87,
                    f"Matriz {card_a}×{card_b} + métrica → Heatmap"
                )
        
        # Múltiplas numéricas
        if len(cols_num) >= 2 and len(cols_cat) == 0:
            # Se tem mais de 2 numéricas, poderia ser 3D scatter
            # Por enquanto, retornar bar com múltiplas séries
            return (
                TipoGrafico.BAR,
                0.80,
                f"{len(cols_num)} métricas → Bar Chart com múltiplas séries"
            )
        
        # 1 categórica + múltiplas numéricas
        if len(cols_cat) == 1 and len(cols_num) >= 2:
            card = self.analisador.colunas_info[cols_cat[0]]["cardinalidade"]
            if card <= 50:
                return (
                    TipoGrafico.BAR,
                    0.90,
                    f"1 categórica ({card} valores) + {len(cols_num)} métricas → Bar Chart agrupado"
                )
        
        # Default
        return (TipoGrafico.BAR, 0.65, "Múltiplas colunas → Bar Chart padrão")
    
    def obter_alternativas(self, grafico_selecionado: TipoGrafico, n: int = 3) -> List[Dict[str, Any]]:
        """Retorna gráficos alternativos com seus scores"""
        alternativas = []
        
        # Scoring heurístico simplificado
        scores = {
            TipoGrafico.BAR: 0.75,
            TipoGrafico.LINE: 0.70,
            TipoGrafico.PIE: 0.50,
            TipoGrafico.SCATTER: 0.65,
            TipoGrafico.HISTOGRAM: 0.60,
            TipoGrafico.BOX_PLOT: 0.55,
            TipoGrafico.HEATMAP: 0.70,
        }
        
        for tipo, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            if tipo != grafico_selecionado and len(alternativas) < n:
                alternativas.append({
                    "tipo": tipo.value,
                    "score": score,
                    "quando_usar": self._quando_usar_grafico(tipo)
                })
        
        return alternativas
    
    def _quando_usar_grafico(self, tipo: TipoGrafico) -> str:
        """Retorna dica de quando usar cada tipo de gráfico"""
        dicas = {
            TipoGrafico.BAR: "Comparação entre categorias, fácil de ler.",
            TipoGrafico.LINE: "Tendências ao longo do tempo, padrões de evolução.",
            TipoGrafico.PIE: "Composição, partes de um todo (use com moderação).",
            TipoGrafico.SCATTER: "Correlação entre 2 variáveis contínuas.",
            TipoGrafico.HISTOGRAM: "Distribuição de frequência de uma variável.",
            TipoGrafico.BOX_PLOT: "Comparação de grupos, detecção de outliers.",
            TipoGrafico.HEATMAP: "Padrões em matriz 2D, densidade de valores.",
        }
        return dicas.get(tipo, "")


class GeradorGrafico:
    """Gera código pronto para renderizar gráficos"""
    
    def __init__(self, dados: pd.DataFrame, tipo: TipoGrafico, tema: str = "light"):
        self.dados = dados
        self.tipo = tipo
        self.tema = tema
    
    def gerar(self) -> str:
        """Gera código HTML/JS para o gráfico"""
        if self.tipo == TipoGrafico.BAR:
            return self._gerar_bar()
        elif self.tipo == TipoGrafico.LINE:
            return self._gerar_line()
        elif self.tipo == TipoGrafico.PIE:
            return self._gerar_pie()
        elif self.tipo == TipoGrafico.SCATTER:
            return self._gerar_scatter()
        elif self.tipo == TipoGrafico.HISTOGRAM:
            return self._gerar_histogram()
        else:
            return self._gerar_generico()
    
    def _gerar_bar(self) -> str:
        """Gera Bar Chart em Chart.js"""
        labels = self.dados.iloc[:, 0].astype(str).tolist()
        dataset_configs = []
        
        for col in self.dados.columns[1:]:
            values = self.dados[col].fillna(0).tolist()
            dataset_configs.append(f"""
        {{
            label: '{col}',
            data: {json.dumps(values)},
            backgroundColor: 'rgba(50, 102, 173, 0.6)',
            borderColor: 'rgba(50, 102, 173, 1)',
            borderWidth: 1
        }}""")
        
        datasets = ",".join(dataset_configs)
        
        return f"""<div style="position: relative; width: 100%; height: 300px;">
  <canvas id="chartCanvas"></canvas>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
new Chart(document.getElementById('chartCanvas'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(labels)},
    datasets: [{datasets}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: true }}
    }},
    scales: {{
      y: {{ beginAtZero: true }}
    }}
  }}
}});
</script>"""
    
    def _gerar_line(self) -> str:
        """Gera Line Chart em Chart.js"""
        labels = self.dados.iloc[:, 0].astype(str).tolist()
        dataset_configs = []
        colors = ['#3266ad', '#d4537e', '#639922', '#ba7517']
        
        for idx, col in enumerate(self.dados.columns[1:]):
            values = self.dados[col].fillna(0).tolist()
            color = colors[idx % len(colors)]
            dataset_configs.append(f"""
        {{
            label: '{col}',
            data: {json.dumps(values)},
            borderColor: '{color}',
            backgroundColor: '{color}22',
            borderWidth: 2,
            tension: 0.4,
            fill: true
        }}""")
        
        datasets = ",".join(dataset_configs)
        
        return f"""<div style="position: relative; width: 100%; height: 300px;">
  <canvas id="chartCanvas"></canvas>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
new Chart(document.getElementById('chartCanvas'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(labels)},
    datasets: [{datasets}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: true }}
    }},
    scales: {{
      y: {{ beginAtZero: true }}
    }}
  }}
}});
</script>"""
    
    def _gerar_pie(self) -> str:
        """Gera Pie Chart em Chart.js"""
        labels = self.dados.iloc[:, 0].astype(str).tolist()
        values = self.dados.iloc[:, 1].fillna(0).tolist()
        
        return f"""<div style="position: relative; width: 100%; height: 300px;">
  <canvas id="chartCanvas"></canvas>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
new Chart(document.getElementById('chartCanvas'), {{
  type: 'pie',
  data: {{
    labels: {json.dumps(labels)},
    datasets: [{{
      data: {json.dumps(values)},
      backgroundColor: [
        'rgba(50, 102, 173, 0.8)',
        'rgba(212, 83, 126, 0.8)',
        'rgba(99, 153, 34, 0.8)',
        'rgba(186, 117, 23, 0.8)',
        'rgba(232, 75, 48, 0.8)'
      ]
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'right' }}
    }}
  }}
}});
</script>"""
    
    def _gerar_scatter(self) -> str:
        """Gera Scatter Plot em Chart.js"""
        col1, col2 = self.dados.columns[0], self.dados.columns[1]
        data_points = []
        for _, row in self.dados.iterrows():
            data_points.append({"x": float(row[col1]), "y": float(row[col2])})
        
        return f"""<div style="position: relative; width: 100%; height: 300px;">
  <canvas id="chartCanvas"></canvas>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
new Chart(document.getElementById('chartCanvas'), {{
  type: 'scatter',
  data: {{
    datasets: [{{
      label: '{col1} vs {col2}',
      data: {json.dumps(data_points)},
      backgroundColor: 'rgba(50, 102, 173, 0.6)',
      borderColor: 'rgba(50, 102, 173, 1)'
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: true }}
    }},
    scales: {{
      x: {{ title: {{ display: true, text: '{col1}' }} }},
      y: {{ title: {{ display: true, text: '{col2}' }} }}
    }}
  }}
}});
</script>"""
    
    def _gerar_histogram(self) -> str:
        """Gera Histogram em Chart.js"""
        col = self.dados.columns[0]
        values = self.dados[col].dropna().tolist()
        
        # Gerar bins simples (10 bins)
        import numpy as np
        counts, bins = np.histogram(values, bins=10)
        bin_labels = [f"{bins[i]:.1f}-{bins[i+1]:.1f}" for i in range(len(bins)-1)]
        
        return f"""<div style="position: relative; width: 100%; height: 300px;">
  <canvas id="chartCanvas"></canvas>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
new Chart(document.getElementById('chartCanvas'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps(bin_labels)},
    datasets: [{{
      label: 'Frequência',
      data: {json.dumps(counts.tolist())},
      backgroundColor: 'rgba(99, 153, 34, 0.6)',
      borderColor: 'rgba(99, 153, 34, 1)',
      borderWidth: 1
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    scales: {{
      y: {{ beginAtZero: true }}
    }}
  }}
}});
</script>"""
    
    def _gerar_generico(self) -> str:
        """Gera gráfico genérico padrão"""
        return self._gerar_bar()


class VisualizadorAgente:
    """Classe principal do agente"""
    
    def analisar_e_gerar(self, dados: pd.DataFrame, pergunta_contexto: str = "", 
                        tipo_grafico_preferido: Optional[str] = None,
                        apenas_recomendacao: bool = False,
                        tema: str = "light") -> Dict[str, Any]:
        """
        Analisa dados e gera gráfico automático
        
        Args:
            dados: DataFrame com os dados
            pergunta_contexto: Contexto da pergunta para melhorar seleção
            tipo_grafico_preferido: Força um tipo específico (sobrepõe análise)
            apenas_recomendacao: Se True, apenas retorna recomendação sem gerar código
            tema: "light" ou "dark"
        
        Returns:
            Dict com análise completa e código do gráfico
        """
        
        # Análise
        analisador = AnalisadorDados(dados)
        seletor = SeletorGrafico(analisador)
        
        # Seleção
        if tipo_grafico_preferido:
            tipo_selecionado = TipoGrafico(tipo_grafico_preferido)
            score_adequacao = 0.90  # Assumir bom score se usuário especificou
            justificativa = f"Gráfico forçado pelo usuário: {tipo_grafico_preferido}"
        else:
            tipo_selecionado, score_adequacao, justificativa = seletor.selecionar()
        
        # Geração de código
        codigo_grafico = None
        if not apenas_recomendacao:
            gerador = GeradorGrafico(dados, tipo_selecionado, tema)
            codigo_grafico = gerador.gerar()
        
        # Montagem de resposta
        problemas = analisador.tem_problemas_qualidade()
        
        return {
            "agente_id": "agente_visualizador",
            "agente_nome": "Visualizador de Dados",
            "pode_responder": True,
            "justificativa_viabilidade": f"{dados.shape[0]} linhas, {dados.shape[1]} colunas.",
            "resposta": f"Selecionado: {tipo_selecionado.value.title()}. {justificativa}",
            "tipo_grafico_selecionado": tipo_selecionado.value,
            "score_adequacao": round(score_adequacao, 2),
            "justificativa_selecao": justificativa,
            "alternativas": seletor.obter_alternativas(tipo_selecionado, n=3),
            "analise_dados": {
                "n_linhas": analisador.n_linhas,
                "n_colunas": analisador.n_colunas,
                "colunas": list(analisador.colunas_info.values()),
                "problemas_qualidade": problemas
            },
            "codigo_grafico": codigo_grafico,
            "scripts_necessarios": [
                "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"
            ],
            "scores": {
                "relevancia": 0.95,
                "completude": 0.90 if codigo_grafico else 0.70,
                "confianca": score_adequacao,
                "score_final": round((0.95 * 0.4 + 0.90 * 0.3 + score_adequacao * 0.3), 3)
            },
            "limitacoes_da_resposta": "Gráfico gerado sem validação de valores extremos.",
            "aspectos_para_outros_agentes": "Análise estatística → agente_dados. Interpretação de negócio → agente_negocios."
        }
