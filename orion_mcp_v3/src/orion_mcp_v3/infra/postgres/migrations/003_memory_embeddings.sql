-- Camada 2: RESUMO — vectores para busca por similaridade (TTL ~7 dias na coluna)

CREATE TABLE IF NOT EXISTS memory_embeddings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(20) NOT NULL,
    text TEXT NOT NULL,
    embedding vector(1536) NOT NULL,
    type VARCHAR(50),
    category VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ttl_expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_memory_embeddings_user_id ON memory_embeddings (user_id);
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_ttl ON memory_embeddings (ttl_expires_at);
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_category ON memory_embeddings (category);

-- IVFFlat: requer pgvector; lists ajustável em bases grandes
CREATE INDEX IF NOT EXISTS idx_memory_embeddings_ivfflat
    ON memory_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

COMMENT ON TABLE memory_embeddings IS 'Camada resumo: fragmentos indexados com embedding (pgvector).';
COMMENT ON COLUMN memory_embeddings.type IS 'question | insight | metric (convénção da aplicação).';
