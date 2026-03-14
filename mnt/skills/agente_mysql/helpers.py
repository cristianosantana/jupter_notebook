"""
Wrapper para importar helpers do diretorio agente-mysql.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parent.parent / "agente-mysql" / "helpers.py"

_spec = importlib.util.spec_from_file_location("agente_mysql_helpers", _MODULE_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Nao foi possivel carregar helpers em {_MODULE_PATH}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

MySQLAgent = _mod.MySQLAgent
DefinicaoTabela = _mod.DefinicaoTabela
MySQLConexao = _mod.MySQLConexao
carregar_tabela_mysql = _mod.carregar_tabela_mysql
carregar_multiplas_tabelas_mysql = _mod.carregar_multiplas_tabelas_mysql

__all__ = ["MySQLAgent", "DefinicaoTabela", "MySQLConexao", "carregar_tabela_mysql", "carregar_multiplas_tabelas_mysql"]
