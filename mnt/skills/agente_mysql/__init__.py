from typing import TYPE_CHECKING

__all__ = ["MySQLAgent", "MySQLConexao", "carregar_tabela_mysql"]

if TYPE_CHECKING:
    from .helpers import MySQLAgent, MySQLConexao, carregar_tabela_mysql


def __getattr__(name: str):
    if name in __all__:
        from . import helpers as _helpers
        return getattr(_helpers, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
