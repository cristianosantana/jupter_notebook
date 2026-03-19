# app/services/maestro_df_registry.py — Namespace compartilhado para DataFrames no processo FastAPI / worker
from __future__ import annotations

import threading
from typing import Any, Dict, MutableMapping

_lock = threading.Lock()
_namespace: Dict[str, Any] = {}


def get_namespace() -> MutableMapping[str, Any]:
    """
    Dict mutável a passar como ``mysql_injetar_namespace`` ao Maestro quando
    ``dataframe_preexistente`` aponta para uma variável já registrada aqui.
    """
    return _namespace


def register(name: str, value: Any) -> None:
    """Associa um nome a um objeto (ex.: pandas.DataFrame)."""
    with _lock:
        _namespace[name] = value


def unregister(name: str) -> None:
    """Remove uma entrada do namespace."""
    with _lock:
        _namespace.pop(name, None)


def clear() -> None:
    """Esvazia o registry (útil em testes)."""
    with _lock:
        _namespace.clear()


def list_keys() -> list:
    """Nomes registrados (sem valores)."""
    with _lock:
        return sorted(_namespace.keys())
