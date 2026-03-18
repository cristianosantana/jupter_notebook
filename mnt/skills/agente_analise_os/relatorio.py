"""
Wrapper para importar relatorio do diretorio agente-analise-os.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent.parent / "agente-analise-os" / "relatorio.py"

_spec = importlib.util.spec_from_file_location("agente_analise_os_relatorio", _MODULE_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Nao foi possivel carregar relatorio em {_MODULE_PATH}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

gerar_relatorio_pdf = _mod.gerar_relatorio_pdf

__all__ = ["gerar_relatorio_pdf"]
