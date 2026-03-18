"""
Wrapper para importar graficos do diretorio agente-analise-os.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent.parent / "agente-analise-os" / "graficos.py"

_spec = importlib.util.spec_from_file_location("agente_analise_os_graficos", _MODULE_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Nao foi possivel carregar graficos em {_MODULE_PATH}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

gerar_todos_graficos = _mod.gerar_todos_graficos
grafico_s1_resumo_executivo = _mod.grafico_s1_resumo_executivo
grafico_s2_concessionarias = _mod.grafico_s2_concessionarias
grafico_s3_sazonalidade = _mod.grafico_s3_sazonalidade
grafico_s4_produtos = _mod.grafico_s4_produtos
grafico_s5_vendedores = _mod.grafico_s5_vendedores
grafico_s6_distribuicao_tickets = _mod.grafico_s6_distribuicao_tickets
grafico_s7_cross_selling = _mod.grafico_s7_cross_selling
grafico_s8_alertas = _mod.grafico_s8_alertas

__all__ = [
    "gerar_todos_graficos",
    "grafico_s1_resumo_executivo",
    "grafico_s2_concessionarias",
    "grafico_s3_sazonalidade",
    "grafico_s4_produtos",
    "grafico_s5_vendedores",
    "grafico_s6_distribuicao_tickets",
    "grafico_s7_cross_selling",
    "grafico_s8_alertas",
]
