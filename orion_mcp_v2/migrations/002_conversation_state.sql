CREATE TABLE IF NOT EXISTS conversation_state (
  session_id TEXT PRIMARY KEY,
  user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  messages JSONB NOT NULL DEFAULT '[]'::jsonb,
  last_data JSONB,
  last_query_signature TEXT,
  state_status VARCHAR(32) DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS conversation_state_user_id_idx ON conversation_state (user_id);
CREATE INDEX IF NOT EXISTS conversation_state_created_at_idx ON conversation_state (created_at);
