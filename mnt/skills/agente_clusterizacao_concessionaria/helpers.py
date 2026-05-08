"""
agente_clusterizacao_concessionaria/helpers.py
================================
Implementa clustering inteligente de concessionárias usando K-Means/DBSCAN.

Extrai 15 features operacionais, normaliza, clusteriza e gera perfis via LLM.

Uso:
    agent = ClusteringAgent(host=..., banco=..., usuario=..., senha=...)
    
    # Clusterizar todas
    resultado = agent.clusterizar_concessionarias(n_clusters=5, periodo_dias=90)
    
    # Analisar uma específica
    analise = agent.analisar_concessionaria("MATRIZ SP", clusters_info=resultado["clusters_info"])
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# Suprimir warnings do sklearn
warnings.filterwarnings('ignore', category=FutureWarning)

from mnt.skills.agente_mysql.helpers import MySQLAgent


# ---------------------------------------------------------------------------
# Features Extraídas (15 dimensões)
# ---------------------------------------------------------------------------

@dataclass
class FeaturesConcessionaria:
    """Features operacionais de uma concessionária."""
    
    concessionaria: str
    
    # Grupo 1: Volume e Faturamento
    faturamento_total: float = 0.0
    ticket_medio: float = 0.0
    ticket_mediana: float = 0.0
    volume_os: int = 0
    volume_servicos: int = 0
    
    # Grupo 2: Mix de Produtos
    pct_servicos_premium: float = 0.0
    pct_servicos_basicos: float = 0.0
    diversidade_servicos: float = 0.0  # Índice Herfindahl invertido
    taxa_cross_sell: float = 0.0
    
    # Grupo 3: Eficiência Operacional
    concentracao_vendedoras: float = 0.0
    produtividade_vendedora: float = 0.0
    taxa_conversao_pagamento: float = 0.0
    
    # Grupo 4: Sazonalidade e Tendência
    volatilidade_mensal: float = 0.0
    taxa_crescimento: float = 0.0
    intensidade_sazonal: float = 0.0
    
    # Metadados
    cluster_id: int = -1
    distancia_centroide: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            'concessionaria': self.concessionaria,
            'faturamento_total': round(self.faturamento_total, 2),
            'ticket_medio': round(self.ticket_medio, 2),
            'ticket_mediana': round(self.ticket_mediana, 2),
            'volume_os': self.volume_os,
            'volume_servicos': self.volume_servicos,
            'pct_servicos_premium': round(self.pct_servicos_premium, 4),
            'pct_servicos_basicos': round(self.pct_servicos_basicos, 4),
            'diversidade_servicos': round(self.diversidade_servicos, 4),
            'taxa_cross_sell': round(self.taxa_cross_sell, 4),
            'concentracao_vendedoras': round(self.concentracao_vendedoras, 4),
            'produtividade_vendedora': round(self.produtividade_vendedora, 2),
            'taxa_conversao_pagamento': round(self.taxa_conversao_pagamento, 4),
            'volatilidade_mensal': round(self.volatilidade_mensal, 2),
            'taxa_crescimento': round(self.taxa_crescimento, 4),
            'intensidade_sazonal': round(self.intensidade_sazonal, 4),
            'cluster_id': self.cluster_id,
            'distancia_centroide': round(self.distancia_centroide, 4),
        }
    
    def to_feature_vector(self) -> np.ndarray:
        """Retorna vetor de 15 features para clustering."""
        return np.array([
            self.faturamento_total,
            self.ticket_medio,
            self.ticket_mediana,
            self.volume_os,
            self.volume_servicos,
            self.pct_servicos_premium,
            self.pct_servicos_basicos,
            self.diversidade_servicos,
            self.taxa_cross_sell,
            self.concentracao_vendedoras,
            self.produtividade_vendedora,
            self.taxa_conversao_pagamento,
            self.volatilidade_mensal,
            self.taxa_crescimento,
            self.intensidade_sazonal,
        ])


# ---------------------------------------------------------------------------
# Perfil de Cluster
# ---------------------------------------------------------------------------

@dataclass
class PerfilCluster:
    """Perfil descritivo de um cluster."""
    
    cluster_id: int
    nome_perfil: str
    tamanho: int
    concessionarias: List[str]
    
    # Características médias
    caracteristicas: Dict[str, float] = field(default_factory=dict)
    
    # Descrições geradas via LLM (opcional)
    descricao: str = ""
    pontos_fortes: List[str] = field(default_factory=list)
    desafios: List[str] = field(default_factory=list)
    recomendacoes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'cluster_id': self.cluster_id,
            'nome_perfil': self.nome_perfil,
            'tamanho': self.tamanho,
            'concessionarias': self.concessionarias,
            'caracteristicas': self.caracteristicas,
            'descricao': self.descricao,
            'pontos_fortes': self.pontos_fortes,
            'desafios': self.desafios,
            'recomendacoes': self.recomendacoes,
        }


# ---------------------------------------------------------------------------
# Clustering Agent
# ---------------------------------------------------------------------------

class ClusteringAgent:
    """
    Agente de clusterização de concessionárias.
    
    Extrai features, normaliza, aplica K-Means/DBSCAN e gera perfis.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        porta: int = 3306,
        usuario: str = "root",
        senha: str = "",
        banco: str = "",
        verbose: bool = True,
    ):
        self.mysql_agent = MySQLAgent(
            host=host, porta=porta, usuario=usuario, senha=senha, banco=banco
        )
        self.verbose = verbose
        self.scaler = StandardScaler()
        self.features_concessionarias: List[FeaturesConcessionaria] = []
        self.perfis_clusters: List[PerfilCluster] = []
    
    def _log(self, mensagem: str):
        if self.verbose:
            print(f"[clustering] {mensagem}")
    
    # -----------------------------------------------------------------------
    # ETAPA 1: Extração de Features
    # -----------------------------------------------------------------------
    
    def extrair_features_concessionarias(
        self,
        periodo_dias: int = 90,
        df: Optional[pd.DataFrame] = None
    ) -> List[FeaturesConcessionaria]:
        """
        Extrai 15 features operacionais de cada concessionária.
        
        Args:
            periodo_dias: Janela temporal de análise (padrão 90 dias)
            df: DataFrame opcional (se None, carrega do banco)
        
        Returns:
            Lista de FeaturesConcessionaria
        """
        self._log(f"Extraindo features das concessionárias (período: {periodo_dias} dias)...")
        
        # Carregar dados se não fornecido
        if df is None:
            df = self._carregar_dados_os(periodo_dias)
        
        # Validar colunas necessárias
        colunas_necessarias = [
            'concessionaria_nome', 'oss_valor_venda_real', 'os_paga',
            'qtd_servicos', 'vendedor_nome', 'servico_nome', 'created_at', 'id'
        ]
        faltando = set(colunas_necessarias) - set(df.columns)
        if faltando:
            raise ValueError(f"Colunas faltando no DataFrame: {faltando}")
        
        # Filtrar apenas serviços válidos
        df = df[df['oss_valor_venda_real'] > 0].copy()
        
        self._log(f"DataFrame carregado: {len(df):,} linhas de {df['concessionaria_nome'].nunique()} concessionárias")
        
        # Calcular percentis globais (para pct_servicos_premium/basicos)
        p20_global = df['oss_valor_venda_real'].quantile(0.20)
        p80_global = df['oss_valor_venda_real'].quantile(0.80)
        
        self._log(f"Percentis globais: P20={p20_global:.2f}, P80={p80_global:.2f}")
        
        # Converter created_at para datetime se string
        if df['created_at'].dtype == 'object':
            df['created_at'] = pd.to_datetime(df['created_at'], errors='coerce')
        
        # Adicionar colunas auxiliares
        df['ano_mes'] = df['created_at'].dt.to_period('M')
        df['is_premium'] = df['oss_valor_venda_real'] >= p80_global
        df['is_basico'] = df['oss_valor_venda_real'] <= p20_global
        df['is_multi_servico'] = df['qtd_servicos'] >= 2
        
        # Agrupar por concessionária
        features_list = []
        
        for conc in df['concessionaria_nome'].unique():
            df_conc = df[df['concessionaria_nome'] == conc]
            
            features = FeaturesConcessionaria(concessionaria=conc)
            
            # --- Grupo 1: Volume e Faturamento ---
            features.faturamento_total = df_conc['oss_valor_venda_real'].sum()
            features.ticket_medio = df_conc['oss_valor_venda_real'].mean()
            features.ticket_mediana = df_conc['oss_valor_venda_real'].median()
            features.volume_os = df_conc['id'].nunique()
            features.volume_servicos = len(df_conc)
            
            # --- Grupo 2: Mix de Produtos ---
            fat_total = features.faturamento_total
            if fat_total > 0:
                fat_premium = df_conc[df_conc['is_premium']]['oss_valor_venda_real'].sum()
                fat_basico = df_conc[df_conc['is_basico']]['oss_valor_venda_real'].sum()
                features.pct_servicos_premium = fat_premium / fat_total
                features.pct_servicos_basicos = fat_basico / fat_total
            
            # Diversidade de serviços (Herfindahl invertido)
            mix_servicos = df_conc.groupby('servico_nome')['oss_valor_venda_real'].sum()
            if len(mix_servicos) > 0:
                mix_servicos_pct = mix_servicos / mix_servicos.sum()
                herfindahl = (mix_servicos_pct ** 2).sum()
                features.diversidade_servicos = 1 - herfindahl  # Quanto maior, mais diverso
            
            # Taxa de cross-sell
            if features.volume_os > 0:
                os_multi = df_conc[df_conc['is_multi_servico']]['id'].nunique()
                features.taxa_cross_sell = os_multi / features.volume_os
            
            # --- Grupo 3: Eficiência Operacional ---
            # Concentração vendedoras
            vendedoras_fat = df_conc.groupby('vendedor_nome')['oss_valor_venda_real'].sum().sort_values(ascending=False)
            if len(vendedoras_fat) > 0:
                fat_top2 = vendedoras_fat.head(2).sum()
                features.concentracao_vendedoras = fat_top2 / fat_total if fat_total > 0 else 0
                
                # Produtividade por vendedora
                features.produtividade_vendedora = fat_total / len(vendedoras_fat)
            
            # Taxa de conversão (pagamento)
            os_pagas = df_conc[df_conc['os_paga'] == 1]['id'].nunique()
            features.taxa_conversao_pagamento = os_pagas / features.volume_os if features.volume_os > 0 else 0
            
            # --- Grupo 4: Sazonalidade e Tendência ---
            # Volatilidade mensal (desvio padrão do faturamento mensal)
            fat_mensal = df_conc.groupby('ano_mes')['oss_valor_venda_real'].sum()
            if len(fat_mensal) >= 2:
                features.volatilidade_mensal = fat_mensal.std()
                
                # Intensidade sazonal (pico - vale) / mediana
                pico = fat_mensal.max()
                vale = fat_mensal.min()
                mediana = fat_mensal.median()
                if mediana > 0:
                    features.intensidade_sazonal = (pico - vale) / mediana
            
            # Taxa de crescimento (últimos 3 meses vs 3 anteriores)
            if len(fat_mensal) >= 6:
                ultimos_3m = fat_mensal.tail(3).sum()
                anteriores_3m = fat_mensal.tail(6).head(3).sum()
                if anteriores_3m > 0:
                    features.taxa_crescimento = (ultimos_3m - anteriores_3m) / anteriores_3m
            
            features_list.append(features)
        
        self.features_concessionarias = features_list
        self._log(f"✅ Features extraídas de {len(features_list)} concessionárias")
        
        return features_list
    
    def _carregar_dados_os(self, periodo_dias: int) -> pd.DataFrame:
        """Carrega dados de OS do MySQL com LEFT JOINs."""
        self._log(f"Carregando dados do MySQL (últimos {periodo_dias} dias)...")
        
        # Usar MySQLAgent para carregar dados com JOINs
        resultado = self.mysql_agent.carregar_multiplas_tabelas(
            definicoes=[
                {"tabela": "os", "alias": "o"},
                {"tabela": "os_servicos", "alias": "oss", "fk": "o.id = oss.os_id"},
                {"tabela": "concessionarias", "alias": "c", "fk": "o.concessionaria_id = c.id"},
                {"tabela": "funcionarios", "alias": "f", "fk": "o.vendedor_id = f.id"},
                {"tabela": "servicos", "alias": "s", "fk": "oss.servico_id = s.id"},
            ],
            filtro_where=f"""
                o.deleted_at IS NULL 
                AND o.cancelada = 0
                AND oss.deleted_at IS NULL
                AND oss.cancelado = 0
                AND o.created_at >= DATE_SUB(CURRENT_DATE, INTERVAL {periodo_dias} DAY)
            """,
            limite=500000,
            verbose=self.verbose
        )
        
        if not resultado["sucesso"]:
            raise RuntimeError(f"Erro ao carregar dados: {resultado['erro']}")
        
        df = resultado["dataframe"]
        
        # Renomear colunas para o padrão esperado
        rename_map = {
            'o.id': 'id',
            'o.created_at': 'created_at',
            'o.paga': 'os_paga',
            'c.nome': 'concessionaria_nome',
            'f.nome': 'vendedor_nome',
            's.nome': 'servico_nome',
            'oss.valor_venda_real': 'oss_valor_venda_real',
        }
        
        # Aplicar renomeação se colunas existirem
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        
        # Calcular qtd_servicos por OS (se não vier da query)
        if 'qtd_servicos' not in df.columns:
            qtd_servicos = df.groupby('id').size().reset_index(name='qtd_servicos')
            df = df.merge(qtd_servicos, on='id', how='left')
        
        return df
    
    # -----------------------------------------------------------------------
    # ETAPA 2: Clustering
    # -----------------------------------------------------------------------
    
    def clusterizar(
        self,
        n_clusters: int = 5,
        metodo: str = "kmeans",
        features: Optional[List[FeaturesConcessionaria]] = None
    ) -> Dict[str, Any]:
        """
        Aplica clustering nas concessionárias.
        
        Args:
            n_clusters: Número de clusters (kmeans) ou min_samples (dbscan)
            metodo: 'kmeans' ou 'dbscan'
            features: Lista de features (usa self.features_concessionarias se None)
        
        Returns:
            Dict com resultado do clustering
        """
        if features is None:
            features = self.features_concessionarias
        
        if not features:
            raise ValueError("Nenhuma feature disponível. Execute extrair_features_concessionarias() primeiro.")
        
        self._log(f"Iniciando clustering ({metodo}) com {len(features)} concessionárias...")
        
        # Converter features para matriz
        concessionarias = [f.concessionaria for f in features]
        X = np.array([f.to_feature_vector() for f in features])
        
        self._log(f"Matriz de features: {X.shape}")
        
        # Normalizar
        X_norm = self.scaler.fit_transform(X)
        
        # Aplicar clustering
        if metodo == "kmeans":
            model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = model.fit_predict(X_norm)
            centroides = model.cluster_centers_
            
        elif metodo == "dbscan":
            model = DBSCAN(eps=0.5, min_samples=max(2, n_clusters // 2))
            labels = model.fit_predict(X_norm)
            centroides = None  # DBSCAN não tem centróides fixos
            
        else:
            raise ValueError(f"Método '{metodo}' não suportado. Use 'kmeans' ou 'dbscan'.")
        
        # Calcular distância ao centróide para cada concessionária
        distancias = np.zeros(len(features))
        if centroides is not None:
            for i, (x, label) in enumerate(zip(X_norm, labels)):
                if label >= 0:  # -1 = outlier no DBSCAN
                    distancias[i] = np.linalg.norm(x - centroides[label])
        
        # Atribuir cluster_id e distância a cada feature
        for i, feature in enumerate(features):
            feature.cluster_id = int(labels[i])
            feature.distancia_centroide = float(distancias[i])
        
        # Calcular silhouette score
        silhouette = -1.0
        if len(set(labels)) > 1 and -1 not in labels:  # Só se houver múltiplos clusters válidos
            try:
                silhouette = silhouette_score(X_norm, labels)
            except:
                pass
        
        # Distribuição de clusters
        unique, counts = np.unique(labels, return_counts=True)
        distribuicao = {f"cluster_{int(k)}": int(v) for k, v in zip(unique, counts)}
        
        self._log(f"✅ Clustering concluído: {len(set(labels))} clusters, silhouette={silhouette:.3f}")
        self._log(f"Distribuição: {distribuicao}")
        
        return {
            'total_concessionarias': len(features),
            'n_clusters': len(set(labels)),
            'metodo': metodo,
            'silhouette_score': round(float(silhouette), 4),
            'distribuicao': distribuicao,
            'labels': labels.tolist(),
            'centroides': centroides.tolist() if centroides is not None else None,
        }
    
    # -----------------------------------------------------------------------
    # ETAPA 3: Geração de Perfis
    # -----------------------------------------------------------------------
    
    def gerar_perfis_clusters(
        self,
        features: Optional[List[FeaturesConcessionaria]] = None
    ) -> List[PerfilCluster]:
        """
        Gera perfis descritivos para cada cluster.
        
        Args:
            features: Lista de features com cluster_id atribuído
        
        Returns:
            Lista de PerfilCluster
        """
        if features is None:
            features = self.features_concessionarias
        
        if not features:
            raise ValueError("Nenhuma feature disponível.")
        
        self._log("Gerando perfis dos clusters...")
        
        # Agrupar por cluster
        clusters_dict = {}
        for f in features:
            if f.cluster_id not in clusters_dict:
                clusters_dict[f.cluster_id] = []
            clusters_dict[f.cluster_id].append(f)
        
        perfis = []
        
        for cluster_id, concs in clusters_dict.items():
            if cluster_id < 0:  # Outliers do DBSCAN
                continue
            
            # Calcular características médias
            n = len(concs)
            caracteristicas = {
                'faturamento_medio': np.mean([c.faturamento_total for c in concs]),
                'ticket_medio': np.mean([c.ticket_medio for c in concs]),
                'ticket_mediana': np.mean([c.ticket_mediana for c in concs]),
                'volume_os_medio': np.mean([c.volume_os for c in concs]),
                'taxa_cross_sell': np.mean([c.taxa_cross_sell for c in concs]),
                'concentracao_vendedoras': np.mean([c.concentracao_vendedoras for c in concs]),
                'diversidade_servicos': np.mean([c.diversidade_servicos for c in concs]),
                'taxa_crescimento': np.mean([c.taxa_crescimento for c in concs]),
            }
            
            # Identificar concessionárias mais próximas do centróide (representativas)
            concs_sorted = sorted(concs, key=lambda c: c.distancia_centroide)
            representativas = [c.concessionaria for c in concs_sorted[:min(3, n)]]
            
            # Gerar nome do perfil baseado nas características
            nome_perfil = self._gerar_nome_perfil(caracteristicas)
            
            perfil = PerfilCluster(
                cluster_id=cluster_id,
                nome_perfil=nome_perfil,
                tamanho=n,
                concessionarias=[c.concessionaria for c in concs],
                caracteristicas={k: round(v, 2) for k, v in caracteristicas.items()},
                descricao=f"Cluster de {n} concessionárias com perfil '{nome_perfil}'."
            )
            
            # Atribuir concessionárias representativas
            perfil.concessionarias = representativas
            
            perfis.append(perfil)
        
        self.perfis_clusters = perfis
        self._log(f"✅ {len(perfis)} perfis de cluster gerados")
        
        return perfis
    
    def _gerar_nome_perfil(self, caracteristicas: Dict[str, float]) -> str:
        """Gera nome descritivo baseado nas características do cluster."""
        
        fat = caracteristicas['faturamento_medio']
        ticket = caracteristicas['ticket_medio']
        cross_sell = caracteristicas['taxa_cross_sell']
        crescimento = caracteristicas['taxa_crescimento']
        
        # Categorizar faturamento
        if fat > 800000:
            nivel_fat = "Alto Volume"
        elif fat > 400000:
            nivel_fat = "Volume Moderado"
        else:
            nivel_fat = "Baixo Volume"
        
        # Categorizar ticket
        if ticket > 5000:
            nivel_ticket = "Premium"
        elif ticket > 3000:
            nivel_ticket = "Médio"
        else:
            nivel_ticket = "Básico"
        
        # Adicionar característica especial
        if cross_sell > 0.4:
            especial = "Alto Cross-Sell"
        elif crescimento > 0.15:
            especial = "Crescimento"
        elif crescimento < -0.10:
            especial = "Declínio"
        else:
            especial = ""
        
        # Montar nome
        partes = [nivel_fat, nivel_ticket]
        if especial:
            partes.append(especial)
        
        return " e ".join(partes[:2]) + (f" ({especial})" if especial and len(partes) > 2 else "")
    
    # -----------------------------------------------------------------------
    # ETAPA 4: Análise de Concessionária Específica
    # -----------------------------------------------------------------------
    
    def analisar_concessionaria(
        self,
        nome_concessionaria: str,
        features: Optional[List[FeaturesConcessionaria]] = None,
        perfis: Optional[List[PerfilCluster]] = None
    ) -> Dict[str, Any]:
        """
        Analisa uma concessionária específica comparando com seu cluster.
        
        Args:
            nome_concessionaria: Nome da concessionária a analisar
            features: Lista de features (usa self.features_concessionarias se None)
            perfis: Lista de perfis (usa self.perfis_clusters se None)
        
        Returns:
            Dict com análise comparativa
        """
        if features is None:
            features = self.features_concessionarias
        
        if perfis is None:
            perfis = self.perfis_clusters
        
        if not features or not perfis:
            raise ValueError("Features e perfis necessários. Execute clustering primeiro.")
        
        # Encontrar feature da concessionária
        feature_conc = None
        for f in features:
            if f.concessionaria == nome_concessionaria:
                feature_conc = f
                break
        
        if feature_conc is None:
            raise ValueError(f"Concessionária '{nome_concessionaria}' não encontrada.")
        
        # Encontrar perfil do cluster
        perfil_cluster = None
        for p in perfis:
            if p.cluster_id == feature_conc.cluster_id:
                perfil_cluster = p
                break
        
        if perfil_cluster is None:
            return {
                'concessionaria': nome_concessionaria,
                'cluster_id': feature_conc.cluster_id,
                'erro': 'Cluster não encontrado (outlier?)',
            }
        
        # Calcular comparação com cluster
        concs_cluster = [f for f in features if f.cluster_id == feature_conc.cluster_id]
        
        comparacao = {}
        metricas = [
            ('faturamento_total', 'Faturamento'),
            ('ticket_medio', 'Ticket Médio'),
            ('taxa_cross_sell', 'Taxa Cross-Sell'),
            ('concentracao_vendedoras', 'Concentração Vendedoras'),
            ('diversidade_servicos', 'Diversidade Serviços'),
            ('taxa_crescimento', 'Taxa de Crescimento'),
        ]
        
        for attr, nome in metricas:
            valor_conc = getattr(feature_conc, attr)
            valores_cluster = [getattr(f, attr) for f in concs_cluster]
            
            media_cluster = np.mean(valores_cluster)
            mediana_cluster = np.median(valores_cluster)
            
            diferenca_pct = ((valor_conc - media_cluster) / media_cluster * 100) if media_cluster != 0 else 0
            
            # Ranking dentro do cluster
            valores_sorted = sorted(valores_cluster, reverse=True)
            posicao = valores_sorted.index(valor_conc) + 1 if valor_conc in valores_sorted else -1
            
            # Interpretação
            if abs(diferenca_pct) < 5:
                interpretacao = "Alinhado com o cluster"
            elif diferenca_pct > 15:
                interpretacao = "Acima da média do cluster"
            elif diferenca_pct < -15:
                interpretacao = "Abaixo da média do cluster — oportunidade"
            else:
                interpretacao = "Próximo à média do cluster"
            
            comparacao[attr] = {
                'nome': nome,
                'valor_concessionaria': round(valor_conc, 2),
                'media_cluster': round(media_cluster, 2),
                'mediana_cluster': round(mediana_cluster, 2),
                'posicao_ranking': posicao,
                'diferenca_pct': round(diferenca_pct, 1),
                'interpretacao': interpretacao,
            }
        
        # Identificar concessionárias similares (mesmo cluster, distância similar)
        similares = []
        for f in concs_cluster:
            if f.concessionaria == nome_concessionaria:
                continue
            
            # Calcular similaridade (inverso da distância euclidiana normalizada)
            dist = np.linalg.norm(
                np.array([
                    f.faturamento_total - feature_conc.faturamento_total,
                    f.ticket_medio - feature_conc.ticket_medio,
                    f.taxa_cross_sell - feature_conc.taxa_cross_sell,
                ])
            )
            
            max_dist = np.linalg.norm(np.array([
                perfil_cluster.caracteristicas['faturamento_medio'],
                perfil_cluster.caracteristicas['ticket_medio'],
                perfil_cluster.caracteristicas['taxa_cross_sell'],
            ]))
            
            similaridade = max(0, 1 - (dist / max_dist)) if max_dist > 0 else 0
            
            similares.append({
                'nome': f.concessionaria,
                'cluster_id': f.cluster_id,
                'similaridade': round(similaridade, 2),
            })
        
        similares = sorted(similares, key=lambda x: x['similaridade'], reverse=True)[:5]
        
        # Gerar pontos fortes e melhorias
        pontos_fortes = []
        pontos_melhoria = []
        
        for attr, comp in comparacao.items():
            if comp['diferenca_pct'] > 10:
                pontos_fortes.append(f"{comp['nome']}: {comp['diferenca_pct']:+.1f}% acima do cluster")
            elif comp['diferenca_pct'] < -10:
                pontos_melhoria.append(f"{comp['nome']}: {comp['diferenca_pct']:.1f}% abaixo do cluster")
        
        return {
            'concessionaria': nome_concessionaria,
            'cluster_id': feature_conc.cluster_id,
            'cluster_nome': perfil_cluster.nome_perfil,
            'resumo_posicionamento': f"{nome_concessionaria} pertence ao cluster '{perfil_cluster.nome_perfil}' ({perfil_cluster.tamanho} concessionárias).",
            'comparacao_cluster': comparacao,
            'concessionarias_similares': similares,
            'pontos_fortes': pontos_fortes,
            'pontos_de_melhoria': pontos_melhoria,
            'features_raw': feature_conc.to_dict(),
        }
    
    # -----------------------------------------------------------------------
    # Método Principal: Clustering Completo
    # -----------------------------------------------------------------------
    
    def clusterizar_concessionarias(
        self,
        n_clusters: int = 5,
        periodo_dias: int = 90,
        metodo: str = "kmeans",
        df: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Pipeline completo: extração → clustering → perfis.
        
        Args:
            n_clusters: Número de clusters
            periodo_dias: Janela temporal de análise
            metodo: 'kmeans' ou 'dbscan'
            df: DataFrame opcional (se None, carrega do banco)
        
        Returns:
            Dict com resultado completo
        """
        # Etapa 1: Extrair features
        features = self.extrair_features_concessionarias(periodo_dias, df)
        
        # Etapa 2: Clusterizar
        resultado_clustering = self.clusterizar(n_clusters, metodo, features)
        
        # Etapa 3: Gerar perfis
        perfis = self.gerar_perfis_clusters(features)
        
        # Etapa 4: Montar mapeamento concessionária → cluster
        mapeamento = []
        for f in features:
            mapeamento.append({
                'concessionaria': f.concessionaria,
                'cluster_id': f.cluster_id,
                'distancia_centroide': round(f.distancia_centroide, 4),
            })
        
        return {
            'resumo_clustering': resultado_clustering,
            'perfis_clusters': [p.to_dict() for p in perfis],
            'mapeamento_concessionarias': sorted(mapeamento, key=lambda x: (x['cluster_id'], x['distancia_centroide'])),
            'features_detalhadas': [f.to_dict() for f in features],
        }


# ---------------------------------------------------------------------------
# Função de conveniência
# ---------------------------------------------------------------------------

def clusterizar_concessionarias(
    host: str = "localhost",
    porta: int = 3306,
    usuario: str = "root",
    senha: str = "",
    banco: str = "",
    n_clusters: int = 5,
    periodo_dias: int = 90,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Função de conveniência para clustering rápido.
    
    Returns:
        Dict com resultado completo do clustering
    """
    agent = ClusteringAgent(
        host=host, porta=porta, usuario=usuario, senha=senha, banco=banco, verbose=verbose
    )
    
    return agent.clusterizar_concessionarias(
        n_clusters=n_clusters,
        periodo_dias=periodo_dias,
        metodo="kmeans"
    )
