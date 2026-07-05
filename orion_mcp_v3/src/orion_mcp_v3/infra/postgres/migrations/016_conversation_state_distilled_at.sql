ALTER TABLE conversation_state
ADD COLUMN IF NOT EXISTS distilled_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_conversation_state_distilled_at
ON conversation_state (distilled_at);

COMMENT ON COLUMN conversation_state.distilled_at IS
'Momento em que a sessão foi processada pela destilação supervisionada de memória remissiva.';
