-- Estado global do índice de contexto (embed / K-Means) para gatilho + cron (single-tenant).

CREATE TABLE IF NOT EXISTS context_index_state (
    tenant_key VARCHAR(64) PRIMARY KEY DEFAULT 'default',
    last_embed_batch_at TIMESTAMPTZ,
    last_kmeans_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO context_index_state (tenant_key) VALUES ('default')
ON CONFLICT (tenant_key) DO NOTHING;
