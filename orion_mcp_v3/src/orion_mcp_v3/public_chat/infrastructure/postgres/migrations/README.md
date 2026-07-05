# Migrações PostgreSQL — Chat Público

Migrações **isoladas** do núcleo Orion. Vivem em `public_chat/infrastructure/postgres/migrations/`.

## Pré-requisito

PostgreSQL com suporte a `gen_random_uuid()` (PostgreSQL 13+) e JSONB.

**Não** requer pgvector — o Chat Público não cria colunas vetoriais nas suas tabelas.

## Ordem de aplicação

| Ficheiro | Conteúdo |
|---|---|
| `001_public_chat_schema.sql` | `public_chat_questions`, `public_chat_responses`, pivô de auditoria |

## Aplicar migrações

Na pasta `orion_mcp_v3`:

```bash
export PUBLIC_CHAT_POSTGRES_URL="postgresql://postgres:secret@127.0.0.1:5432/dev"
python3 -m orion_mcp_v3.public_chat.scripts.apply_migrations
```

Variáveis aceites: `PUBLIC_CHAT_POSTGRES_URL`, `PUBLIC_CHAT_DATABASE_URL`.

O script lê opcionalmente `public_chat/.env` e o `.env` do projeto.

## Notas

- Tabelas prefixadas `public_chat_*` — sem `user_id`, conhecimento global.
- Cache exato por `(topic, semantic_hash)` — sem embeddings nestas tabelas.
- Leitura de `memory_*` (fase 2+) usa o mesmo Postgres mas SQL próprio em `PublicRemissiveReader`.
