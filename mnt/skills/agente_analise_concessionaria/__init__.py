"""
Import package-style: mnt.skills.agente_analise_concessionaria
Código em agente-analise-concessionaria/ (hífen).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_DIR = Path(__file__).resolve().parent.parent / "agente-analise-concessionaria"

_spec_g = importlib.util.spec_from_file_location(
    "agente_analise_concessionaria_graficos", _DIR / "graficos.py",
)
_mod_g = importlib.util.module_from_spec(_spec_g)
assert _spec_g.loader
sys.modules[_spec_g.name] = _mod_g
_spec_g.loader.exec_module(_mod_g)

_spec_r = importlib.util.spec_from_file_location(
    "agente_analise_concessionaria_relatorio", _DIR / "relatorio.py",
)
_mod_r = importlib.util.module_from_spec(_spec_r)
assert _spec_r.loader
sys.modules[_spec_r.name] = _mod_r
_spec_r.loader.exec_module(_mod_r)

gerar_todos_graficos = _mod_g.gerar_todos_graficos
gerar_relatorio_pdf = _mod_r.gerar_relatorio_pdf

__all__ = ["gerar_todos_graficos", "gerar_relatorio_pdf"]
