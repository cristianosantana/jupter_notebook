Resumo do que foi implementado:

## Módulo genérico: `connection_hub`

Caminho: [`orion_mcp_v3/src/orion_mcp_v3/connection_hub/`](orion_mcp_v3/src/orion_mcp_v3/connection_hub/)

| Ficheiro | Função |
|----------|--------|
| `abstract.py` | **`AbstractDatastoreClient`** — `select`, `insert`, `update`, `delete`, `close` |
| `postgres_backend.py` | **`PostgresDatastoreClient`** — asyncpg, params **posicionais** (`$1`, `$2`); `select` devolve `list[dict]`; DML devolve `int` (linhas) |
| `mysql_backend.py` | **`MysqlDatastoreClient`** — asyncmy, `%s` com **tupla** ou **dict**; `select` com `DictCursor` |
| `redis_backend.py` | **`RedisDatastoreClient`** — `query` = comando Redis (`GET`, `SET`, `DEL`, …), `params` = tupla de argumentos |
| `pools.py` | Factories alinhadas ao v2: `create_postgres_pool`, `create_mysql_pool`, `create_redis_client` + `close_*` |

Pacote instalável: [`orion_mcp_v3/pyproject.toml`](orion_mcp_v3/pyproject.toml) (`pip install -e orion_mcp_v3`).

### Uso rápido

```python
from orion_mcp_v3 import (
    PostgresDatastoreClient,
    create_postgres_pool,
    MysqlDatastoreClient,
    create_mysql_pool,
    RedisDatastoreClient,
    create_redis_client,
)

pool = await create_postgres_pool("postgresql://user:pass@localhost/db")
pg = PostgresDatastoreClient(pool)
rows = await pg.select("SELECT id, name FROM t WHERE id = $1", (1,))
n = await pg.insert("INSERT INTO t (name) VALUES ($1)", ("x",))
await pg.close()
```

Redis:

```python
rcli = await create_redis_client("redis://localhost:6379/0")
rd = RedisDatastoreClient(rcli)
v = await rd.select("GET", ("minha_chave",))
await rd.close()
```

**Nota:** Em Postgres só são aceites params **posicionais** (tuple/list); em Redis, **não** uses `Mapping` — apenas tupla de argumentos do comando.