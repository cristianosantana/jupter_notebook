-- Camada 3: ESSÊNCIA — conclusões estáveis por tema

CREATE TABLE IF NOT EXISTS memory_essence (
    user_id VARCHAR(20) NOT NULL,
    theme VARCHAR(50) NOT NULL,
    observation TEXT,
    key_finding TEXT,
    recommendation TEXT,
    stable_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confidence VARCHAR(20),
    PRIMARY KEY (user_id, theme)
);

CREATE INDEX IF NOT EXISTS idx_memory_essence_confidence ON memory_essence (confidence);

COMMENT ON TABLE memory_essence IS 'Essência: observações persistentes por utilizador e tema.';
COMMENT ON COLUMN memory_essence.confidence IS 'high | medium | low (convénção da aplicação).';
