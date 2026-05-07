-- Camada 1: LITERAL — conversa actual na sessão (~1h)

CREATE TABLE IF NOT EXISTS conversation_state (
    session_id UUID PRIMARY KEY,
    user_id VARCHAR(20),
    messages JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_conversation_state_user_id ON conversation_state (user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_state_expires_at ON conversation_state (expires_at);

COMMENT ON TABLE conversation_state IS 'Camada literal: todas as mensagens da sessão até expiração (~1h).';
COMMENT ON COLUMN conversation_state.messages IS 'Histórico serializado em JSONB (roles, conteúdo, timestamps).';
