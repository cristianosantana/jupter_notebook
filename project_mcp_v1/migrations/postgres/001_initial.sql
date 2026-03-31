-- Sessões Maestro: utilizadores opcionais + transcript só de especialistas (app grava após run).

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255),
    concessionaria_id INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id UUID PRIMARY KEY,
    user_id VARCHAR(64) REFERENCES users (user_id) ON DELETE SET NULL,
    current_agent VARCHAR(50) NOT NULL DEFAULT 'maestro',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    metadata JSONB
);

CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON sessions (last_active_at);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions (session_id) ON DELETE CASCADE,
    seq INT NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT,
    tool_name VARCHAR(128),
    tool_call_id VARCHAR(128),
    tool_args JSONB,
    tool_calls JSONB,
    extra JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_session ON conversation_messages (session_id, seq);
