# Migrações PostgreSQL — memória conversacional

## Pré-requisito: pgvector

As migrações `003_memory_embeddings.sql` e índices IVFFlat usam o tipo `vector`. É preciso o **pacote pgvector no servidor PostgreSQL** (o erro `extension "vector" is not available` / ficheiro `vector.control` em falta indica que falta instalar no OS/imagem).

- **Docker:** imagem com pgvector, por exemplo `pgvector/pgvector:pg16`.
- **Debian/Ubuntu:** por exemplo `sudo apt install postgresql-16-pgvector` (ajuste à versão do seu servidor).

Com `python scripts/apply_migrations.py`, a extensão é criada automaticamente **após** o pgvector estar instalado no servidor.

Ordem de aplicação (prefixo numérico):

| Ficheiro | Conteúdo |
|----------|-----------|
| `001_extensions.sql` | Notas; `CREATE EXTENSION vector` é feito pelo script ou manualmente antes do `psql`. |
| `002_conversation_state.sql` | Camada 1 — literal (sessão actual). |
| `003_memory_embeddings.sql` | Camada 2 — embeddings + índice IVFFlat. |
| `004_memory_curta.sql` | Camada 2 — memória estruturada curta. |
| `005_memory_essence.sql` | Camada 3 — essência estável. |
| `006_memory_compression_log.sql` | Auditoria de compactação. |

**Conexão:** definir `POSTGRES_URL` ou `DATABASE_URL` em `orion_mcp_v3/.env` (ex.: `postgresql://postgres:secret@cs_postgres:5432/dev`). Não commitar credenciais.

## Sem `psql` instalado (recomendado)

Na pasta **`orion_mcp_v3`**:

```bash
pip install -r requirements.txt
python scripts/apply_migrations.py
```

O script usa **asyncpg** e lê o `.env` automaticamente.

## Com `psql` no sistema

Crie primeiro a extensão (se ainda não existir):

```bash
psql "$POSTGRES_URL" -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'
```

Depois aplique os ficheiros em ordem:

```bash
cd src/orion_mcp_v3/infra/postgres/migrations
for f in *.sql; do psql "$POSTGRES_URL" -v ON_ERROR_STOP=1 -f "$f"; done
```

## Notas de modelo

- `memory_curta` e `memory_essence` usam chave primária **composta** `(user_id, category)` e `(user_id, theme)` para permitir várias linhas por utilizador (alinhado ao Redis `memory:{user}:{categoria}`).
