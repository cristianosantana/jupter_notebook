"""Redis: `query` é o comando; `params` são os argumentos seguintes (tupla)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from orion_mcp_v3.connection_hub.abstract import AbstractDatastoreClient


def _redis_args(params: Sequence[Any] | Mapping[str, Any] | None) -> tuple[Any, ...]:
    if params is None:
        return ()
    if isinstance(params, Mapping):
        raise TypeError("RedisDatastoreClient: use tupla de argumentos Redis, ex.: ('chave',) ou ('k','v')")
    return tuple(params)


class RedisDatastoreClient(AbstractDatastoreClient):
    """
    Encaminha todos os métodos para ``execute_command(comando, *args)``.

    Exemplos::

        await client.select("GET", ("user:1",))
        await client.insert("SET", ("user:1", "valor"))
        await client.delete("DEL", ("user:1",))
        await client.update("SET", ("contador", "10"))
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    async def _cmd(self, query: str, params: Sequence[Any] | Mapping[str, Any] | None) -> Any:
        args = _redis_args(params)
        q = query.strip()
        if not q:
            raise ValueError("comando Redis vazio")
        return await self._client.execute_command(q, *args)

    async def select(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> Any:
        return await self._cmd(query, params)

    async def insert(self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> Any:
        return await self._cmd(query, params)

    async def update(self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> Any:
        return await self._cmd(query, params)

    async def delete(self, query: str, params: Sequence[Any] | Mapping[str, Any] | None = None) -> Any:
        return await self._cmd(query, params)

    async def close(self) -> None:
        close = getattr(self._client, "aclose", None)
        if callable(close):
            await close()
            return
        c = getattr(self._client, "close", None)
        if callable(c):
            await c() if hasattr(c, "__await__") else c()
