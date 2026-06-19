# Migrações PostgreSQL — memória conversacional

## Pré-requisito: pgvector

As migrações `003_memory_embeddings.sql`, `008_chat_turn_embeddings.sql` e `010_remissive_memory_schema.sql` usam o tipo `vector`. É preciso o **pacote pgvector no servidor PostgreSQL** (o erro `extension "vector" is not available` / ficheiro `vector.control` em falta indica que falta instalar no OS/imagem).

- **Docker:** imagem com pgvector, por exemplo `pgvector/pgvector:pg16`.
- **Debian/Ubuntu:** por exemplo `sudo apt install postgresql-16-pgvector` (ajuste à versão do seu servidor).

Com `python scripts/apply_migrations.py`, a extensão é criada automaticamente **após** o pgvector estar instalado no servidor.

Ordem de aplicação (prefixo numérico):

| Ficheiro | Conteúdo |
|----------|-----------|
| `001_extensions.sql` | Notas; `CREATE EXTENSION vector` é feito pelo script ou manualmente antes do `psql`. |
| `002_conversation_state.sql` | Camada 1 — literal (sessão actual). |
| `003_memory_embeddings.sql` | Camada 2 legada — embeddings + índice IVFFlat. |
| `004_conversation_external_id.sql` | `external_id` em `conversation_state` (IDs de sessão não-UUID). |
| `005_memory_curta.sql` | Camada 2 legada — memória estruturada curta. |
| `006_memory_essence.sql` | Camada 3 legada — essência estável. |
| `007_memory_compression_log.sql` | Auditoria legada de compactação. |
| `008_chat_turn_embeddings.sql` | Embeddings por turno de chat — fonte read-only para destilação V2. |
| `009_chat_turn_embeddings_content.sql` | Coluna `content` em `chat_turn_embeddings`. |
| `010_remissive_memory_schema.sql` | V2 destrutiva de `memory_curta`, `memory_embeddings`, `memory_essence` e `memory_compression_log`. |
| `011_memory_compression_log_wide_keys.sql` | Aumenta campos de auditoria do `memory_compression_log` para payloads reais do destilador. |
| `012_memory_essence_wide_keys.sql` | Aumenta campos curtos de `memory_essence` para temas/confianças reais do destilador. |
| `013_memory_curta_last_seen.sql` | Adiciona `last_seen_at` para rotação de conhecimento remissivo não renovado. |
| `014_alter_column_context_key.sql` | Amplia `memory_curta.context_key` para chaves longas do destilador. |

### Chat Público — migrações isoladas

As tabelas `public_chat_*` **não** estão nesta pasta. Migrações e script de apply vivem em:

`src/orion_mcp_v3/public_chat/infrastructure/postgres/migrations/`

```bash
python -m orion_mcp_v3.public_chat.scripts.apply_migrations
```

Documentação: [`public_chat/README.md`](../../public_chat/README.md)

### Migrações 008/009 — embeddings por turno

Estas migrações alimentam apenas o subsistema opcional `chat_turn_embeddings` (`ChatTurnEmbeddingStore`, `VectorRetriever`) e a leitura read-only do comando externo de destilação remissiva. **Não** fazem parte do núcleo analítico (planner, evidence, MySQL).

- Documentação: [`docs/architecture/MEMORY_AUGMENTATION_LAYER.md`](../../../../docs/architecture/MEMORY_AUGMENTATION_LAYER.md)
- Activar via `ORION_EMBEDDING_MODE=index_only|retrieve` (e API key LLM); default é `off`.
- **Congelado:** não adicionar novos retrievers vector no `broker/`, nem writer para `003_memory_embeddings.sql` sem decisão explícita.

#### Lista de não-fazer (até nova decisão arquitectural)

- Embedding-centric orchestration ou vector-first memory.
- Vector retrieval dentro do `MemoryComposer` ou do planner.
- Async no `broker/` / `runtime/` apenas por causa de embeddings.
- Substituir `SemanticRetriever` lexical quando vector estiver activo (usar **paralelo**).
- Tornar embeddings obrigatórios para `POST /chat`.

### Migração 010 — memória remissiva V2

`010_remissive_memory_schema.sql` recria a visão materializada de memória remissiva:

- `memory_curta`: conteúdo validado, com upsert por `context_key` calculado no código a partir de `user_id`, `category`, `theme` e `periodo` opcional; renova `last_seen_at` a cada destilação.
- `memory_embeddings`: perguntas curtas vetoriais apontando para `memory_curta` por `origin_id`/`origin_type`; usa `vector(1536)` com IVFFlat `lists = 100`, e as consultas devem configurar `ivfflat.probes` localmente antes da busca.
- `memory_essence`: achados estáveis com unique `(user_id, theme)`.
- `memory_compression_log`: auditoria da destilação de uma janela supervisionada, idempotente por `batch_key`.
- `011_memory_compression_log_wide_keys.sql`: amplia `batch_key`, `from_state` e `to_state` para `VARCHAR(255)` para evitar truncamento de janelas ISO e estados descritivos.
- `012_memory_essence_wide_keys.sql`: amplia `memory_essence.theme` e `confidence` para `VARCHAR(255)` para preservar rótulos gerados pelo LLM.
- `013_memory_curta_last_seen.sql`: adiciona `memory_curta.last_seen_at` e índice para limpeza periódica de conhecimento que deixou de aparecer na destilação.

A rotina que grava essas tabelas é o comando independente:

```bash
python scripts/distill_supervised_memory.py \
  --start 2026-06-09T00:00:00Z \
  --end 2026-06-10T00:00:00Z
```

Esse comando deve ser chamado por cron externo. Ele lê `conversation_state` e `chat_turn_embeddings` em modo read-only e não é registrado no lifespan, nas rotas de chat, no retrieval runtime ou no `ChatTurnEmbeddingStore`.

**Conexão:** definir `ORION_POSTGRES_URL` ou `ORION_DATABASE_URL` em `orion_mcp_v3/.env` (ex.: `postgresql://postgres:secret@cs_postgres:5432/dev`). Não commitar credenciais.

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

- Antes da migração `010`, as tabelas `memory_*` tinham formato legado usado por planos anteriores.
- Depois da migração `010`, `memory_curta` e `memory_essence` usam `id` sequencial; a idempotência vem de `memory_curta.context_key`, de `memory_essence` unique `(user_id, theme)` e de `memory_compression_log.batch_key`.
- `memory_embeddings` representa múltiplas perguntas de índice apontando para um conteúdo validado em `memory_curta`.
