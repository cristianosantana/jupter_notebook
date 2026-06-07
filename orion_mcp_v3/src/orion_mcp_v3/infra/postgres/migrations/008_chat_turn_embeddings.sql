-- FASE 2 — ROADMAP_EMBEDDING_PIPELINE
-- Nova tabela de embeddings alinhada ao pipeline de chat por turno.
--
-- Nota: a tabela memory_embeddings em 003_memory_embeddings.sql usa user_id + text
-- e serve a camada de resumo de longo prazo.
-- Esta tabela (chat_turn_embeddings) é específica para o retrieval por turno de sessão.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chat_turn_embeddings (
    id              BIGSERIAL PRIMARY KEY,
    session_id      VARCHAR(255) NOT NULL,
    message_id      VARCHAR(255) NOT NULL,
    role            VARCHAR(50)  NOT NULL,
    content_hash    VARCHAR(64)  NOT NULL,        -- SHA-256 hex do conteúdo (idempotência)
    content         TEXT         NOT NULL DEFAULT '',
    embedding       vector(1536) NOT NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_chat_turn_embedding_message UNIQUE (message_id)
);

-- Busca por similaridade coseno (operador <=>)
CREATE INDEX IF NOT EXISTS ix_chat_turn_emb_cosine
    ON chat_turn_embeddings
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Filtro por sessão (sempre presente nas queries de retrieval)
CREATE INDEX IF NOT EXISTS ix_chat_turn_emb_session
    ON chat_turn_embeddings (session_id);

-- Filtro por hash (idempotência na indexação)
CREATE INDEX IF NOT EXISTS ix_chat_turn_emb_hash
    ON chat_turn_embeddings (content_hash);

COMMENT ON TABLE chat_turn_embeddings IS
    'Embeddings de turnos de chat por sessão — alimenta o VectorRetriever (ROADMAP_EMBEDDING_PIPELINE Fase 2).';
COMMENT ON COLUMN chat_turn_embeddings.content_hash IS
    'SHA-256 hex do conteúdo bruto. Evita re-embedding de texto já indexado.';
