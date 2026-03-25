"""
Exemplos de uso do Agente Visualizador
Demonstra os 7 tipos de gráficos com dados reais
"""

import pandas as pd
import json
from helpers import VisualizadorAgente


def exemplo_1_bar_chart():
    """Vendas por mês — Bar Chart"""
    print("\n" + "="*60)
    print("EXEMPLO 1: BAR CHART — Vendas por Mês")
    print("="*60)
    
    dados = pd.DataFrame({
        'mes': ['Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho'],
        'vendas': [1500, 2100, 1800, 2400, 2200, 2800],
        'lucro': [350, 520, 420, 580, 490, 650]
    })
    
    viz = VisualizadorAgente()
    resultado = viz.analisar_e_gerar(
        dados=dados,
        pergunta_contexto="Como evoluíram as vendas?"
    )
    
    print(f"\nGráfico Selecionado: {resultado['tipo_grafico_selecionado']}")
    print(f"Score de Adequação: {resultado['score_adequacao']}")
    print(f"Justificativa: {resultado['justificativa_selecao']}")
    print(f"\nAlternativas:")
    for alt in resultado['alternativas']:
        print(f"  - {alt['tipo']}: {alt['score']} ({alt['quando_usar']})")
    
    return resultado


def exemplo_2_line_chart():
    """Série temporal — Line Chart"""
    print("\n" + "="*60)
    print("EXEMPLO 2: LINE CHART — Série Temporal de Temperatura")
    print("="*60)
    
    dados = pd.DataFrame({
        'data': pd.date_range('2024-01-01', periods=30),
        'temperatura_min': [15, 16, 14, 17, 18, 16, 15, 19, 20, 21, 
                            22, 21, 20, 19, 18, 17, 16, 15, 14, 13,
                            12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
        'temperatura_max': [25, 26, 24, 27, 28, 26, 25, 29, 30, 31,
                            32, 31, 30, 29, 28, 27, 26, 25, 24, 23,
                            22, 23, 24, 25, 26, 27, 28, 29, 30, 31]
    })
    
    viz = VisualizadorAgente()
    resultado = viz.analisar_e_gerar(
        dados=dados,
        pergunta_contexto="Como variou a temperatura ao longo do mês?"
    )
    
    print(f"\nGráfico Selecionado: {resultado['tipo_grafico_selecionado']}")
    print(f"Score de Adequação: {resultado['score_adequacao']}")
    print(f"Justificativa: {resultado['justificativa_selecao']}")
    
    return resultado


def exemplo_3_scatter_plot():
    """Correlação — Scatter Plot"""
    print("\n" + "="*60)
    print("EXEMPLO 3: SCATTER PLOT — Correlação Vendas vs Lucro")
    print("="*60)
    
    dados = pd.DataFrame({
        'vendas': [1500, 2100, 1800, 2400, 2200, 2800, 1600, 2300, 2500, 2900],
        'lucro': [350, 520, 420, 580, 490, 650, 380, 560, 610, 680]
    })
    
    viz = VisualizadorAgente()
    resultado = viz.analisar_e_gerar(
        dados=dados,
        pergunta_contexto="Qual é a correlação entre vendas e lucro?"
    )
    
    print(f"\nGráfico Selecionado: {resultado['tipo_grafico_selecionado']}")
    print(f"Score de Adequação: {resultado['score_adequacao']}")
    print(f"Justificativa: {resultado['justificativa_selecao']}")
    
    return resultado


def exemplo_4_pie_chart():
    """Composição — Pie Chart"""
    print("\n" + "="*60)
    print("EXEMPLO 4: PIE CHART — Composição de Receita")
    print("="*60)
    
    dados = pd.DataFrame({
        'categoria': ['Produto A', 'Produto B', 'Produto C', 'Serviço D'],
        'receita': [35000, 28000, 22000, 15000]
    })
    
    viz = VisualizadorAgente()
    resultado = viz.analisar_e_gerar(
        dados=dados,
        pergunta_contexto="Qual é a proporção de receita por categoria?"
    )
    
    print(f"\nGráfico Selecionado: {resultado['tipo_grafico_selecionado']}")
    print(f"Score de Adequação: {resultado['score_adequacao']}")
    print(f"Justificativa: {resultado['justificativa_selecao']}")
    
    return resultado


def exemplo_5_histogram():
    """Distribuição — Histogram"""
    print("\n" + "="*60)
    print("EXEMPLO 5: HISTOGRAM — Distribuição de Idade")
    print("="*60)
    
    import numpy as np
    dados = pd.DataFrame({
        'idade': np.random.normal(35, 15, 200)
    })
    
    viz = VisualizadorAgente()
    resultado = viz.analisar_e_gerar(
        dados=dados,
        pergunta_contexto="Qual é a distribuição de idade dos clientes?"
    )
    
    print(f"\nGráfico Selecionado: {resultado['tipo_grafico_selecionado']}")
    print(f"Score de Adequação: {resultado['score_adequacao']}")
    print(f"Justificativa: {resultado['justificativa_selecao']}")
    
    return resultado


def exemplo_6_boxplot():
    """Comparação de grupos — Box Plot"""
    print("\n" + "="*60)
    print("EXEMPLO 6: BOX PLOT — Comparação de Salários por Departamento")
    print("="*60)
    
    dados = pd.DataFrame({
        'departamento': ['TI']*20 + ['RH']*20 + ['Vendas']*20 + ['Financeiro']*20,
        'salario': (
            list(np.random.normal(5500, 800, 20)) +
            list(np.random.normal(4500, 600, 20)) +
            list(np.random.normal(4000, 900, 20)) +
            list(np.random.normal(5200, 700, 20))
        )
    })
    
    viz = VisualizadorAgente()
    resultado = viz.analisar_e_gerar(
        dados=dados,
        pergunta_contexto="Como variam os salários entre departamentos?"
    )
    
    print(f"\nGráfico Selecionado: {resultado['tipo_grafico_selecionado']}")
    print(f"Score de Adequação: {resultado['score_adequacao']}")
    print(f"Justificativa: {resultado['justificativa_selecao']}")
    
    return resultado


def exemplo_7_heatmap():
    """Matriz — Heatmap"""
    print("\n" + "="*60)
    print("EXEMPLO 7: HEATMAP — Padrões de Vendas")
    print("="*60)
    
    dados = pd.DataFrame({
        'regiao': ['Norte', 'Sul', 'Leste', 'Oeste'] * 4,
        'trimestre': ['Q1']*4 + ['Q2']*4 + ['Q3']*4 + ['Q4']*4,
        'vendas': [450, 380, 520, 490, 480, 410, 560, 530, 
                   500, 420, 580, 550, 520, 450, 600, 570]
    })
    
    viz = VisualizadorAgente()
    resultado = viz.analisar_e_gerar(
        dados=dados,
        pergunta_contexto="Como se distribuem as vendas por região e trimestre?"
    )
    
    print(f"\nGráfico Selecionado: {resultado['tipo_grafico_selecionado']}")
    print(f"Score de Adequação: {resultado['score_adequacao']}")
    print(f"Justificativa: {resultado['justificativa_selecao']}")
    
    return resultado


def exemplo_preferencia_forcada():
    """Forçar um tipo de gráfico"""
    print("\n" + "="*60)
    print("EXEMPLO AVANÇADO: Forçar tipo de gráfico")
    print("="*60)
    
    dados = pd.DataFrame({
        'mes': ['Jan', 'Fev', 'Mar', 'Abr'],
        'vendas': [1000, 1500, 1200, 1800]
    })
    
    viz = VisualizadorAgente()
    
    # Tentar forçar um tipo diferente do recomendado
    resultado = viz.analisar_e_gerar(
        dados=dados,
        tipo_grafico_preferido='pie',
        pergunta_contexto="Mostre as vendas em Pizza (mesmo que seja estranho)"
    )
    
    print(f"\nGráfico Selecionado: {resultado['tipo_grafico_selecionado']}")
    print(f"Justificativa: {resultado['justificativa_selecao']}")
    print(f"\nObservação: Score reduzido por tipo forçado")
    
    return resultado


def exemplo_apenas_recomendacao():
    """Apenas gerar recomendação, sem código"""
    print("\n" + "="*60)
    print("EXEMPLO AVANÇADO: Apenas Recomendação")
    print("="*60)
    
    dados = pd.DataFrame({
        'categoria': ['A', 'B', 'C', 'D', 'E'],
        'valor1': [100, 150, 120, 180, 160],
        'valor2': [200, 180, 220, 150, 190]
    })
    
    viz = VisualizadorAgente()
    resultado = viz.analisar_e_gerar(
        dados=dados,
        apenas_recomendacao=True
    )
    
    print(f"\nGráfico Recomendado: {resultado['tipo_grafico_selecionado']}")
    print(f"Score: {resultado['score_adequacao']}")
    print(f"Código Gerado: {resultado['codigo_grafico'] is not None}")
    print(f"(False = apenas recomendação, sem código)")
    
    return resultado


def exemplo_analise_completa():
    """Exemplo com análise detalhada"""
    print("\n" + "="*60)
    print("EXEMPLO DETALHADO: Análise Completa")
    print("="*60)
    
    dados = pd.DataFrame({
        'semana': ['Sem 1', 'Sem 2', 'Sem 3', 'Sem 4'],
        'trafego': [5000, 6200, 5800, 7100],
        'conversoes': [150, 180, 165, 210],
        'ctr': [3.0, 2.9, 2.8, 3.0]
    })
    
    viz = VisualizadorAgente()
    resultado = viz.analisar_e_gerar(dados=dados)
    
    print(f"\n📊 SELEÇÃO")
    print(f"  Tipo: {resultado['tipo_grafico_selecionado']}")
    print(f"  Score: {resultado['score_adequacao']}")
    print(f"  Motivo: {resultado['justificativa_selecao']}")
    
    print(f"\n📈 ANÁLISE DE DADOS")
    print(f"  Linhas: {resultado['analise_dados']['n_linhas']}")
    print(f"  Colunas: {resultado['analise_dados']['n_colunas']}")
    
    print(f"\n📋 COLUNAS")
    for col in resultado['analise_dados']['colunas']:
        print(f"  - {col['nome']}: {col['tipo']}")
    
    print(f"\n⚠️  PROBLEMAS")
    problemas = resultado['analise_dados']['problemas_qualidade']
    if problemas:
        for p in problemas:
            print(f"  - {p}")
    else:
        print("  Nenhum problema detectado")
    
    print(f"\n💡 ALTERNATIVAS")
    for alt in resultado['alternativas']:
        print(f"  - {alt['tipo']}: score {alt['score']}")
    
    print(f"\n📝 SCORES")
    scores = resultado['scores']
    print(f"  Relevância: {scores['relevancia']}")
    print(f"  Completude: {scores['completude']}")
    print(f"  Confiança: {scores['confianca']}")
    print(f"  Score Final: {scores['score_final']}")
    
    print(f"\n💾 CÓDIGO GERADO: {resultado['codigo_grafico'] is not None}")
    
    return resultado


if __name__ == "__main__":
    print("\n🎨 EXEMPLOS DE USO — Agente Visualizador de Dados\n")
    
    # Executar todos os exemplos
    exemplo_1_bar_chart()
    exemplo_2_line_chart()
    exemplo_3_scatter_plot()
    exemplo_4_pie_chart()
    
    # Histogram precisa de numpy
    try:
        import numpy as np
        exemplo_5_histogram()
        exemplo_6_boxplot()
        exemplo_7_heatmap()
    except ImportError:
        print("\n⚠️  Numpy não instalado. Pulando exemplos 5, 6, 7")
    
    exemplo_preferencia_forcada()
    exemplo_apenas_recomendacao()
    exemplo_analise_completa()
    
    print("\n" + "="*60)
    print("✅ Todos os exemplos executados com sucesso!")
    print("="*60)
