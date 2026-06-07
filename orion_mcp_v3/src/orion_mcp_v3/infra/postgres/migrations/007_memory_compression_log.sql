-- Auditoria: evolução literal → resumo → essência

CREATE TABLE IF NOT EXISTS memory_compression_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(20) NOT NULL,
    from_state VARCHAR(50) NOT NULL,
    to_state VARCHAR(50) NOT NULL,
    messages_compressed INT NOT NULL DEFAULT 0,
    compression_ratio DOUBLE PRECISION,
    what_was_kept TEXT,
    what_was_dropped TEXT,
    compressed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_compression_log_user ON memory_compression_log (user_id);
CREATE INDEX IF NOT EXISTS idx_memory_compression_log_at ON memory_compression_log (compressed_at);

COMMENT ON TABLE memory_compression_log IS 'Registo de compactações entre camadas de memória.';
COMMENT ON COLUMN memory_compression_log.compression_ratio IS 'Ex.: 0.1 indica ~90% de informação agregada/descartada na compactação.';
