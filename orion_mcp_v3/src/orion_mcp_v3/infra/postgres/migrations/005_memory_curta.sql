-- Camada 2: RESUMO — memória estruturada curta (cache Postgres; espelho opcional em Redis)

CREATE TABLE IF NOT EXISTS memory_curta (
    user_id VARCHAR(20) NOT NULL,
    category VARCHAR(50) NOT NULL,
    recent_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    key_insights JSONB NOT NULL DEFAULT '[]'::jsonb,
    key_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    consolidated_at TIMESTAMPTZ,
    ttl_expires_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, category)
);

CREATE INDEX IF NOT EXISTS idx_memory_curta_ttl ON memory_curta (ttl_expires_at);

COMMENT ON TABLE memory_curta IS 'Resumo por utilizador e categoria (FATURAMENTO, QUALIDADE, …). PK composta permite várias categorias por user.';
COMMENT ON COLUMN memory_curta.category IS 'Alinhado à chave Redis memory:{user}:{CATEGORIA}.';
