# Orion MCP v3

Pacote base (`connection_hub`: Postgres, MySQL, Redis), migrações de memória conversacional em PostgreSQL e especificação Redis.

## Documentação (ecossistema)

| Documento | Conteúdo |
|-----------|------------|
| [`docs/README.md`](docs/README.md) | Índice da pasta `docs/` |
| **[`docs/architecture/ORION_V3_MASTER_ARCHITECTURE.md`](docs/architecture/ORION_V3_MASTER_ARCHITECTURE.md)** | Índice mestre: infraestrutura analytics × plano incremental × cognição |
| [`docs/execution/PLANO_EXECUCAO.md`](docs/execution/PLANO_EXECUCAO.md) | Roadmap técnico incremental |
| [`docs/roadmaps/ROADMAP_COM_MYSQL_INTEGRADO.md`](docs/roadmaps/ROADMAP_COM_MYSQL_INTEGRADO.md) | Pipeline analytics + MySQL |
| [`docs/architecture/ARQUITETURA_COGNITIVA_CENTRAL.md`](docs/architecture/ARQUITETURA_COGNITIVA_CENTRAL.md) | Arquitetura cognitiva superior |

## Arranque rápido

```bash
cd orion_mcp_v3
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## Migrações PostgreSQL

Variável **`POSTGRES_URL`** ou **`DATABASE_URL`** em `.env` na raiz desta pasta.

No **host** (fora do Docker), use `127.0.0.1` ou `localhost` e a **porta exposta** do Postgres — não use o hostname interno do compose (`cs_postgres`), pois não resolve no seu sistema.

```bash
python scripts/apply_migrations.py
```

É necessário **pgvector instalado no servidor PostgreSQL** (embeddings em `memory_embeddings`). Se aparecer `extension "vector" is not available`, instale o pacote no OS ou use uma imagem Docker com pgvector — ver o README das migrações.

Detalhes: [`src/orion_mcp_v3/infra/postgres/migrations/README.md`](src/orion_mcp_v3/infra/postgres/migrations/README.md).

Migrações MySQL futuras podem seguir o mesmo padrão em `src/orion_mcp_v3/infra/mysql/migrations/` (script dedicado quando existir).

## Redis (keyspace)

[`src/orion_mcp_v3/infra/redis/MEMORY_KEYSPACE.md`](src/orion_mcp_v3/infra/redis/MEMORY_KEYSPACE.md)


## Executar Tests

No projeto **`orion_mcp_v3`** os testes estão em `tests/` e o `pyproject.toml` define `pytest` em extras de desenvolvimento e `pythonpath = ["src"]`.

### Passos típicos

1. Na raíz do pacote (`orion_mcp_v3/`):

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

2. Executar todos os testes:

```bash
pytest tests/ -v
```
