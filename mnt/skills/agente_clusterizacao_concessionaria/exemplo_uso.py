"""
exemplo_uso_clustering.py
==========================
Exemplo de uso do agente de clusterização de concessionárias.

Execute este script para ver o agente em ação.
"""

from mnt.skills.agente_clusterizacao_concessionaria import ClusteringAgent
import json

# ---------------------------------------------------------------------------
# EXEMPLO 1: Clustering Completo
# ---------------------------------------------------------------------------

def exemplo_clustering_completo():
    """Pipeline completo: extrair features → clusterizar → gerar perfis."""
    
    print("=" * 80)
    print("EXEMPLO 1: CLUSTERING COMPLETO DE CONCESSIONÁRIAS")
    print("=" * 80)
    
    # Criar agente
    agent = ClusteringAgent(
        host="localhost",
        porta=3306,
        usuario="root",
        senha="sua_senha",
        banco="seu_banco",
        verbose=True
    )
    
    # Executar clustering completo
    resultado = agent.clusterizar_concessionarias(
        n_clusters=5,          # Número de clusters desejado
        periodo_dias=90,       # Últimos 90 dias
        metodo="kmeans"        # Algoritmo de clustering
    )
    
    # Exibir resumo
    print("\n" + "=" * 80)
    print("RESUMO DO CLUSTERING")
    print("=" * 80)
    print(json.dumps(resultado["resumo_clustering"], indent=2, ensure_ascii=False))
    
    # Exibir perfis dos clusters
    print("\n" + "=" * 80)
    print("PERFIS DOS CLUSTERS")
    print("=" * 80)
    
    for perfil in resultado["perfis_clusters"]:
        print(f"\n🔹 CLUSTER {perfil['cluster_id']}: {perfil['nome_perfil']}")
        print(f"   Tamanho: {perfil['tamanho']} concessionárias")
        print(f"   Características:")
        for k, v in perfil['caracteristicas'].items():
            print(f"     • {k}: {v:,.2f}")
        print(f"   Concessionárias representativas: {', '.join(perfil['concessionarias'])}")
    
    # Exibir mapeamento
    print("\n" + "=" * 80)
    print("MAPEAMENTO: CONCESSIONÁRIA → CLUSTER")
    print("=" * 80)
    
    for item in resultado["mapeamento_concessionarias"][:10]:  # Primeiras 10
        print(f"  {item['concessionaria']:<40} → Cluster {item['cluster_id']} (dist: {item['distancia_centroide']:.4f})")
    
    return resultado


# ---------------------------------------------------------------------------
# EXEMPLO 2: Análise de Concessionária Específica
# ---------------------------------------------------------------------------

def exemplo_analise_concessionaria(resultado_clustering):
    """Analisa uma concessionária específica comparando com seu cluster."""
    
    print("\n\n" + "=" * 80)
    print("EXEMPLO 2: ANÁLISE DE CONCESSIONÁRIA ESPECÍFICA")
    print("=" * 80)
    
    # Criar agente
    agent = ClusteringAgent(
        host="localhost",
        porta=3306,
        usuario="root",
        senha="sua_senha",
        banco="seu_banco",
        verbose=False  # Silencioso para esta análise
    )
    
    # Reconstruir features e perfis do resultado anterior
    # (Em uso real, você manteria o objeto agent do exemplo 1)
    agent.features_concessionarias = [
        FeaturesConcessionaria(**f) for f in resultado_clustering["features_detalhadas"]
    ]
    
    from mnt.skills.agente_clusterizacao_concessionaria.helpers import PerfilCluster
    agent.perfis_clusters = [
        PerfilCluster(**p) for p in resultado_clustering["perfis_clusters"]
    ]
    
    # Escolher uma concessionária para analisar
    # (Pegue a primeira do mapeamento como exemplo)
    conc_exemplo = resultado_clustering["mapeamento_concessionarias"][0]["concessionaria"]
    
    print(f"\n🔍 Analisando: {conc_exemplo}")
    
    # Analisar
    analise = agent.analisar_concessionaria(conc_exemplo)
    
    # Exibir resumo
    print(f"\n📊 POSICIONAMENTO")
    print(f"   {analise['resumo_posicionamento']}")
    
    # Exibir comparação com cluster
    print(f"\n📈 COMPARAÇÃO COM CLUSTER")
    for attr, comp in analise['comparacao_cluster'].items():
        print(f"\n   {comp['nome']}:")
        print(f"     • Valor: {comp['valor_concessionaria']:,.2f}")
        print(f"     • Média do cluster: {comp['media_cluster']:,.2f}")
        print(f"     • Diferença: {comp['diferenca_pct']:+.1f}%")
        print(f"     • Posição no ranking: {comp['posicao_ranking']}º")
        print(f"     • {comp['interpretacao']}")
    
    # Exibir concessionárias similares
    print(f"\n🤝 CONCESSIONÁRIAS SIMILARES (mesmo cluster)")
    for similar in analise['concessionarias_similares']:
        print(f"   • {similar['nome']:<40} (similaridade: {similar['similaridade']:.2f})")
    
    # Exibir pontos fortes
    print(f"\n✅ PONTOS FORTES")
    for pf in analise['pontos_fortes']:
        print(f"   • {pf}")
    
    # Exibir oportunidades de melhoria
    print(f"\n⚠️ OPORTUNIDADES DE MELHORIA")
    for pm in analise['pontos_de_melhoria']:
        print(f"   • {pm}")
    
    return analise


# ---------------------------------------------------------------------------
# EXEMPLO 3: Uso com DataFrame Personalizado (sem banco)
# ---------------------------------------------------------------------------

def exemplo_clustering_custom_dataframe():
    """Exemplo usando um DataFrame customizado (sem conectar ao banco)."""
    
    print("\n\n" + "=" * 80)
    print("EXEMPLO 3: CLUSTERING COM DATAFRAME CUSTOMIZADO")
    print("=" * 80)
    
    import pandas as pd
    import numpy as np
    
    # Simular DataFrame de exemplo
    # (Em uso real, você carregaria de CSV, Parquet, etc.)
    
    np.random.seed(42)
    n_registros = 10000
    
    concessionarias = [f"Conc_{i:02d}" for i in range(1, 21)]  # 20 concessionárias
    
    df_exemplo = pd.DataFrame({
        'id': range(1, n_registros + 1),
        'concessionaria_nome': np.random.choice(concessionarias, n_registros),
        'oss_valor_venda_real': np.random.lognormal(8, 0.8, n_registros),  # Distribuição log-normal
        'os_paga': np.random.choice([0, 1], n_registros, p=[0.15, 0.85]),
        'qtd_servicos': np.random.choice([1, 2, 3, 4], n_registros, p=[0.6, 0.25, 0.10, 0.05]),
        'vendedor_nome': [f"Vendedor_{np.random.randint(1, 6)}" for _ in range(n_registros)],
        'servico_nome': np.random.choice(['Serv_A', 'Serv_B', 'Serv_C', 'Serv_D', 'Serv_E'], n_registros),
        'created_at': pd.date_range(end=pd.Timestamp.now(), periods=n_registros, freq='H')
    })
    
    print(f"DataFrame criado: {len(df_exemplo):,} linhas, {df_exemplo['concessionaria_nome'].nunique()} concessionárias")
    
    # Criar agente (sem banco - apenas clustering)
    agent = ClusteringAgent(
        host="localhost",  # Não será usado
        verbose=True
    )
    
    # Extrair features do DataFrame customizado
    features = agent.extrair_features_concessionarias(periodo_dias=90, df=df_exemplo)
    
    print(f"\n✅ Features extraídas de {len(features)} concessionárias")
    
    # Clusterizar
    resultado_clustering = agent.clusterizar(n_clusters=4, metodo="kmeans")
    
    print(f"\n✅ Clustering executado: {resultado_clustering['n_clusters']} clusters")
    print(f"   Silhouette Score: {resultado_clustering['silhouette_score']:.3f}")
    
    # Gerar perfis
    perfis = agent.gerar_perfis_clusters()
    
    print(f"\n✅ Perfis gerados:")
    for perfil in perfis:
        print(f"   • Cluster {perfil.cluster_id}: {perfil.nome_perfil} ({perfil.tamanho} concs)")
    
    return {
        'df': df_exemplo,
        'features': features,
        'perfis': perfis,
    }


# ---------------------------------------------------------------------------
# EXECUTAR EXEMPLOS
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Exemplo 1: Clustering completo
    resultado = exemplo_clustering_completo()
    
    # Exemplo 2: Análise de concessionária
    analise = exemplo_analise_concessionaria(resultado)
    
    # Exemplo 3: Clustering com DataFrame customizado
    # exemplo_custom = exemplo_clustering_custom_dataframe()
    
    print("\n\n" + "=" * 80)
    print("EXEMPLOS CONCLUÍDOS!")
    print("=" * 80)
