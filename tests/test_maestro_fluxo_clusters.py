"""Testes para listas de concessionárias na entrega markdown do Maestro."""
import unittest

from app.services.maestro_fluxo import (
    _formatar_entrega,
    _markdown_concessionarias_por_cluster,
    _resposta_agente_para_texto,
)


class TestMarkdownConcessionariasPorCluster(unittest.TestCase):
    def test_resumo_mais_listas_em_perfis_clusters(self):
        resposta = {
            "resumo_executivo": "Resumo curto sobre perfis.",
            "perfis_clusters": [
                {
                    "cluster_id": 0,
                    "nome_perfil": "Alto volume",
                    "concessionarias": ["Loja A", "Loja B"],
                }
            ],
        }
        out = _resposta_agente_para_texto(resposta)
        self.assertIn("Resumo curto sobre perfis.", out)
        self.assertIn("#### Concessionárias por cluster", out)
        self.assertIn("Alto volume", out)
        self.assertIn("- Loja A", out)
        self.assertIn("- Loja B", out)

    def test_fallback_perfis_clusters_dados(self):
        resposta = {
            "resumo_executivo": "Só resumo.",
            "perfis_clusters": [
                {"cluster_id": 0, "nome_perfil": "Perfil X"},
            ],
        }
        resultado_execucao = {
            "clustering_deterministico": {
                "perfis_clusters_dados": [
                    {"cluster_id": 0, "n_concessionarias": 2, "concessionarias": ["Alpha", "Beta"]},
                ],
                "mapeamento_concessionarias": [
                    {"concessionaria": "Alpha", "cluster_id": 0},
                    {"concessionaria": "Beta", "cluster_id": 0},
                ],
            }
        }
        out = _resposta_agente_para_texto(resposta, resultado_execucao=resultado_execucao)
        self.assertIn("Só resumo.", out)
        self.assertIn("- Alpha", out)
        self.assertIn("- Beta", out)

    def test_apenas_mapeamento_sem_perfis_nem_dados(self):
        resposta = {
            "mapeamento_concessionarias": [
                {"concessionaria": "L1", "cluster_id": 1},
                {"concessionaria": "L2", "cluster_id": 1},
            ],
        }
        md = _markdown_concessionarias_por_cluster(resposta, None)
        self.assertIn("#### Concessionárias por cluster", md)
        self.assertIn("- L1", md)
        self.assertIn("- L2", md)


class TestFormatarEntregaCluster(unittest.TestCase):
    def test_formatar_entrega_passa_resultado_execucao(self):
        para_avaliador = [
            {
                "agente_id": "agente_clusterizacao_concessionaria",
                "agente_nome": "Cluster",
                "pode_responder": True,
                "scores": {"score_final": 0.9},
                "resposta": {
                    "resumo_executivo": "Visão geral.",
                    "perfis_clusters": [{"cluster_id": 0, "concessionarias": ["Z"]}],
                },
                "resultado_execucao": {"metricas": []},
            }
        ]
        avaliacao = {
            "avaliacao_completa": [
                {"agente_id": "agente_clusterizacao_concessionaria", "score_total": 0.9},
            ],
            "ranking_final": ["agente_clusterizacao_concessionaria"],
        }
        md = _formatar_entrega("Pergunta?", para_avaliador, avaliacao, para_avaliador)
        self.assertIn("Visão geral.", md)
        self.assertIn("- Z", md)


if __name__ == "__main__":
    unittest.main()
