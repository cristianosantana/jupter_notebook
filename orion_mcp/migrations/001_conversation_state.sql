CREATE TABLE IF NOT EXISTS conversation_state (
  session_id TEXT PRIMARY KEY,
  state JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS conversation_state_updated_at_idx
  ON conversation_state (updated_at DESC);
