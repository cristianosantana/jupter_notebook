-- A extensão `vector` é criada em Python (`migrate.py`) com tratamento de erro.
-- Requer pgvector instalado no servidor PostgreSQL (pacote `postgresql-16-pgvector` ou imagem com pgvector).

CREATE TABLE IF NOT EXISTS memory_embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id TEXT NOT NULL,
  content TEXT NOT NULL,
  embedding vector(1536) NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS memory_embeddings_session_idx
  ON memory_embeddings (session_id);

CREATE INDEX IF NOT EXISTS memory_embeddings_metadata_gin
  ON memory_embeddings USING gin (metadata);
