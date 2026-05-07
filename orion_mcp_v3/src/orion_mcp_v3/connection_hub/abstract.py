"""Contrato genérico: o chamador passa SQL (ou comando Redis) e parâmetros; o backend executa."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping, Sequence


class AbstractDatastoreClient(ABC):
    """
    Cliente de dados orientado a consulta em texto.

    **PostgreSQL / MySQL:** `query` é SQL completo; `params` é tupla/lista posicional
    (`%s` em MySQL, `$1..$n` em Postgres com asyncpg).

    **Redis:** `query` é o nome do comando Redis (ex.: ``GET``, ``SET``, ``DEL``, ``HGETALL``);
    `params` é tupla dos argumentos seguintes (ex.: ``("minha_chave",)``).
    Os métodos ``insert`` / ``update`` / ``delete`` são atalhos semânticos para o mesmo
    ``execute_command`` — escolha o comando adequado em cada caso.
    """

    @abstractmethod
    async def select(self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> Any:
        """SELECT — devolve linhas (lista de dicts em SQL) ou resultado Redis."""

    @abstractmethod
    async def insert(self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> Any:
        """INSERT — SQL ou comando Redis equivalente (ex.: SET com NX)."""

    @abstractmethod
    async def update(self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> Any:
        """UPDATE — SQL ou comando Redis equivalente."""

    @abstractmethod
    async def delete(self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> Any:
        """DELETE — SQL ou comando Redis ``DEL`` / ``HDEL`` / etc."""

    @abstractmethod
    async def close(self) -> None:
        """Liberta pool ou conexão."""
