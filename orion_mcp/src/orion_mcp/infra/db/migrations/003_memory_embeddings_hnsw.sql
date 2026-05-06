-- Índice ANN HNSW (cosseno), alinhado com ORDER BY embedding <=> ... em retrieve_memory.
-- Requer pgvector com suporte a HNSW (versões recentes). Se falhar, migrate.py regista e adia.

CREATE INDEX IF NOT EXISTS memory_embeddings_embedding_hnsw_idx
  ON memory_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
