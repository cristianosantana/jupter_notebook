"""Camada genérica de conexão a Postgres, MySQL e Redis com operações CRUD por texto de consulta."""

from orion_mcp_v3.connection_hub.abstract import AbstractDatastoreClient
from orion_mcp_v3.connection_hub.mysql_backend import MysqlDatastoreClient
from orion_mcp_v3.connection_hub.postgres_backend import PostgresDatastoreClient
from orion_mcp_v3.connection_hub.pools import (
    close_mysql_pool,
    close_postgres_pool,
    close_redis_client,
    create_mysql_pool,
    create_postgres_pool,
    create_redis_client,
)
from orion_mcp_v3.connection_hub.redis_backend import RedisDatastoreClient

__all__ = [
    "AbstractDatastoreClient",
    "PostgresDatastoreClient",
    "MysqlDatastoreClient",
    "RedisDatastoreClient",
    "create_postgres_pool",
    "close_postgres_pool",
    "create_mysql_pool",
    "close_mysql_pool",
    "create_redis_client",
    "close_redis_client",
]
