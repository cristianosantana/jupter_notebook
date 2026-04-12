-- Embeddings de sessão, centróides K-Means e embeddings opcionais por mensagem (JSONB = vector como array).

CREATE TABLE IF NOT EXISTS session_embeddings (
    session_id UUID PRIMARY KEY REFERENCES sessions (session_id) ON DELETE CASCADE,
    embedding_model VARCHAR(64) NOT NULL DEFAULT 'text-embedding-3-small',
    embedding JSONB NOT NULL,
    text_digest TEXT,
    cluster_id INT,
    cluster_model_version VARCHAR(64),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_embeddings_cluster
    ON session_embeddings (cluster_model_version, cluster_id);

CREATE TABLE IF NOT EXISTS kmeans_centroids (
    id BIGSERIAL PRIMARY KEY,
    model_version VARCHAR(64) NOT NULL,
    n_clusters INT NOT NULL,
    cluster_id INT NOT NULL,
    centroid JSONB NOT NULL,
    n_points INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (model_version, cluster_id)
);

CREATE TABLE IF NOT EXISTS conversation_message_embeddings (
    id BIGSERIAL PRIMARY KEY,
    message_id BIGINT NOT NULL REFERENCES conversation_messages (id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES sessions (session_id) ON DELETE CASCADE,
    embedding_model VARCHAR(64) NOT NULL DEFAULT 'text-embedding-3-small',
    embedding JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (message_id, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_conv_msg_emb_session ON conversation_message_embeddings (session_id);
