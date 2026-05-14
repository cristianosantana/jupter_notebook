"""
broker.queries — Auto-discovery de query modules.

Cada módulo neste pacote expõe:
    SQL         — string SQL parametrizada (%s placeholders)
    ANSWERS     — tupla de frases que a query responde
    VALUE_KEY   — coluna principal de valor
    TIME_KEY    — coluna temporal (ou None)
    GRAIN       — granularidade: "day", "month", "total"
    LABEL_KEY   — coluna de label/dimensão (ou None)
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

_QUERY_MODULES: dict[str, Any] = {}


def _discover() -> None:
    """Importa todos os módulos irmãos e indexa por nome (slug)."""
    package = __package__
    path = __path__  # type: ignore[name-defined]
    for info in pkgutil.iter_modules(path):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{package}.{info.name}")
        if hasattr(mod, "SQL"):
            _QUERY_MODULES[info.name] = mod


_discover()


def get_all_modules() -> dict[str, Any]:
    """Retorna dict {slug: module} de todas as queries registradas."""
    return dict(_QUERY_MODULES)
